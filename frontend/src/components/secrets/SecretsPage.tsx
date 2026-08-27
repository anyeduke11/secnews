/**
 * secrets/SecretsPage — 密钥管理页主入口 / 薄壳。
 *
 * 拆自原 SecretsPage.tsx (794 行 → 8 文件, 每文件 ≤ 400 行)。
 * 本文件仅做组合: 页面级状态 (表单开关/编辑对象/模态开关/倒计时) +
 * 头部操作 + 列表 + 子组件 (StatusBar/SecretCardView/AddOrEditForm/模态)。
 *
 * API 保持向后兼容: export function SecretsPage({ onBack })
 * (App.tsx lazy import: import('./components/secrets/SecretsPage').then(m => ({ default: m.SecretsPage })))
 */
import { useState, useEffect } from 'react';
import { useSecrets } from '../../hooks/useSecrets';
import { SecretItem } from '../../types';
import { Icon } from '../Icon';
import { StatusBar } from './StatusBar';
import { SecretCardView } from './SecretCardView';
import { AddOrEditForm } from './AddOrEditForm';
import { SetupModal } from './SetupModal';
import { UnlockModal } from './UnlockModal';
import type { SecretsPageProps } from './types';

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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2">
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
          <h2 className="text-base font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </Icon>
            密钥管理
          </h2>
          <span className="hidden sm:inline text-xs" style={{ color: 'var(--text-muted)' }}>
            LLM API Key · 30 分钟解锁
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
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
                const mk = window.prompt('复制明文需验证主密钥, 请输入:');
                if (!mk) return;
                try {
                  const r = await reveal(item.id, mk);
                  await navigator.clipboard.writeText(r.api_key);
                  window.alert(`已复制到剪贴板`);
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
