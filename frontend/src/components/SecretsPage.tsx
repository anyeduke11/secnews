import React, { useState, useEffect } from 'react';
import { useSecrets } from '../hooks/useSecrets';
import { SecretItem } from '../types';

interface SecretsPageProps {
  onBack: () => void;
}

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

function formatRemaining(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function SecretsPage({ onBack }: SecretsPageProps) {
  const {
    status, items, total, loading, error,
    refreshStatus, refreshList,
    setupMasterKey, unlock, lock,
    add, update, remove,
    reveal, testConnection,
    exportSecrets, importSecrets,
  } = useSecrets();

  const [showAddForm, setShowAddForm] = useState(false);
  const [editing, setEditing] = useState<SecretItem | null>(null);
  const [unlockModalOpen, setUnlockModalOpen] = useState(false);
  const [setupModalOpen, setSetupModalOpen] = useState(false);

  // 倒计时显示 (前端估算, 每秒 tick)
  const [remaining, setRemaining] = useState<number>(0);
  useEffect(() => {
    setRemaining(status?.remaining_seconds ?? 0);
    if (!status?.unlocked) return;
    const t = window.setInterval(() => {
      setRemaining(prev => Math.max(0, prev - 1));
    }, 1000);
    return () => window.clearInterval(t);
  }, [status?.unlocked, status?.remaining_seconds]);

  return (
    <div className="secrets-page">
      {/* 顶部标题区 */}
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
            🔐 密钥管理
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            LLM API Key · 30 分钟解锁
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {total} 条
          </span>
          {status?.setup && (
            <button
              onClick={async () => {
                if (!window.confirm('导入会更新同名 secret, 确认继续?')) return;
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'application/json,application/octet-stream,.json';
                input.onchange = async (e: any) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const mk = window.prompt('请输入主密钥 (master_key)');
                  if (!mk) return;
                  try {
                    const result = await importSecrets(file, mk);
                    window.alert(
                      `导入完成: 新增 ${result.inserted}, 更新 ${result.updated}, 失败 ${result.failures.length}`
                    );
                    await refreshList();
                  } catch (err: any) {
                    window.alert(`导入失败: ${err?.message || err}`);
                  }
                };
                input.click();
              }}
              className="btn-ghost px-3 py-1.5 text-xs"
              title="导入加密 JSON"
            >
              导入
            </button>
          )}
          {status?.setup && (
            <button
              onClick={async () => {
                const mk = window.prompt('请输入主密钥以导出 (主密钥不存 DB, 丢失则无法解密)');
                if (!mk) return;
                try {
                  const blob = await exportSecrets(mk);
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `secrets-export-${Math.floor(Date.now() / 1000)}.json`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                } catch (err: any) {
                  window.alert(`导出失败: ${err?.message || err}`);
                }
              }}
              className="btn-ghost px-3 py-1.5 text-xs"
              title="导出加密 JSON (整个文件用 master_key 加密)"
            >
              导出
            </button>
          )}
          {status?.setup && (
            <button
              onClick={() => {
                setEditing(null);
                setShowAddForm(s => !s);
              }}
              className="btn-ghost px-3 py-1.5 text-xs"
              style={{
                backgroundColor: showAddForm && !editing ? 'var(--bg-hover)' : undefined,
                color: 'var(--color-ai)',
                borderColor: 'var(--color-ai)',
              }}
            >
              {showAddForm && !editing ? '收起表单' : '+ 新增'}
            </button>
          )}
        </div>
      </div>

      {/* 状态条 */}
      <StatusBar
        status={status}
        remaining={remaining}
        onSetupClick={() => setSetupModalOpen(true)}
        onUnlockClick={() => setUnlockModalOpen(true)}
        onLockClick={async () => {
          if (window.confirm('立即锁定? 30 分钟内已复制的明文仍可用 (浏览器剪贴板)。')) {
            await lock();
          }
        }}
      />

      {/* 错误条 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          {error}
        </div>
      )}

      {/* 新增 / 编辑表单 */}
      {showAddForm && status?.setup && (
        <div className="mb-3">
          <AddOrEditForm
            editing={editing}
            unlocked={status.unlocked}
            onSubmit={async req => {
              if (editing) {
                await update(editing.id, req);
                setEditing(null);
                setShowAddForm(false);
              } else {
                await add(req);
              }
            }}
            onCancel={editing ? () => { setEditing(null); setShowAddForm(false); } : undefined}
          />
        </div>
      )}

      {/* 列表 */}
      {loading && items.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          加载中…
        </p>
      ) : !status?.setup ? (
        <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          请先点击「首次设置主密钥」初始化。
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          暂无密钥, 点击「+ 新增」开始管理
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {items.map(item => (
            <SecretCardView
              key={item.id}
              item={item}
              onEdit={() => { setEditing(item); setShowAddForm(true); }}
              onDelete={async () => {
                if (window.confirm(`确定删除「${item.name}」?`)) {
                  try { await remove(item.id); } catch (e: any) { window.alert(`删除失败: ${e?.message || e}`); }
                }
              }}
              onCopy={async () => {
                try {
                  const r = await reveal(item.id);
                  await navigator.clipboard.writeText(r.api_key);
                  window.alert(`已复制 (明文仅在内存, 30 分钟后过期)`);
                } catch (e: any) {
                  window.alert(`复制失败: ${e?.message || e}`);
                }
              }}
              onTest={async () => {
                try {
                  const r = await testConnection(item.id);
                  if (r.ok) {
                    const m = r.model_count != null ? ` (${r.model_count} models)` : '';
                    const w = r.warning ? ` · ${r.warning}` : '';
                    window.alert(`✓ 连通 (${r.latency_ms}ms, HTTP ${r.status_code})${m}${w}`);
                  } else {
                    window.alert(`✗ 失败: ${r.error || '未知错误'}`);
                  }
                } catch (e: any) {
                  window.alert(`测试失败: ${e?.message || e}`);
                }
              }}
            />
          ))}
        </div>
      )}

      {/* 模态: 首次设置主密钥 */}
      {setupModalOpen && (
        <SetupModal
          onSubmit={async mk => {
            await setupMasterKey(mk);
            setSetupModalOpen(false);
          }}
          onClose={() => setSetupModalOpen(false)}
        />
      )}

      {/* 模态: 解锁 */}
      {unlockModalOpen && (
        <UnlockModal
          onSubmit={async mk => {
            await unlock(mk);
            setUnlockModalOpen(false);
          }}
          onClose={() => setUnlockModalOpen(false)}
        />
      )}
    </div>
  );
}

