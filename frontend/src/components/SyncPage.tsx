import React, { useEffect, useState } from 'react';
import { useSync } from '../hooks/useSync';
import { formatRelativeTime } from '../types';

interface SyncPageProps {
  onBack: () => void;
}

// Phase 49: master_key 客户端缓存 (sessionStorage, 关页即清, 不持久化到 disk)
const MASTER_KEY_CACHE_KEY = 'hotspot.sync.master_key';

function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function StatusBadge({ status }: { status?: string | null }) {
  const s = status || 'unknown';
  const colorMap: Record<string, { bg: string; fg: string; label: string }> = {
    success: { bg: 'rgba(0, 201, 106, 0.15)', fg: '#00c96a', label: '成功' },
    error: { bg: 'rgba(232, 93, 93, 0.15)', fg: '#e85d5d', label: '失败' },
    skipped: { bg: 'rgba(240, 201, 41, 0.15)', fg: '#f0c929', label: '跳过' },
    unknown: { bg: 'rgba(136, 136, 153, 0.15)', fg: '#888899', label: '未知' },
  };
  const c = colorMap[s] || colorMap.unknown;
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded"
      style={{ background: c.bg, color: c.fg }}
    >
      {c.label}
    </span>
  );
}

export function SyncPage({ onBack }: SyncPageProps) {
  const {
    status, history, preview, lastResult, loading, error,
    fetchStatus, fetchHistory, fetchPreview,
    testConnection, upsertConfig, deleteConfig, setAutoSync,
    push, pull, bidirectional,
  } = useSync();

  const [form, setForm] = useState({
    webdav_url: 'https://dav.jianguoyun.com/dav',
    webdav_username: '',
    webdav_password: '',
    master_key: '',
    remote_path: '/hotspot/config.json',
    auto_sync_enabled: true,
    sync_frequency: 'weekly',
  });
  const [testMsg, setTestMsg] = useState<{ ok: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState<string | null>(null);  // Phase 49: 保存成功提示
  const [syncing, setSyncing] = useState<'push' | 'pull' | 'bidirectional' | null>(null);
  const [showMasterKey, setShowMasterKey] = useState(false);
  const [masterKeyForSync, setMasterKeyForSync] = useState('');
  const [masterKeyFromCache, setMasterKeyFromCache] = useState(false);  // Phase 49: 标记 master_key 是否从 sessionStorage 自动填
  const [actionError, setActionError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<{conflicts: Record<string, number>; total: number} | null>(null);

  // 初始化表单 (从 status 读) —— 启动时立刻填回已保存配置
  useEffect(() => {
    if (status) {
      console.log('[SyncPage] useEffect 触发, status:', status.status);
    }
    if (!status) return;  // 加载中
    if (status.status.configured) {
      setForm(f => ({
        ...f,
        webdav_url: status.status.webdav_url || f.webdav_url,
        webdav_username: status.status.webdav_username || f.webdav_username,
        remote_path: status.status.remote_path || f.remote_path,
        auto_sync_enabled: status.status.auto_sync_enabled ?? true,
        sync_frequency: status.status.auto_sync_interval_minutes === 1440
          ? 'daily' : 'weekly',
      }));
    }
  }, [status?.status.configured, status?.status.webdav_url,
      status?.status.webdav_username, status?.status.remote_path,
      status?.status.auto_sync_enabled, status?.status.auto_sync_interval_minutes]);

  // Phase 49: 启动时从 sessionStorage 恢复 master_key, 配置就绪时自动填入同步框
  useEffect(() => {
    if (!status?.status.configured) return;
    const cached = window.sessionStorage.getItem(MASTER_KEY_CACHE_KEY);
    if (cached && cached.length >= 8 && !masterKeyForSync) {
      setMasterKeyForSync(cached);
      setMasterKeyFromCache(true);
    }
  }, [status?.status.configured]); // 仅在配置就绪时尝试一次

  const configured = status?.status.configured === true;

  const fetchConflicts = async () => {
    try {
      const r = await fetch('/api/sync/conflicts');
      if (r.ok) {
        const data = await r.json();
        setConflicts(data);
      }
    } catch {}
  };

  useEffect(() => {
    if (configured) fetchConflicts();
  }, [configured, lastResult]);

  // 测试连接
  const handleTest = async () => {
    setTestMsg(null);
    setTesting(true);
    try {
      const r = await testConnection({
        webdav_url: form.webdav_url,
        webdav_username: form.webdav_username,
        webdav_password: form.webdav_password,
      });
      setTestMsg({ ok: r.ok, message: r.message });
    } catch (e) {
      setTestMsg({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setTesting(false);
    }
  };

  // 保存配置
  const handleSave = async () => {
    if (!form.webdav_url || !form.webdav_username) {
      setActionError('请填写 URL / 用户名');
      return;
    }
    if (form.master_key.length < 8) {
      setActionError('主密钥至少 8 位 (≥ 8)');
      return;
    }
    // 已配置时 webdav_password 可留空 (后端保留原密文)
    if (!configured && !form.webdav_password) {
      setActionError('首次配置请填写 WebDAV 应用密码');
      return;
    }
    setSaving(true);
    setActionError(null);
    setSaveOk(null);
    try {
      // 已配置 + password 留空 → 后端走"保留原密文"路径, 不传 password 字段
      const payload: Record<string, unknown> = {
        webdav_url: form.webdav_url,
        webdav_username: form.webdav_username,
        master_key: form.master_key,
        remote_path: form.remote_path,
        auto_sync_enabled: form.auto_sync_enabled,
        sync_frequency: form.sync_frequency,
      };
      if (form.webdav_password) {
        payload.webdav_password = form.webdav_password;
      }
      await upsertConfig(payload as unknown as Parameters<typeof upsertConfig>[0]);
      // Phase 49: 保存后写 master_key 到 sessionStorage, 后续同步免重复输入
      if (form.master_key && form.master_key.length >= 8) {
        window.sessionStorage.setItem(MASTER_KEY_CACHE_KEY, form.master_key);
      }
      setForm(f => ({ ...f, webdav_password: '', master_key: '' }));
      setSaveOk('✓ WebDAV 配置已保存 (master_key 已缓存到 sessionStorage)');
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      // 401 主密钥错误 → 友好提示
      if (raw === '主密钥错误' || raw.includes('主密钥错误')) {
        setActionError('主密钥错误: 跟首次 setup 时输入的一致, 或 sessionStorage 已清空, 需重新输入');
      } else {
        setActionError(raw);
      }
    } finally {
      setSaving(false);
    }
  };

  // 删除配置
  const handleDelete = async () => {
    if (!window.confirm('确认删除同步配置? 历史记录会保留以便审计。')) return;
    try {
      await deleteConfig();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  // 同步
  const handleSync = async (direction: 'push' | 'pull' | 'bidirectional') => {
    if (!masterKeyForSync || masterKeyForSync.length < 8) {
      setActionError('请先输入主密钥 (用于解密 webdav password 和 bundle)');
      return;
    }
    setSyncing(direction);
    setActionError(null);
    // Phase 49: 同步成功后再回写 (避免错误密码污染缓存)
    try {
      if (direction === 'push') await push(masterKeyForSync);
      else if (direction === 'pull') await pull(masterKeyForSync);
      else await bidirectional(masterKeyForSync);
      // 同步成功后写 sessionStorage, 下次无需重输
      window.sessionStorage.setItem(MASTER_KEY_CACHE_KEY, masterKeyForSync);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(null);
    }
  };

  // 切换 auto
  const handleToggleAuto = async (enabled: boolean) => {
    try {
      await setAutoSync(enabled);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="sync-page">
      {/* 顶部 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            ☁️ 跨端配置同步
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            WebDAV / 坚果云 · {form.sync_frequency === 'weekly' ? '每周一 10:30' : form.sync_frequency === 'daily' ? '每日 10:30' : form.sync_frequency === 'after_collect' ? '采集后自动' : '手动同步'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {configured ? (
            <span
              className="text-[10px] px-2 py-0.5 rounded"
              style={{
                background: 'rgba(0, 201, 106, 0.15)',
                color: '#00c96a',
              }}
            >
              ● 已配置
            </span>
          ) : (
            <span
              className="text-[10px] px-2 py-0.5 rounded"
              style={{
                background: 'rgba(240, 201, 41, 0.15)',
                color: '#f0c929',
              }}
            >
              ● 未配置
            </span>
          )}
        </div>
      </div>

      {/* 状态卡 */}
      {configured && status?.status && (
        <div
          className="rounded-lg p-3 mb-3 text-xs space-y-1"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <span style={{ color: 'var(--text-muted)' }}>上次同步:</span>
            <span style={{ color: 'var(--text-primary)' }}>
              {status.status.last_sync_at
                ? formatRelativeTime(status.status.last_sync_at)
                : '从未'}
            </span>
            <StatusBadge status={status.status.last_sync_status} />
            {status.status.last_sync_direction && (
              <span style={{ color: 'var(--text-muted)' }}>
                ({status.status.last_sync_direction})
              </span>
            )}
            {status.status.auto_sync_enabled ? (
              <span style={{ color: '#00c96a' }}>· 自动同步开</span>
            ) : (
              <span style={{ color: '#888899' }}>· 自动同步关</span>
            )}
          </div>
          {status.status.last_sync_error && (
            <div className="text-[11px]" style={{ color: '#e85d5d' }}>
              错误: {status.status.last_sync_error}
            </div>
          )}
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            device_id: {status.status.device_id?.slice(0, 8)}…
          </div>
        </div>
      )}

      {/* 配置表单 */}
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
              style={{ background: 'rgba(6, 182, 212, 0.15)', color: '#06b6d4', border: '1px solid rgba(6, 182, 212, 0.3)' }}
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
              {configured && <span className="ml-1" style={{ color: '#00c96a' }}>· 已保存 (留空不修改)</span>}
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
                <span className="ml-1" style={{ color: '#06b6d4' }}>
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
            {status?.status?.effective_remote_path && (
              <div className="mt-1 flex flex-col gap-0.5">
                <span
                  className="text-[10px] font-mono break-all"
                  style={{ color: 'var(--text-muted)' }}
                  title="每次同步将覆盖写入此 zip 路径"
                >
                  实际: {status.status.effective_remote_path}
                </span>
                {status.status.effective_display_name && (
                  <span
                    className="text-[10px]"
                    style={{ color: 'var(--text-muted)' }}
                    title="manifest 内的中文展示名,坚果云 web 端以 ASCII 路径显示"
                  >
                    (内部标识: {status.status.effective_display_name})
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
              onChange={e => setForm(f => ({ ...f, sync_frequency: e.target.value }))}
              className="px-2 py-1.5 rounded"
              style={{
                background: 'var(--surface-2)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <option value="manual">仅手动</option>
              <option value="daily">每日 10:30</option>
              <option value="weekly">每周一 10:30</option>
              <option value="after_collect">采集后自动</option>
            </select>
          </label>
        </div>

        {saveOk && (
          <div
            className="mt-3 px-3 py-2 rounded text-[11px]"
            style={{
              background: 'rgba(0, 201, 106, 0.1)',
              color: '#00c96a',
              border: '1px solid rgba(0, 201, 106, 0.3)',
            }}
          >
            {saveOk}
          </div>
        )}

        {actionError && (
          <div
            className="mt-3 px-3 py-2 rounded text-[11px]"
            style={{
              background: 'rgba(232, 93, 93, 0.1)',
              color: '#e85d5d',
              border: '1px solid rgba(232, 93, 93, 0.3)',
            }}
          >
            ✗ {actionError}
          </div>
        )}

        <div className="flex gap-2 mt-3 flex-wrap">
          <button
            onClick={handleTest}
            disabled={testing || !form.webdav_url || !form.webdav_username || !form.webdav_password}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ opacity: testing ? 0.6 : 1 }}
          >
            <Icon size={12}>
              <polyline points="9 11 12 14 22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </Icon>
            {testing ? '测试中…' : '测试连接'}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ opacity: saving ? 0.6 : 1 }}
          >
            <Icon size={12}>
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
              <polyline points="17 21 17 13 7 13 7 21" />
              <polyline points="7 3 7 8 15 8" />
            </Icon>
            {saving ? '保存中…' : '保存配置'}
          </button>
          {configured && (
            <button
              onClick={handleDelete}
              className="btn-ghost px-3 py-1.5 text-xs"
              style={{ color: '#e85d5d' }}
            >
              <Icon size={12}>
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              </Icon>
              删除配置
            </button>
          )}
        </div>

        {testMsg && (
          <div
            className="mt-3 px-3 py-2 rounded text-[11px]"
            style={{
              background: testMsg.ok ? 'rgba(0, 201, 106, 0.1)' : 'rgba(232, 93, 93, 0.1)',
              color: testMsg.ok ? '#00c96a' : '#e85d5d',
              border: `1px solid ${testMsg.ok ? 'rgba(0, 201, 106, 0.3)' : 'rgba(232, 93, 93, 0.3)'}`,
            }}
          >
            {testMsg.ok ? '✓' : '✗'} {testMsg.message}
          </div>
        )}
      </div>

      {/* 同步操作 */}
      {configured && (
        <div
          className="rounded-lg p-4 mb-3"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            手动同步
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
              onClick={() => handleSync('push')}
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
              onClick={() => handleSync('pull')}
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
              onClick={() => handleSync('bidirectional')}
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
              onClick={fetchPreview}
              disabled={loading}
              className="btn-ghost px-3 py-1.5 text-xs"
            >
              {loading ? '…' : '预览本地 bundle'}
            </button>
            <button
              onClick={() => handleToggleAuto(!form.auto_sync_enabled)}
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
                  ? 'rgba(0, 201, 106, 0.1)'
                  : 'rgba(232, 93, 93, 0.1)',
                color: lastResult.status === 'success' ? '#00c96a' : '#e85d5d',
                border: `1px solid ${lastResult.status === 'success' ? 'rgba(0, 201, 106, 0.3)' : 'rgba(232, 93, 93, 0.3)'}`,
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
      )}

      {/* 冲突裁决 */}
      {configured && conflicts && conflicts.total > 0 && (
        <div
          className="rounded-lg p-4 mb-3"
          style={{
            background: 'rgba(240, 201, 41, 0.05)',
            border: '1px solid rgba(240, 201, 41, 0.3)',
          }}
        >
          <h3 className="text-sm font-semibold mb-2" style={{ color: '#f0c929' }}>
            同步冲突 ({conflicts.total} 项)
          </h3>
          <p className="text-[11px] mb-2" style={{ color: 'var(--text-muted)' }}>
            以下表存在本地与远端冲突，默认保留较新的一方。您可逐条裁决。
          </p>
          <div className="space-y-1.5">
            {Object.entries(conflicts.conflicts).map(([table, count]) => (
              <div
                key={table}
                className="flex items-center justify-between text-xs px-2 py-1.5 rounded"
                style={{ background: 'var(--surface-2)' }}
              >
                <span style={{ color: 'var(--text-primary)' }}>{table}</span>
                <span style={{ color: '#f0c929' }}>{count} 项冲突</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] mt-2" style={{ color: 'var(--text-muted)' }}>
            当前冲突已自动按 updated_at 较新者保留。如需手动裁决，请通过 API /api/sync/conflicts/resolve 操作。
          </p>
        </div>
      )}

      {/* 历史 */}
      {history.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            同步历史 (最近 {history.length} 条)
          </h3>
          <div className="space-y-1.5">
            {history.map(h => (
              <div
                key={h.id}
                className="flex items-center gap-2 text-[11px] flex-wrap px-2 py-1.5 rounded"
                style={{ background: 'var(--surface-2)' }}
              >
                <StatusBadge status={h.status} />
                <span style={{ color: 'var(--text-primary)' }}>{h.direction}</span>
                <span style={{ color: 'var(--text-muted)' }}>
                  {formatRelativeTime(h.started_at)}
                </span>
                {h.records_count != null && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {h.records_count} 条
                  </span>
                )}
                {(h.conflict_count ?? 0) > 0 && (
                  <span style={{ color: '#f0c929' }}>
                    冲突 {h.conflict_count}
                  </span>
                )}
                {h.error_message && (
                  <span style={{ color: '#e85d5d' }} className="truncate max-w-[400px]">
                    {h.error_message}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: 'rgba(232, 93, 93, 0.1)',
            color: '#e85d5d',
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
