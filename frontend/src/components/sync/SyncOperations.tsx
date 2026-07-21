/**
 * SyncOperations — 手动同步操作区 (主密钥输入 + push/pull/bidirectional 按钮 + 上次结果 + 预览)。
 *
 * Phase 1B: 拆自原 SyncBundleConfig.tsx 的下半段 (sync operations section)。
 * 仅渲染, props-only; 状态与回调由 index.tsx 注入。
 */
import React from 'react';
import { Icon } from '../Icon';
import type { BundleConfigForm, BundlePreview, LastSyncResult, SyncDirection, SyncPhase } from './types';

const FREQUENCY_BADGE = (f: BundleConfigForm['sync_frequency']) =>
  f === 'weekly' ? '每周一 10:30'
  : f === 'daily' ? '每日 10:30'
  : f === 'after_collect' ? '采集后自动'
  : '手动同步';

interface SyncOperationsProps {
  form: BundleConfigForm;
  configured: boolean;
  syncing: SyncPhase;
  masterKeyForSync: string;
  setMasterKeyForSync: React.Dispatch<React.SetStateAction<string>>;
  lastResult: LastSyncResult | null;
  preview: BundlePreview | null;
  loading: boolean;
  onSync: (direction: SyncDirection) => void;
  onToggleAuto: () => void;
  onFetchPreview: () => void;
}

export function SyncOperations({
  form, configured, syncing,
  masterKeyForSync, setMasterKeyForSync,
  lastResult, preview, loading,
  onSync, onToggleAuto, onFetchPreview,
}: SyncOperationsProps) {
  if (!configured) return null;

  return (
    <div
      className="rounded-lg p-4 mb-3"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        手动同步 · {FREQUENCY_BADGE(form.sync_frequency)}
      </h3>
      <p className="text-[11px] mb-3" style={{ color: 'var(--text-muted)' }}>
        同步需要主密钥用于解密 webdav password 和 bundle 整体加密层。
        自动同步 (周一 10:30) 在 master_key 未解锁时会被跳过。
      </p>
      <label className="flex flex-col gap-1 mb-3">
        <span style={{ color: 'var(--text-muted)' }}>主密钥 (本次同步用)</span>
        <input
          type="password"
          value={masterKeyForSync}
          onChange={e => setMasterKeyForSync(e.target.value)}
          placeholder="≥ 8 位"
          className="px-2 py-1.5 rounded"
          style={{
            background: 'var(--surface-2)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-subtle)',
          }}
        />
      </label>
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => onSync('push')}
          disabled={syncing !== null}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: syncing ? 0.6 : 1 }}
        >
          <Icon size={12}>
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </Icon>
          {syncing === 'push' ? '推送中…' : '推送 (本机 → 远端)'}
        </button>
        <button
          onClick={() => onSync('pull')}
          disabled={syncing !== null}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: syncing ? 0.6 : 1 }}
        >
          <Icon size={12}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          {syncing === 'pull' ? '拉取中…' : '拉取 (远端 → 本机)'}
        </button>
        <button
          onClick={() => onSync('bidirectional')}
          disabled={syncing !== null}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: syncing ? 0.6 : 1 }}
        >
          <Icon size={12}>
            <polyline points="17 1 21 5 17 9" />
            <path d="M3 11V9a4 4 0 0 1 4-4h14" />
            <polyline points="7 23 3 19 7 15" />
            <path d="M21 13v2a4 4 0 0 1-4 4H3" />
          </Icon>
          {syncing === 'bidirectional' ? '同步中…' : '双向同步'}
        </button>
        <button
          onClick={onFetchPreview}
          disabled={loading}
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          {loading ? '…' : '预览本地 bundle'}
        </button>
        <button
          onClick={onToggleAuto}
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          {form.auto_sync_enabled ? '关闭自动' : '开启自动'}
        </button>
      </div>

      {lastResult && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: lastResult.status === 'success'
              ? 'color-mix(in srgb, var(--color-success) 10%, transparent)'
              : 'color-mix(in srgb, var(--color-error) 10%, transparent)',
            color: lastResult.status === 'success' ? 'var(--color-success)' : 'var(--color-error)',
            border: `1px solid ${lastResult.status === 'success' ? 'color-mix(in srgb, var(--color-success) 30%, transparent)' : 'color-mix(in srgb, var(--color-error) 30%, transparent)'}`,
          }}
        >
          {lastResult.status === 'success' ? '✓' : '✗'} {lastResult.direction} 成功 ·
          同步 {lastResult.records_count ?? 0} 条
          {lastResult.conflict_count != null && lastResult.conflict_count > 0 && (
            <> · 冲突 {lastResult.conflict_count}</>
          )}
          {lastResult.message && <div>{lastResult.message}</div>}
        </div>
      )}

      {preview && (
        <div className="mt-3 text-[11px] flex flex-wrap gap-2"
             style={{ color: 'var(--text-muted)' }}>
          <span>本机 bundle:</span>
          {Object.entries(preview.record_counts).map(([k, v]) => (
            <span
              key={k}
              className="px-1.5 py-0.5 rounded"
              style={{
                background: 'var(--surface-2)',
                color: 'var(--text-primary)',
              }}
            >
              {k}: {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
