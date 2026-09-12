// T17.5: useSSEWithRefetch - V1Prototype 顶层 useSSE 订阅 + Toast 触发.
//
// 5 event_type (T17 已落 publish_event):
//   v1_judgment (info) / v1_action (info) / v1_artifact verify+accept (success)
//   v1_knowledge (info) / v1_signal (info)
//
// 触发:
//   - onEvent: refetch 对应 view (setter) + toast.show (走 dedupe + muted, 2s 合并 + localStorage 静默)
//   - SSE 自动重连 + 3s 延时 (P0.3)
//
// Batch 5 任务 C: 连接层已迁移到统一注册器 useRealtimeInvalidation
// (src/hooks/realtime.ts, 底座仍为 useSSE), 全局 refetch + toast 语义逐字保留;
// 事件类型魔法字符串收敛为 SSE_EVENTS 常量。
import { useCallback } from "react";

import {
  useRealtimeInvalidation,
  SSE_EVENTS,
  V1_AGGREGATE_EVENT_TYPES,
} from "../../hooks/realtime";
import { useToast } from "../Toast";

type Tab = "workbench" | "intel" | "cases" | "knowledge";

// event_type → (Tab, toast message, toast type) 映射
const EVENT_TAB_MAP: Record<string, { tab: Tab | null; message: string; type: "info" | "success" | "warning" }> = {
  [SSE_EVENTS.V1_JUDGMENT]: { tab: "cases", message: "新判断已发布", type: "info" },
  [SSE_EVENTS.V1_ACTION]: { tab: "cases", message: "新行动已启动", type: "info" },
  [SSE_EVENTS.V1_ARTIFACT]: { tab: "cases", message: "产物状态已更新", type: "success" },
  [SSE_EVENTS.V1_KNOWLEDGE]: { tab: "knowledge", message: "知识状态已更新", type: "info" },
  [SSE_EVENTS.V1_SIGNAL]: { tab: "intel", message: "新信号已录入", type: "info" },
};

// T19 case-level refetch 占位: 不直接传 setter, 由 V1Prototype 内调用 setSelectedCase (避开类型冲突)
export function useSSEWithRefetch(
  setTab: (t: Tab) => void,
  onCaseRefetch?: (caseId: string) => void,
): void {
  const { show } = useToast();

  const onEvent = useCallback(
    (type: string, data: unknown) => {
      const m = EVENT_TAB_MAP[type];
      if (!m) return;  // 未注册 type (如 collect_done) 忽略
      if (m.tab) setTab(m.tab);
      // T19: case-level refetch (data 带 case_id 时触发)
      if (onCaseRefetch && data && typeof data === "object" && "case_id" in data) {
        onCaseRefetch((data as { case_id: string }).case_id);
      }
      show({ type: m.type, message: "[" + type + "] " + m.message, duration: 3000 });
    },
    [setTab, onCaseRefetch, show]
  );

  // types 收敛到注册器 entry 层 (原实现无 types 过滤、handler 内自行 ignore,
  // 两者对 EVENT_TAB_MAP 之外的事件行为等价: 均不产生任何副作用)。
  useRealtimeInvalidation([{ types: V1_AGGREGATE_EVENT_TYPES, handler: onEvent }]);
}
