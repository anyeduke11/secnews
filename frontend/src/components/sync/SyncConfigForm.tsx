/**
 * SyncConfigForm — WebDAV 配置表单 (输入字段)。
 *
 * Phase 1B: 拆自原 SyncBundleConfig.tsx 的上半段 (form section)。
 * Phase 6: 进一步把 actions/testMsg 拆到 SyncConfigActions, 本文件仅留表单字段。
 * 仅渲染, props-only; 状态与回调由 index.tsx 注入。
 */
import React from 'react';
import { SyncConfigActions } from './SyncConfigActions';
import type { BundleConfigForm, EffectiveRemoteInfo, SyncFrequency } from './types';

const FREQUENCY_LABEL: Record<SyncFrequency, string> = {
  manual: '仅手动',
  daily: '每日 10:30',
  weekly: '每周一 10:30',
  after_collect: '采集后自动',
};

interface SyncConfigFormProps {
  form: BundleConfigForm;
  setForm: React.Dispatch<React.SetStateAction<BundleConfigForm>>;
  configured: boolean;
  effective: EffectiveRemoteInfo | null;
  testing: boolean;
  saving: boolean;
  testMsg: { ok: boolean; message: string } | null;
  saveOk: string | null;
  actionError: string | null;
  showMasterKey: boolean;
  setShowMasterKey: React.Dispatch<React.SetStateAction<boolean>>;
  masterKeyFromCache: boolean;
  setMasterKeyFromCache: React.Dispatch<React.SetStateAction<boolean>>;
  onTest: () => void;
  onSave: () => void;
  onDelete: () => void;
}

export function SyncConfigForm({
  form, setForm, configured, effective,
  testing, saving, testMsg, saveOk, actionError,
  showMasterKey, setShowMasterKey, masterKeyFromCache, setMasterKeyFromCache,
  onTest, onSave, onDelete,
}: SyncConfigFormProps) {
  const canTest = Boolean(form.webdav_url && form.webdav_username && form.webdav_password);

  return (
    <div
      className="rounded-lg p-4 mb-3"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        WebDAV 配置
        {!configured && (
          <button
            onClick={() => setForm(f => ({ ...f, webdav_url: 'https://dav.jianguoyun.com/dav' }))}
            className="ml-2 text-[10px] px-2 py-0.5 rounded"
            style={{ background: 'color-mix(in srgb, var(--color-info) 15%, transparent)', color: 'var(--color-info)', border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)' }}
          >
            坚果云快速配置
          </button>
        )}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>WebDAV URL</span>
          <input
            type="text"
            value={form.webdav_url}
            onChange={e => setForm(f => ({ ...f, webdav_url: e.target.value }))}
            placeholder="https://dav.jianguoyun.com/dav"
            className="px-2 py-1.5 rounded"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
            }}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>用户名 (邮箱)</span>
          <input
            type="text"
            value={form.webdav_username}
            onChange={e => setForm(f => ({ ...f, webdav_username: e.target.value }))}
            placeholder="user@example.com"
            className="px-2 py-1.5 rounded"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
            }}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>
            WebDAV 应用密码
            {configured && <span className="ml-1" style={{ color: 'var(--color-success)' }}>· 已保存 (留空不修改)</span>}
          </span>
          <input
            type="password"
            value={form.webdav_password}
            onChange={e => setForm(f => ({ ...f, webdav_password: e.target.value }))}
            placeholder="应用专用密码 (不是登录密码)"
            className="px-2 py-1.5 rounded"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
            }}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>
            主密钥 (用于加密 webdav password)
            {masterKeyFromCache && (
              <span className="ml-1" style={{ color: 'var(--color-info)' }}>
                · ✓ 从 sessionStorage 自动填入
              </span>
            )}
          </span>
          <div className="flex gap-1">
            <input
              type={showMasterKey ? 'text' : 'password'}
              value={form.master_key}
              onChange={e => {
                setForm(f => ({ ...f, master_key: e.target.value }));
                if (masterKeyFromCache) setMasterKeyFromCache(false);
              }}
              placeholder="≥ 8 位 (跟首次 setup 一致)"
              className="flex-1 px-2 py-1.5 rounded"
              style={{
                background: 'var(--surface-2)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-subtle)',
              }}
            />
            <button
              type="button"
              onClick={() => setShowMasterKey(s => !s)}
              className="btn-ghost px-2 py-1.5 text-[10px]"
              aria-label="切换显示"
            >
              {showMasterKey ? '隐藏' : '显示'}
            </button>
          </div>
        </label>
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>远端目录 (config-YYYY-MM-DD.zip)</span>
          <input
            type="text"
            value={form.remote_path}
            onChange={e => setForm(f => ({ ...f, remote_path: e.target.value }))}
            placeholder="/hotspot/config.json"
            className="px-2 py-1.5 rounded"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
            }}
          />
          {effective?.effective_remote_path && (
            <div className="mt-1 flex flex-col gap-0.5">
              <span
                className="text-[10px] font-mono break-all"
                style={{ color: 'var(--text-muted)' }}
                title="每次同步将覆盖写入此 zip 路径"
              >
                实际: {effective.effective_remote_path}
              </span>
              {effective.effective_display_name && (
                <span
                  className="text-[10px]"
                  style={{ color: 'var(--text-muted)' }}
                  title="manifest 内的中文展示名,坚果云 web 端以 ASCII 路径显示"
                >
                  (内部标识: {effective.effective_display_name})
                </span>
              )}
            </div>
          )}
        </label>
        <label className="flex items-center gap-2 mt-5">
          <input
            type="checkbox"
            checked={form.auto_sync_enabled}
            onChange={e => setForm(f => ({ ...f, auto_sync_enabled: e.target.checked }))}
          />
          <span style={{ color: 'var(--text-primary)' }}>启用自动同步</span>
        </label>
        <label className="flex flex-col gap-1">
          <span style={{ color: 'var(--text-muted)' }}>同步频率</span>
          <select
            value={form.sync_frequency}
            onChange={e => setForm(f => ({ ...f, sync_frequency: e.target.value as SyncFrequency }))}
            className="px-2 py-1.5 rounded"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {(Object.entries(FREQUENCY_LABEL) as [SyncFrequency, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
      </div>

      <SyncConfigActions
        testing={testing}
        saving={saving}
        configured={configured}
        canTest={canTest}
        onTest={onTest}
        onSave={onSave}
        onDelete={onDelete}
        saveOk={saveOk}
        actionError={actionError}
        testMsg={testMsg}
      />
    </div>
  );
}
