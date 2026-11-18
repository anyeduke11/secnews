/**
 * SyncStatusBadge — 同步状态徽章 (sync 域词汇 → L1 StatusBadge 薄封装)。
 *
 * 在 SyncStatusPanel / SyncHistory 中复用, 单独抽出避免循环依赖。
 * 视觉走 design/redesign-v1 R-2 的状态徽章词汇 (.badge + .b-*, 见 primitives/primitives.css)。
 */

import { StatusBadge, type StatusTone } from '../../primitives/StatusBadge';

interface SyncStatusBadgeProps {
  status?: string | null;
}

const STATUS_MAP: Record<string, { tone: StatusTone; label: string }> = {
  success: { tone: 'ok', label: '成功' },
  error: { tone: 'risk', label: '失败' },
  skipped: { tone: 'warn', label: '跳过' },
  unknown: { tone: 'neutral', label: '未知' },
};

export function SyncStatusBadge({ status }: SyncStatusBadgeProps) {
  const s = STATUS_MAP[status || 'unknown'] ?? STATUS_MAP.unknown;
  return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>;
}