// ===========================================================================
// 子组件
// ===========================================================================
function StatusBar({
  status, remaining, onSetupClick, onUnlockClick, onLockClick,
}: {
  status: ReturnType<typeof useSecrets>['status'];
  remaining: number;
  onSetupClick: () => void;
  onUnlockClick: () => void;
  onLockClick: () => void;
}) {
  if (!status) {
    return (
      <div className="rounded-[var(--radius-md)] p-3 mb-3 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
        状态加载中…
      </div>
    );
  }

  if (!status.setup) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
        style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-error) 40%, transparent)' }}
      >
        <div>
          <p style={{ color: 'var(--text-primary)' }}>🔒 主密钥未初始化</p>
          <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
            请先设置主密钥 (master key, &gt;= 8 字符)。<b>主密钥不存数据库</b>, 丢失后该密钥下所有 secret 永久不可解密。
          </p>
        </div>
        <button
          onClick={onSetupClick}
          className="btn-ghost px-3 py-1.5 text-xs shrink-0"
          style={{ backgroundColor: 'var(--color-ai)', color: 'var(--text-on-light)', borderColor: 'var(--color-ai)' }}
        >
          首次设置主密钥
        </button>
      </div>
    );
  }

  if (!status.unlocked) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
        style={{ backgroundColor: 'color-mix(in srgb, var(--color-warning) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-warning) 40%, transparent)' }}
      >
        <div>
          <p style={{ color: 'var(--text-primary)' }}>🔒 已锁定</p>
          <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
            输入主密钥可解锁 30 分钟, 期间可一键复制明文 API key。
          </p>
        </div>
        <button
          onClick={onUnlockClick}
          className="btn-ghost px-3 py-1.5 text-xs shrink-0"
          style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
        >
          🔑 解锁
        </button>
      </div>
    );
  }

  return (
    <div
      className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
      style={{ backgroundColor: 'color-mix(in srgb, var(--color-success) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-success) 40%, transparent)' }}
    >
      <div>
        <p style={{ color: 'var(--text-primary)' }}>
          🔓 已解锁 <span className="font-mono tabular-nums" style={{ color: 'var(--color-ai)' }}>{formatRemaining(remaining)}</span>
          <span style={{ color: 'var(--text-muted)' }}> 后过期</span>
        </p>
        <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
          到期后清空内存中的明文, 重新输入主密钥可继续使用。
        </p>
      </div>
      <button
        onClick={onLockClick}
        className="btn-ghost px-3 py-1.5 text-xs shrink-0"
        style={{ color: 'var(--color-error)', borderColor: 'var(--color-error)' }}
      >
        立即锁定
      </button>
    </div>
  );
}

