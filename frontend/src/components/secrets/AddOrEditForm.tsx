/**
 * secrets/AddOrEditForm — 新增/编辑密钥表单。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 AddOrEditForm (~460-605 行)。
 * 纯结构拆分: 表单状态与提交校验逻辑逐字迁移。
 */
import { useState } from 'react';
import { SecretItem } from '../../types';
import type { SecretFormRequest } from './types';

export function AddOrEditForm({
  editing, onSubmit, onCancel,
}: {
  editing: SecretItem | null;
  onSubmit: (req: SecretFormRequest) => Promise<void>;
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
    if (needsMasterKey && masterKey.length < 12) {
      setError('主密钥至少 12 字符 (用于加解密 api_key)');
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
        <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="名称 (e.g. 我的 DeepSeek)"
          className="tech-input px-2 py-1.5 text-xs w-full"
        />
        <input
          type="text"
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="模型 (e.g. deepseek-chat, gpt-4o)"
          className="tech-input px-2 py-1.5 text-xs w-full"
        />
      </div>
      <input
        type="text"
        value={baseUrl}
        onChange={e => setBaseUrl(e.target.value)}
        placeholder="base_url (e.g. https://api.deepseek.com/v1)"
        className="tech-input px-2 py-1.5 text-xs font-mono w-full"
      />
      <input
        type="password"
        value={apiKey}
        onChange={e => setApiKey(e.target.value)}
        placeholder={editing ? '新 api_key (留空则不修改)' : 'api_key 明文 (一次性, 提交后加密存储)'}
        className="tech-input px-2 py-1.5 text-xs font-mono w-full"
        autoComplete="new-password"
      />
      <input
        type="password"
        value={masterKey}
        onChange={e => setMasterKey(e.target.value)}
        placeholder={editing ? '主密钥 (仅修改 api_key 时必填, >= 12 字符)' : '主密钥 (>= 12 字符)'}
        className="tech-input px-2 py-1.5 text-xs font-mono w-full"
        autoComplete="new-password"
      />

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{
            backgroundColor: 'var(--text-primary)',
            color: 'var(--bg-primary)',
            borderColor: 'var(--text-primary)',
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
