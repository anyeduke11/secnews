/**
 * useSyncPage — SyncPage 状态管理 hook。
 *
 * Phase 1B: 从原 SyncPage.tsx 抽离所有 useState + handlers,
 * 保持 index.tsx 仅为薄壳 (composition)。
 *
 * 返回值:
 *   - state:  表单 + UI 状态
 *   - setters: 状态 setter
 *   - handlers: 业务回调 (test/save/delete/sync/toggle/resolve)
 *   - meta:  derived (configured, statusForPanel, effective, ...)
 */
import { useEffect, useRef, useState } from 'react';
import { useSync } from '../../hooks/useSync';
import type { SyncStatus } from './SyncStatusPanel';
import type { BundleConfigForm, ConflictInfo, SyncDirection, SyncFrequency } from './types';

const MASTER_KEY_CACHE_KEY = 'hotspot.sync.master_key';

export function useSyncPage() {
  const {
    status, history, preview, lastResult, loading, error,
    testConnection, upsertConfig, deleteConfig, setAutoSync,
    push, pull, bidirectional, fetchPreview,
  } = useSync();

  const [form, setForm] = useState<BundleConfigForm>({
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
  const [saveOk, setSaveOk] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<SyncDirection | null>(null);
  const [showMasterKey, setShowMasterKey] = useState(false);
  const [masterKeyForSync, setMasterKeyForSync] = useState('');
  const [masterKeyFromCache, setMasterKeyFromCache] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<ConflictInfo | null>(null);

  // 初始化表单 (从 status 读) —— 启动时立刻填回已保存配置
  const formInitRef = useRef(false);
  useEffect(() => {
    if (formInitRef.current) return;
    if (!status?.status.configured) return;
    formInitRef.current = true;
    setForm(f => ({
      ...f,
      webdav_url: status.status.webdav_url || f.webdav_url,
      webdav_username: status.status.webdav_username || f.webdav_username,
      remote_path: status.status.remote_path || f.remote_path,
      auto_sync_enabled: status.status.auto_sync_enabled ?? true,
      sync_frequency: status.status.auto_sync_interval_minutes === 1440
        ? 'daily' as SyncFrequency : 'weekly' as SyncFrequency,
    }));
  }, [status?.status.configured, status?.status.webdav_url,
      status?.status.webdav_username, status?.status.remote_path,
      status?.status.auto_sync_enabled, status?.status.auto_sync_interval_minutes]);

  // 兜底: status loading 时 500ms 后强制读一次
  useEffect(() => {
    const t = setTimeout(() => {
      if (formInitRef.current) return;
      if (status?.status.configured) {
        formInitRef.current = true;
        setForm(f => ({
          ...f,
          webdav_url: status.status.webdav_url || f.webdav_url,
          webdav_username: status.status.webdav_username || f.webdav_username,
          remote_path: status.status.remote_path || f.remote_path,
        }));
      }
    }, 500);
    return () => clearTimeout(t);
  }, [status]);

  // Phase 49: 启动时从 sessionStorage 恢复 master_key
  useEffect(() => {
    if (!status?.status.configured) return;
    const cached = window.sessionStorage.getItem(MASTER_KEY_CACHE_KEY);
    if (cached && cached.length >= 8 && !masterKeyForSync) {
      setMasterKeyForSync(cached);
      setMasterKeyFromCache(true);
    }
  }, [status?.status.configured]);

  const configured = status?.status.configured === true;

  const fetchConflicts = async () => {
    try {
      const r = await fetch('/api/sync/conflicts');
      if (r.ok) {
        const data: ConflictInfo = await r.json();
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
    if (!configured && !form.webdav_password) {
      setActionError('首次配置请填写 WebDAV 应用密码');
      return;
    }
    setSaving(true);
    setActionError(null);
    setSaveOk(null);
    try {
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
      if (form.master_key && form.master_key.length >= 8) {
        window.sessionStorage.setItem(MASTER_KEY_CACHE_KEY, form.master_key);
      }
      setForm(f => ({ ...f, webdav_password: '', master_key: '' }));
      setSaveOk('✓ WebDAV 配置已保存 (master_key 已缓存到 sessionStorage)');
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
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
  const handleSync = async (direction: SyncDirection) => {
    if (!masterKeyForSync || masterKeyForSync.length < 8) {
      setActionError('请先输入主密钥 (用于解密 webdav password 和 bundle)');
      return;
    }
    setSyncing(direction);
    setActionError(null);
    try {
      if (direction === 'push') await push(masterKeyForSync);
      else if (direction === 'pull') await pull(masterKeyForSync);
      else await bidirectional(masterKeyForSync);
      window.sessionStorage.setItem(MASTER_KEY_CACHE_KEY, masterKeyForSync);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(null);
    }
  };

  // 切换 auto
  const handleToggleAuto = async () => {
    try {
      await setAutoSync(!form.auto_sync_enabled);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  // 冲突裁决
  const handleResolveConflict = async (table: string, choice: 'local' | 'remote') => {
    try {
      await fetch('/api/sync/conflicts/auto-resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_type: table, choice }),
      });
    } catch {}
    fetchConflicts();
  };

  // 适配 status.status 到 SyncStatus 形状
  const statusForPanel: SyncStatus | null = status?.status
    ? {
        configured: status.status.configured,
        last_sync_at: status.status.last_sync_at ?? null,
        last_sync_status: status.status.last_sync_status ?? null,
        last_sync_direction: status.status.last_sync_direction ?? null,
        auto_sync_enabled: status.status.auto_sync_enabled,
        last_sync_error: status.status.last_sync_error ?? null,
        device_id: status.status.device_id ?? null,
      }
    : null;

  return {
    // state
    form, setForm,
    testMsg, testing, saving, saveOk,
    syncing, actionError, showMasterKey, setShowMasterKey,
    masterKeyForSync, setMasterKeyForSync,
    masterKeyFromCache, setMasterKeyFromCache,
    conflicts,
    history, preview, lastResult, loading, error,
    // derived
    configured, statusForPanel,
    effective: status?.status
      ? {
          effective_remote_path: status.status.effective_remote_path,
          effective_display_name: status.status.effective_display_name,
        }
      : null,
    // handlers
    handleTest, handleSave, handleDelete, handleSync, handleToggleAuto,
    handleResolveConflict, fetchPreview,
  };
}

export type SyncPageController = ReturnType<typeof useSyncPage>;
