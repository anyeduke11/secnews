import React, { useState } from 'react';
import type { SkillValidation, PublishTask } from '../types';

interface PublishDialogProps {
  draft_id: number | null;
  draft_title: string;
  onClose: () => void;
  onPublished?: (task_id: number) => void;
}

const PLATFORM_SKILL_MAP: Record<string, string> = {
  wechat: 'baoyu-post-to-wechat',
  x: 'baoyu-post-to-x',
  weibo: 'baoyu-post-to-weibo',
};

const PLATFORM_LABELS: { value: string; label: string }[] = [
  { value: 'wechat', label: '微信公众号' },
  { value: 'x', label: 'X' },
  { value: 'weibo', label: '微博' },
];

const REASON_MESSAGES: Record<string, string> = {
  no_secret_bound: '该 skill 未绑定 LLM 密钥，请先在 Skills 配置中绑定',
  skill_disabled: 'skill 已禁用',
  skill_not_found: 'skill 不存在',
};

const inputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '4px',
  display: 'block',
};

export function PublishDialog({ draft_id, draft_title, onClose, onPublished }: PublishDialogProps) {
  const [platform, setPlatform] = useState<string>('wechat');
  const [dryRun, setDryRun] = useState(false);
  const [tagsText, setTagsText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  if (draft_id == null) return null;

  const showToast = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const handlePublish = async () => {
    if (draft_id == null) return;
    const skill_name = PLATFORM_SKILL_MAP[platform];
    setSubmitting(true);
    setToast(null);

    try {
      // Step 1: validate skill
      const validateRes = await fetch(`/api/knowledge/skills/${encodeURIComponent(skill_name)}/validate`);
      const validateData: SkillValidation = await validateRes.json();

      if (!validateData.valid) {
        const reason = validateData.reason || '';
        showToast('err', REASON_MESSAGES[reason] || 'skill 校验失败');
        setSubmitting(false);
        return;
      }

      // Step 2: create publish task
      const tagsArray = tagsText
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0);

      const publishRes = await fetch(`/api/content/drafts/${draft_id}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform,
          skill_name,
          options: { dry_run: dryRun, tags: tagsArray },
        }),
      });

      if (!publishRes.ok) {
        const errData = await publishRes.json().catch(() => ({}));
        showToast('err', errData.detail || `HTTP ${publishRes.status}`);
        setSubmitting(false);
        return;
      }

      const data: PublishTask = await publishRes.json();
      showToast('ok', `发布任务已创建 (task_id: ${data.task_id})`);
      onPublished?.(data.task_id);
      setTimeout(() => onClose(), 800);
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="rounded-[var(--radius-md)] p-4"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          width: '480px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        {/* 顶部标题 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            🚀 发布草稿
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-0.5 text-xs" aria-label="关闭">
            ✕
          </button>
        </div>

        {/* 草稿标题 */}
        <div className="mb-3">
          <label style={labelStyle}>草稿</label>
          <div
            className="rounded-[var(--radius-sm)] px-2 py-1.5 text-xs"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
          >
            {draft_title || `#${draft_id}`}
          </div>
        </div>

        {/* 平台选择 */}
        <div className="mb-3">
          <label style={labelStyle}>平台</label>
          <div className="flex gap-3">
            {PLATFORM_LABELS.map(p => (
              <label
                key={p.value}
                className="flex items-center gap-1 text-xs cursor-pointer"
                style={{ color: platform === p.value ? 'var(--color-ai)' : 'var(--text-primary)' }}
              >
                <input
                  type="radio"
                  name="platform"
                  value={p.value}
                  checked={platform === p.value}
                  onChange={() => setPlatform(p.value)}
                  style={{ accentColor: 'var(--color-ai)' }}
                />
                {p.label}
              </label>
            ))}
          </div>
          <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
            skill: {PLATFORM_SKILL_MAP[platform]}
          </div>
        </div>

        {/* Dry run */}
        <div className="mb-3">
          <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-primary)' }}>
            <input
              type="checkbox"
              checked={dryRun}
              onChange={e => setDryRun(e.target.checked)}
              style={{ accentColor: 'var(--color-ai)' }}
            />
            Dry run（仅模拟，不实际发布）
          </label>
        </div>

        {/* 标签 */}
        <div className="mb-3">
          <label style={labelStyle}>标签（逗号分隔，可选）</label>
          <input
            type="text"
            style={inputStyle}
            value={tagsText}
            onChange={e => setTagsText(e.target.value)}
            placeholder="tag1, tag2, ..."
          />
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={handlePublish}
            disabled={submitting}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', opacity: submitting ? 0.6 : 1 }}
          >
            {submitting ? '发布中…' : '发布'}
          </button>
          <button
            onClick={onClose}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--text-muted)' }}
          >
            取消
          </button>
          {toast && (
            <span className="text-[10px] ml-auto" style={{
              color: toast.kind === 'ok' ? 'var(--color-ai)' : '#e85d5d',
            }}>
              {toast.kind === 'ok' ? '✓ ' : '✗ '}{toast.msg}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
