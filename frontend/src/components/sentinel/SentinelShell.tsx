/**
 * SentinelShell — 兼容桥 (2026-11-17 结构性拆分)
 *
 * 实现已迁至 src/shell/ (types / menuOf / pipe / PipeBar / MenuNav / AppShell),
 * 本文件仅保旧路径 (6 处现有 import 暂不改), B6 全量改指后删除。
 */
export { SentinelShell } from '../../shell/AppShell';
export { menuOf } from '../../shell/menuOf';
export { fetchPipe, usePipe, usePipeReloadOnSse } from '../../shell/pipe';
export type { SentinelLayer, PipeSnapshot, SourceHealthRow } from '../../shell/types';