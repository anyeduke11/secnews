/**
 * settings/DatabaseMaintenance — 危险动作类型 / 文案表 / 结果消息类型。
 *
 * 拆分自 DatabaseMaintenance.tsx, 仅承载类型与常量, 无运行时逻辑.
 */

export type DangerAction = 'vacuum' | 'dedup' | 'cleanup';

export const DANGER_LABELS: Record<DangerAction, string> = {
  vacuum: 'VACUUM 压缩',
  dedup: '重复数据去重',
  cleanup: '清理历史数据',
};

/** 操作结果消息 (null = 未产生结果) */
export type Msg = { kind: 'ok' | 'bad' | 'mute'; text: string } | null;