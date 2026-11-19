/**
 * secrets/SecretsPage — 密钥管理页主入口 / 薄壳。
 *
 * 拆自原 SecretsPage.tsx (794 行 → 8 文件, 每文件 ≤ 400 行)。
 * 本文件仅做组合: 页面级状态 (表单开关/编辑对象/模态开关/倒计时) +
 * 头部操作 + 列表 + 子组件 (StatusBar/SecretCardView/AddOrEditForm/模态)。
 *
 * API 保持向后兼容: export function SecretsPage({ onBack })
 * (App.tsx lazy import: import('./components/secrets/SecretsPage').then(m => ({ default: m.SecretsPage })))
 *
 * B6-a 二次拆分: 头部右侧导入/导出/新增按钮 → ./SecretsToolbar (纯搬迁)。
 */
import { useState, useEffect } from 'react';
import { useSecrets } from '../../hooks/useSecrets';
import { SecretItem } from '../../types';
import { Icon } from '../../primitives/Icon';
import { StatusBar } from './StatusBar';
import { SecretCardView } from './SecretCardView';
import { AddOrEditForm } from './AddOrEditForm';
import { SetupModal } from './SetupModal';
import { UnlockModal } from './UnlockModal';
import { MasterKeyPromptModal } from './MasterKeyPromptModal';
import { RotationBanner } from './RotationBanner';
import { SecretsToolbar } from './SecretsToolbar';
import type { SecretsPageProps } from './types';

export function SecretsPage({ onBack }: SecretsPageProps) {
  const {
    status, items, total, loading, error,
    refreshList,
    setupMasterKey, unlock, lock,
    add, update, remove,
    reveal, testConnection,
    exportSecrets, importSecrets,
  } = useSecrets();

  const [showAddForm, setShowAddForm] = useState(false);
  const [editing, setEditing] = useState<SecretItem | null>(null);
  const [unlockModalOpen, setUnlockModalOpen] = useState(false);
  const [setupModalOpen, setSetupModalOpen] = useState(false);
  // 三处 window.prompt 的统一替换: 单一 modal 复用, promptRequest 描述当前场景
  const [promptRequest, setPromptRequest] = useState<null | {
    title: string;
    hint?: string;
    submitLabel?: string;
    onSubmit: (mk: string) => void | Promise<void>;
  }>(null);

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
      {/* v0.7 Batch ⑨ B9-2: 主密钥轮换提醒 (年龄 >= remind_days 时显示) */}
      <div className="mb-3">
        <RotationBanner />
      </div>
      {/* 顶部标题区 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回"
            aria-label="返回"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回
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
        <SecretsToolbar
          total={total}
          setup={!!status?.setup}
          showAddForm={showAddForm}
          editing={editing}
          setPromptRequest={setPromptRequest}
          setEditing={setEditing}
          setShowAddForm={setShowAddForm}
          importSecrets={importSecrets}
          exportSecrets={exportSecrets}
          refreshList={refreshList}
        />
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
                setPromptRequest({
                  title: `复制明文 (${item.name})`,
                  hint: '复制明文 API key 需验证主密钥',
                  submitLabel: '复制',
                  onSubmit: async (mk) => {
                    setPromptRequest(null);
                    try {
                      const r = await reveal(item.id, mk);
                      await navigator.clipboard.writeText(r.api_key);
                      window.alert(`已复制到剪贴板`);
                    } catch (e: any) {
                      window.alert(`复制失败: ${e?.message || e}`);
                    }
                  },
                });
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

      {/* 模态: 主密钥 prompt (替换导入/导出/reveal 三处 window.prompt) */}
      {promptRequest && (
        <MasterKeyPromptModal
          title={promptRequest.title}
          hint={promptRequest.hint}
          submitLabel={promptRequest.submitLabel}
          onSubmit={promptRequest.onSubmit}
          onClose={() => setPromptRequest(null)}
        />
      )}
    </div>
  );
}