function SecretCardView({
  item, onEdit, onDelete, onCopy, onTest,
}: {
  item: SecretItem;
  onEdit: () => void;
  onDelete: () => void;
  onCopy: () => void;
  onTest: () => void;
}) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3 flex flex-col gap-2"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <h3 className="text-sm font-bold truncate" style={{ color: 'var(--text-primary)' }} title={item.name}>
            {item.name}
          </h3>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded-[var(--radius-sm)] shrink-0"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}
          >
            {item.model}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={onEdit} className="btn-ghost px-1.5 py-0.5 text-[10px]" title="编辑" aria-label="编辑">
            <Icon>
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </Icon>
          </button>
          <button onClick={onDelete} className="btn-ghost px-1.5 py-0.5 text-[10px]" title="删除" aria-label="删除" style={{ color: 'var(--color-error)' }}>
            <Icon>
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
            </Icon>
          </button>
        </div>
      </div>

      <a
        href={item.base_url}
        target="_blank"
        rel="noreferrer"
        className="text-[11px] truncate block hover:underline"
        style={{ color: 'var(--color-ai)' }}
        title={item.base_url}
      >
        🔗 {item.base_url}
      </a>

      <div
        className="px-2 py-1.5 rounded-[var(--radius-sm)] font-mono text-[11px] overflow-x-auto"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}
      >
        {item.api_key_masked}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          onClick={onCopy}
          disabled={!item.unlocked}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{
            opacity: item.unlocked ? 1 : 0.5,
            cursor: item.unlocked ? 'pointer' : 'not-allowed',
            color: item.unlocked ? 'var(--color-ai)' : undefined,
            borderColor: item.unlocked ? 'var(--color-ai)' : undefined,
          }}
          title={item.unlocked ? '复制明文到剪贴板' : '未解锁, 无法复制'}
        >
          📋 复制
        </button>
        <button
          onClick={onTest}
          disabled={!item.unlocked}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{ opacity: item.unlocked ? 1 : 0.5, cursor: item.unlocked ? 'pointer' : 'not-allowed' }}
          title="测试连通性"
        >
          ⚡ 测试
        </button>
      </div>
    </div>
  );
}

