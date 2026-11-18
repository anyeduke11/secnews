/**
 * MaintPage 后端响应类型定义 (从 MaintPage.tsx 拆出)。
 *
 * 纯 type 声明, 无运行时导出; 各形状注释随类型一并迁移, 口径未改动。
 */

/** 后端权威形状 = maintenance_service.db_health() (fragmentation_pct 已是百分数)。 */
export interface HealthResp {
  size_mb?: number;
  page_count?: number;
  freelist_pages?: number;
  fragmentation_pct?: number;
  journal_mode?: string;
}

/** 后端权威形状 = maintenance_service.dirty_data_report() (嵌套;
 * DEV-0322: older_than_7_days → older_than_retention, 口径改台账动态
 * retention 且与 archive_quality_logs 同 isoformat cutoff)。 */
export interface DirtyReportResp {
  quality_check_logs?: { total?: number; older_than_retention?: number; retention_days?: number };
  duplicate_hotspots?: number;
  duplicate_knowledge_items?: number;
  orphan_raw_items?: number;
  invalid_urls?: number;
}

/** 后端权威形状 = GET /quality-log-tiers (DEV-0322 进程内实测:
 * bands 末档 in_window=false 的 rows = 此刻点"清理"将真实归档的量)。 */
export interface TierBand {
  index: number;
  in_window: boolean;
  from_days: number | null;
  to_days: number;
  rows: number;
  est_bytes: number;
}

export interface TiersResp {
  tier_days?: number;
  tiers?: number;
  window_days?: number;
  ledger_retention_days?: number;
  total_rows?: number;
  avg_row_bytes?: number;
  total_est_bytes?: number;
  bands?: TierBand[];
}

/** 后端权威形状 = maintenance_service.run_vacuum() (DEV-0318: 旧 ok/duration_ms/reindexed 为想象契约)。 */
export interface VacuumResp {
  status?: string;
  total_seconds?: number;
}

/** 后端权威形状 = GET /api/maintenance/index-health (DEV-0320, 进程内实测:
 * check=ok|\"N issues\"|probe_failed:*; user/auto 索引分列;
 * stat1_covered 为绝对数展示 — 小表/纯 autoindex 表 ANALYZE 有意跳过,
 * 覆盖率分母会制造"欠 stats"假异常, 前端不用 tables_with_indexes 组成比率)。 */
export interface IndexHealthSchema {
  schema: string;
  file: string;
  user_indexes: number;
  auto_indexes: number;
  tables_with_indexes: number;
  stat1_covered: number;
  check: string;
  check_errors: string[];
  check_ms: number;
}

export interface IndexHealthResp {
  mode?: string;
  checked_at?: string;
  schemas?: IndexHealthSchema[];
  totals?: {
    user_indexes: number;
    auto_indexes: number;
    schemas_ok: number;
    schemas_total: number;
  };
}

/** 后端权威形状 = cleanup_quality_logs() (薄包装 archive_quality_logs;
 * DEV-0318: 旧 /cleanup + {deleted} 全对不上 → 按钮永远空跑)。 */
export interface CleanupResp {
  dry_run?: boolean;
  retention_days?: number;
  rows_to_delete?: number;
  rows_archived?: number;
  rows_remaining_after?: number;
}

export type ToolStatus = 'idle' | 'running' | 'ok' | 'error';