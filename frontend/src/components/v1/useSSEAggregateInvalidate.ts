/**
 * C11 R18+R19: useSSEAggregateInvalidate
 *
 * 5 service (judgment / action / artifact / knowledge / signal) 通过 v1_outbox
 * 持久化事件, 后台 OutboxDispatcher 推 SSE 广播. 旧实现 (T17.5) 仅按 event_type
 * 全局 refetch, 同 tab 多 CaseDetail 时触发 O(case 数) 次无效重拉.
 *
 * 修复 (按 aggregate_type + id + revision 精确失效):
 *   1. onEvent 解析事件 payload, 提取 (aggregate_type, aggregate_id, revision)
 *   2. 仅当与当前 case 关联的 aggregate (case / judgment / action / run / artifact)
 *      变更时, 才触发 onCaseRefetch (走 ?case_id= 匹配)
 *   3. revision 防回退: 比较新事件 revision 与本地缓存, 旧 revision 直接 ignore
 *   4. signal / knowledge 与 CaseDetail 关联不直接, 由调用方传 caseIdToMatch 决定
 *
 * 5 event_type (与 backend publish_event 写入对齐):
 *   v1_judgment (judgment_id / case_id / revision)
 *   v1_action (action_id / case_id / revision)
 *   v1_artifact (artifact_id / run_id / case_id / revision)
 *   v1_knowledge (knowledge_id / case_id / revision)
 *   v1_signal (signal_id / case_id / revision)
 *
 * Batch 5 任务 C: 连接层已迁移到统一注册器 useRealtimeInvalidation
 * (src/hooks/realtime.ts, 底座仍为 useSSE), 失效语义逐字保留:
 * case_id 匹配 + revision 防回退 + revision 缺失降级 refetch。
 */

import { useCallback, useRef } from "react";
import { useRealtimeInvalidation, V1_AGGREGATE_EVENT_TYPES } from "../../hooks/realtime";

export interface AggregateEventData {
  id?: number;
  event_type?: string;
  aggregate_type?: string;
  aggregate_id?: string;
  case_id?: string;
  revision?: number;
  [k: string]: unknown;
}

export interface UseSSEAggregateInvalidateOptions {
  // 当前 CaseDetail 展示的 case id (None = 不订阅).
  currentCaseId: string | null;
  // 当前 case 的 revision (从 aggregate 拉取, 事件 revision 高才更新).
  currentRevision: number;
  // 触发 refetch (上层 V1Prototype 包装成 refetchAggregate).
  onRefetch: () => void;
  // 持久化 last_id (跨刷新续传).
  onLastId?: (id: number) => void;
}

export function useSSEAggregateInvalidate(opts: UseSSEAggregateInvalidateOptions): { connected: boolean } {
  const { currentCaseId, currentRevision, onRefetch, onLastId } = opts;
  // ref 持有, 避免重连时 stale closure
  const ctxRef = useRef({ currentCaseId, currentRevision, onRefetch });
  ctxRef.current = { currentCaseId, currentRevision, onRefetch };

  const onEvent = useCallback(
    (_type: string, rawData: unknown) => {
      if (!ctxRef.current.currentCaseId) return;
      const data = rawData as AggregateEventData;
      if (!data || typeof data !== "object") return;
      // 事件必须与当前 case 关联, 否则 ignore.
      // 兼容两种字段: payload 直接 case_id (publish_event 写入) 或 outer wrapper.
      const evCaseId = data.case_id;
      if (evCaseId !== ctxRef.current.currentCaseId) return;
      // 5 service 改 outbox 后, 事件 payload 必含 aggregate_type / aggregate_id / revision.
      // revision 缺失 (旧实现或 hot-patch 漏字段) → fallback 触发 refetch (降级路径, 不冒充成功).
      const newRev = typeof data.revision === "number" ? data.revision : null;
      if (newRev !== null && newRev < ctxRef.current.currentRevision) {
        // 旧 revision, 静默 ignore (按 R18 重复/错序不回退状态).
        return;
      }
      ctxRef.current.onRefetch();
    },
    [],
  );

  // types 过滤上移到注册器 entry 层: 只有 5 个 v1_* aggregate 事件携带
  // case_id/revision payload, 其余 (埋点 / collect_done / alert …) 无需进入 handler。
  const { connected } = useRealtimeInvalidation(
    [{ types: V1_AGGREGATE_EVENT_TYPES, handler: onEvent }],
    { onLastId },
  );
  return { connected };
}
