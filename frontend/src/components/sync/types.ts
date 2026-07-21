/**
 * sync/types — SyncPage 共享类型定义。
 *
 * Phase 1B 修复: 解决 SyncBundleConfig ↔ SyncConfigForm/SyncOperations 循环 import。
 * 所有类型统一从此文件 re-export, 避免循环引用。
 */
export type SyncFrequency = 'manual' | 'daily' | 'weekly' | 'after_collect';
export type SyncDirection = 'push' | 'pull' | 'bidirectional';
export type SyncPhase = SyncDirection | null;

export interface BundleConfigForm {
  webdav_url: string;
  webdav_username: string;
  webdav_password: string;
  master_key: string;
  remote_path: string;
  auto_sync_enabled: boolean;
  sync_frequency: SyncFrequency;
}

export interface EffectiveRemoteInfo {
  effective_remote_path?: string | null;
  effective_display_name?: string | null;
}

export interface LastSyncResult {
  status: string;
  direction: string;
  records_count?: number;
  conflict_count?: number;
  message?: string;
}

export interface BundlePreview {
  record_counts: Record<string, number>;
}

export interface ConflictInfo {
  conflicts: Record<string, number>;
  total: number;
}

export interface HistoryItem {
  id: string | number;
  status: string | null;
  direction: string;
  started_at: string;
  records_count?: number | null;
  conflict_count?: number | null;
  error_message?: string | null;
}
