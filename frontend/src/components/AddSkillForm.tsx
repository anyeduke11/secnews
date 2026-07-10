import React, { useState } from 'react';
import { SkillItem, SkillSource, SkillCreateRequest, SkillUpdateRequest } from '../types';

interface AddSkillFormProps {
  editing?: SkillItem | null;
  onSubmit: (req: SkillCreateRequest | SkillUpdateRequest) => Promise<void>;
  onCancel?: () => void;
}

const SOURCES: SkillSource[] = ['npx', 'uvx', 'curl', 'git', 'manual'];

export function AddSkillForm({ editing, onSubmit, onCancel }: AddSkillFormProps) {
  const [name, setName] = useState(editing?.name ?? '');
  const [url, setUrl] = useState(editing?.url ?? '');
  const [installCommand, setInstallCommand] = useState(editing?.install_command ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [source, setSource] = useState<SkillSource>(editing?.source ?? 'manual');
  const [tagsText, setTagsText] = useState((editing?.tags ?? []).join(', '));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !url.trim() || !installCommand.trim()) {
      setError('名称 / 链接 / 安装指令 均不能为空');
      return;
    }
    const tags = tagsText
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    setSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        url: url.trim(),
        install_command: installCommand.trim(),
        description: description.trim() || undefined,
        source,
        tags,
      });
      if (!editing) {
        // 清空表单
        setName('');
        setUrl('');
        setInstallCommand('');
        setDescription('');
        setTagsText('');
      }
    } catch (e: any) {
      setError(e?.message || '保存失败');
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
        {editing ? `编辑 Skill: ${editing.name}` : '新增 Skill'}
      </h3>

      {error && (
        <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'rgba(232, 93, 93, 0.15)', color: '#e85d5d' }}>
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="名称 (e.g. aihot)"
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <input
          type="text"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="链接 (e.g. https://github.com/...)"
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
      </div>

      <input
        type="text"
        value={installCommand}
        onChange={e => setInstallCommand(e.target.value)}
        placeholder="安装指令 (e.g. npx -y aihot@latest)"
        className="px-2 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
      />

      <input
        type="text"
        value={description}
        onChange={e => setDescription(e.target.value)}
        placeholder="简介 (可选)"
        className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <select
          value={source}
          onChange={e => setSource(e.target.value as SkillSource)}
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        >
          {SOURCES.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          type="text"
          value={tagsText}
          onChange={e => setTagsText(e.target.value)}
          placeholder="标签 (逗号分隔, e.g. ai, image)"
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{
            backgroundColor: 'var(--color-ai)',
            color: '#0a0d12',
            borderColor: 'var(--color-ai)',
            opacity: submitting ? 0.6 : 1,
            cursor: submitting ? 'wait' : 'pointer',
          }}
        >
          {submitting ? '保存中…' : editing ? '保存修改' : '+ 新增'}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="btn-ghost px-3 py-1.5 text-xs"
          >
            取消
          </button>
        )}
      </div>
    </form>
  );
}