function AddOrEditForm({
  editing, unlocked, onSubmit, onCancel,
}: {
  editing: SecretItem | null;
  unlocked: boolean;
  onSubmit: (req: {
    name: string; model: string; base_url: string; api_key: string; master_key: string;
  }) => Promise<void>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? '');
  const [model, setModel] = useState(editing?.model ?? '');
  const [baseUrl, setBaseUrl] = useState(editing?.base_url ?? '');
  const [apiKey, setApiKey] = useState('');
  const [masterKey, setMasterKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const needsMasterKey = !editing || (editing && apiKey.trim().length > 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !model.trim() || !baseUrl.trim()) {
      setError('名称 / 模型 / base_url 均不能为空');
      return;
    }
    if (needsMasterKey && masterKey.length < 8) {
      setError('主密钥至少 8 字符 (用于加解密 api_key)');
      return;
    }
    setSubmitting(true);
    try {
      const req: any = {
        name: name.trim(),
        model: model.trim(),
        base_url: baseUrl.trim(),
      };
      if (apiKey.trim()) {
        req.api_key = apiKey.trim();
        req.master_key = masterKey;
      } else if (!editing) {
        // 新增必须有 api_key + master_key
        setError('新增时必须填 api_key');
        setSubmitting(false);
        return;
      } else if (editing) {
        // 编辑, 但未改 api_key — 也允许 (允许改 name/model/base_url 不传 master_key)
      }
      if (!editing) req.master_key = masterKey;  // 新增时强制 master_key
      await onSubmit(req);
      if (!editing) {
        setName(''); setModel(''); setBaseUrl(''); setApiKey(''); setMasterKey('');
      } else {
        setApiKey(''); setMasterKey('');
      }
    } catch (err: any) {
      setError(err?.message || '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[var(--radius-md)] p-3 flex flex-col gap-2"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>
        {editing ? `编辑密钥: ${editing.name}` : '新增密钥'}
      </h3>

      {error && (
        <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 15%, transparent)', color: 'var(--color-error)' }}>
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="名称 (e.g. 我的 DeepSeek)"
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <input
          type="text"
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="模型 (e.g. deepseek-chat, gpt-4o)"
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
      </div>
      <input
        type="text"
        value={baseUrl}
        onChange={e => setBaseUrl(e.target.value)}
        placeholder="base_url (e.g. https://api.deepseek.com/v1)"
        className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
      />
      <input
        type="password"
        value={apiKey}
        onChange={e => setApiKey(e.target.value)}
        placeholder={editing ? '新 api_key (留空则不修改)' : 'api_key 明文 (一次性, 提交后加密存储)'}
        className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        autoComplete="new-password"
      />
      <input
        type="password"
        value={masterKey}
        onChange={e => setMasterKey(e.target.value)}
        placeholder={editing ? '主密钥 (仅修改 api_key 时必填, >= 8 字符)' : '主密钥 (>= 8 字符)'}
        className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        autoComplete="new-password"
      />

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{
            backgroundColor: 'var(--color-ai)',
            color: 'var(--text-on-light)',
            borderColor: 'var(--color-ai)',
            opacity: submitting ? 0.6 : 1,
            cursor: submitting ? 'wait' : 'pointer',
          }}
        >
          {submitting ? '保存中…' : editing ? '保存修改' : '+ 新增'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        )}
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          api_key 在传输和落库前用 PBKDF2 + Fernet 加密
        </span>
      </div>
    </form>
  );
}

function UnlockModal({
  onSubmit, onClose,
}: {
  onSubmit: (mk: string) => Promise<void>;
  onClose: () => void;
}) {
  const [mk, setMk] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (mk.length < 8) {
      setErr('主密钥至少 8 字符');
      return;
    }
    setBusy(true);
    try {
      await onSubmit(mk);
    } catch (e: any) {
      setErr(e?.message || '解锁失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>🔑 解锁密钥</h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          输入主密钥, 解锁 30 分钟。期间可一键复制明文 API key, 过期自动锁定。
        </p>
        {err && (
          <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 15%, transparent)', color: 'var(--color-error)' }}>
            {err}
          </p>
        )}
        <input
          type="password"
          value={mk}
          onChange={e => setMk(e.target.value)}
          autoFocus
          autoComplete="new-password"
          placeholder="主密钥"
          className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              backgroundColor: 'var(--color-ai)',
              color: 'var(--text-on-light)',
              borderColor: 'var(--color-ai)',
              opacity: busy ? 0.6 : 1,
              cursor: busy ? 'wait' : 'pointer',
            }}
          >
            {busy ? '验证中…' : '解锁'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        </div>
      </form>
    </Modal>
  );
}

function SetupModal({
  onSubmit, onClose,
}: {
  onSubmit: (mk: string) => Promise<void>;
  onClose: () => void;
}) {
  const [mk, setMk] = useState('');
  const [mk2, setMk2] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (mk.length < 8) {
      setErr('主密钥至少 8 字符');
      return;
    }
    if (mk !== mk2) {
      setErr('两次输入不一致');
      return;
    }
    setBusy(true);
    try {
      await onSubmit(mk);
    } catch (e: any) {
      setErr(e?.message || '设置失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>🔒 首次设置主密钥</h3>
        <p className="text-xs" style={{ color: 'var(--color-error)' }}>
          ⚠️ <b>主密钥不存数据库, 一旦丢失, 该主密钥下所有 secret 永久不可解密, 且禁止重置</b>。
          请使用密码管理器保存或选一段你能记住的强密码。
        </p>
        {err && (
          <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 15%, transparent)', color: 'var(--color-error)' }}>
            {err}
          </p>
        )}
        <input
          type="password"
          value={mk}
          onChange={e => setMk(e.target.value)}
          autoFocus
          autoComplete="new-password"
          placeholder="主密钥 (>= 8 字符)"
          className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <input
          type="password"
          value={mk2}
          onChange={e => setMk2(e.target.value)}
          autoComplete="new-password"
          placeholder="再次输入主密钥"
          className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              backgroundColor: 'var(--color-ai)',
              color: 'var(--text-on-light)',
              borderColor: 'var(--color-ai)',
              opacity: busy ? 0.6 : 1,
              cursor: busy ? 'wait' : 'pointer',
            }}
          >
            {busy ? '设置中…' : '确认设置'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'var(--bg-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="rounded-[var(--radius-md)] p-4 w-[420px] max-w-[90vw]"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        {children}
      </div>
    </div>
  );
}
