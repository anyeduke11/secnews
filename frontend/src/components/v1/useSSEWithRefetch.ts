// T17.5: useSSEWithRefetch - V1Prototype 顶层 useSSE 订阅 + Toast 触发.
//
// 5 event_type (T17 已落 publish_event):
//   v1_judgment (info) / v1_action (info) / v1_artifact verify+accept (success)
//   v1_knowledge (info) / v1_signal (info)
//
// 触发:
//   - onEvent: refetch 对应 view (setter) + toast.show (走 dedupe + muted, 2s 合并 + localStorage 静默)
//   - useSSE 自动重连 + 3s 延时 (P0.3)
import { useCallback } from "react";

import { useSSE } from "../../hooks/useSSE";
import { useToast } from "../Toast";

type Tab = "workbench" | "intel" | "cases" | "knowledge";

// event_type → (Tab, toast message, toast type) 映射
const EVENT_TAB_MAP: Record<string, { tab: Tab | null; message: string; type: "info" | "success" | "warning" }> = {
  v1_judgment: { tab: "cases", message: "新判断已发布", type: "info" },
  v1_action: { tab: "cases", message: "新行动已启动", type: "info" },
  v1_artifact: { tab: "cases", message: "产物状态已更新", type: "success" },
  v1_knowledge: { tab: "knowledge", message: "知识状态已更新", type: "info" },
  v1_signal: { tab: "intel", message: "新信号已录入", type: "info" },
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

  useSSE({ onEvent, autoReconnect: true, reconnectDelay: 3000 });
}
