import React, { useState, useEffect } from 'react';
import type { SkillConfig, SecretItem } from '../types';

interface SkillConfigDialogProps {
  skill_id: number | null;
  onClose: () => void;
  onSaved?: () => void;
}

const SKILL_LABELS: Record<string, string> = {
  'baoyu-post-to-wechat': '微信发布',
  'baoyu-post-to-x': 'X 发布',
  'baoyu-post-to-weibo': '微博发布',
  'baoyu-slide-deck': '幻灯片',
  'baoyu-infographic': '信息图',
  'baoyu-cover-image': '封面图',
  'baoyu-translate': '翻译',
  'baoyu-markdown-to-html': 'MD转HTML',
  'baoyu-xhs-images': '小红书图',
  'baoyu-youtube-transcript': 'YT字幕',
  'baoyu-url-to-markdown': 'URL转MD',
  'baoyu-image-gen': 'AI绘图',
  'baoyu-compress-image': '图片压缩',
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

export function SkillConfigDialog({ skill_id, onClose, onSaved }: SkillConfigDialogProps) {
  const [skill, setSkill] = useState<SkillConfig | null>(null);
  const [secrets, setSecrets] = useState<SecretItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const [secretId, setSecretId] = useState<number | null>(null);
  const [modelOverride, setModelOverride] = useState('');
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (skill_id == null) return;
    setLoading(true);
    setError(null);
    setToast(null);

    Promise.all([
      fetch('/api/knowledge/skills').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
      fetch('/api/secrets').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
    ])
      .then(([skillsData, secretsData]) => {
        const found: SkillConfig | undefined = (skillsData.skills || []).find(
          (s: SkillConfig) => s.id === skill_id
        );
        if (!found) {
          setError('未找到 skill 配置');
          setLoading(false);
          return;
        }
        setSkill(found);
        setSecrets(secretsData.items || []);
        setSecretId(found.secret_id);
        setModelOverride(found.model_override || '');
        setEnabled(found.enabled);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, [skill_id]);

  if (skill_id == null) return null;

  const showToast = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 2500);
  };

  const handleSave = () => {
    if (skill_id == null || !skill) return;
    setSaving(true);
    const body: Record<string, unknown> = {
      secret_id: secretId,
      model_override: modelOverride.trim() || null,
      enabled,
    };
    fetch(`/api/knowledge/skills/${skill_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        showToast('ok', '已保存');
        onSaved?.();
        setTimeout(() => onClose(), 600);
      })
      .catch(e => {
        showToast('err', `保存失败: ${e?.message || String(e)}`);
      })
      .finally(() => setSaving(false));
  };

  const label = skill ? (SKILL_LABELS[skill.skill_name] || skill.skill_name) : '';

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
            ⚙ Skill 配置
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-0.5 text-xs" aria-label="关闭">
            ✕
          </button>
        </div>

        {loading && (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            加载中…
          </p>
        )}

        {error && (
          <div
            className="rounded-[var(--radius-sm)] p-2.5 mb-3 text-xs"
            style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)', border: '1px solid var(--color-error)', color: 'var(--color-error)' }}
          >
            {error}
          </div>
        )}

        {skill && !loading && (
          <div className="space-y-3">
            {/* Skill 名称 */}
            <div>
              <label style={labelStyle}>Skill</label>
              <div
                className="rounded-[var(--radius-sm)] px-2 py-1.5 text-xs"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
              >
                {label} <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>({skill.skill_name})</span>
              </div>
            </div>

            {/* Secret 绑定 */}
            <div>
              <label style={labelStyle}>LLM 密钥 (Secret)</label>
              <select
                style={inputStyle}
                value={secretId ?? ''}
                onChange={e => setSecretId(e.target.value === '' ? null : Number(e.target.value))}
              >
                <option value="">(无)</option>
                {secrets.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.unlocked ? '' : '(未解锁)'} · {s.model}
                  </option>
                ))}
              </select>
              {secrets.length === 0 && (
                <div className="text-[10px] mt-1" style={{ color: 'var(--color-warning)' }}>
                  暂无可用密钥，请先在密钥管理中添加
                </div>
              )}
            </div>

            {/* model_override */}
            <div>
              <label style={labelStyle}>model_override（可选）</label>
              <input
                type="text"
                style={inputStyle}
                value={modelOverride}
                onChange={e => setModelOverride(e.target.value)}
                placeholder="留空使用 secret 默认 model"
              />
            </div>

            {/* enabled */}
            <div>
              <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-primary)' }}>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={e => setEnabled(e.target.checked)}
                  style={{ accentColor: 'var(--color-ai)' }}
                />
                启用此 skill
              </label>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-ghost px-3 py-1.5 text-xs"
                style={{ color: 'var(--color-ai)', opacity: saving ? 0.6 : 1 }}
              >
                {saving ? '保存中…' : '保存'}
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
                  color: toast.kind === 'ok' ? 'var(--color-ai)' : 'var(--color-error)',
                }}>
                  {toast.kind === 'ok' ? '✓ ' : '✗ '}{toast.msg}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
