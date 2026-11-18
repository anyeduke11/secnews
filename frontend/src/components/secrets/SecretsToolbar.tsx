/**
 * secrets/SecretsToolbar — 从 secrets/SecretsPage.tsx 拆出的头部右侧操作区 (B6-a 纯搬迁, 无行为变更)。
 * 职责: 密钥条数 + 导入 / 导出 / 新增 按钮; 状态与 hook 动作由 SecretsPage 传入。
 */
import type { Dispatch, SetStateAction } from 'react';
import { SecretItem } from '../../types';
import type { UseSecretsReturn } from '../../hooks/useSecrets';

interface SecretsToolbarProps {
  total: number;
  setup: boolean;
  showAddForm: boolean;
  editing: SecretItem | null;
  setPromptRequest: (req: null | {
    title: string;
    hint?: string;
    submitLabel?: string;
    onSubmit: (mk: string) => void | Promise<void>;
  }) => void;
  setEditing: (item: SecretItem | null) => void;
  setShowAddForm: Dispatch<SetStateAction<boolean>>;
  importSecrets: UseSecretsReturn['importSecrets'];
  exportSecrets: UseSecretsReturn['exportSecrets'];
  refreshList: UseSecretsReturn['refreshList'];
}

export function SecretsToolbar({
  total,
  setup,
  showAddForm,
  editing,
  setPromptRequest,
  setEditing,
  setShowAddForm,
  importSecrets,
  exportSecrets,
  refreshList,
}: SecretsToolbarProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
        共 {total} 条
      </span>
      {setup && (
        <button
          onClick={async () => {
            if (!window.confirm('导入会更新同名 secret, 确认继续?')) return;
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'application/json,application/octet-stream,.json';
            input.onchange = async (e: any) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setPromptRequest({
                title: '导入加密 JSON',
                hint: '请输入主密钥以解密',
                submitLabel: '导入',
                onSubmit: async (mk) => {
                  setPromptRequest(null);
                  try {
                    const result = await importSecrets(file, mk);
                    window.alert(
                      `导入完成: 新增 ${result.inserted}, 更新 ${result.updated}, 失败 ${result.failures.length}`
                    );
                    await refreshList();
                  } catch (err: any) {
                    window.alert(`导入失败: ${err?.message || err}`);
                  }
                },
              });
            };
            input.click();
          }}
          className="btn-ghost px-3 py-1.5 text-xs"
          title="导入加密 JSON"
        >
          导入
        </button>
      )}
      {setup && (
        <button
          onClick={async () => {
            setPromptRequest({
              title: '导出加密 JSON',
              hint: '主密钥不存 DB, 丢失则无法解密。导出文件用此密钥加密。',
              submitLabel: '导出',
              onSubmit: async (mk) => {
                setPromptRequest(null);
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
              },
            });
          }}
          className="btn-ghost px-3 py-1.5 text-xs"
          title="导出加密 JSON (整个文件用 master_key 加密)"
        >
          导出
        </button>
      )}
      {setup && (
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
  );
}