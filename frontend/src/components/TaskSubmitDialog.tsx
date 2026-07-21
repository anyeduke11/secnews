import React, { useState, useEffect } from 'react';
import type { TaskSubmitParams } from '../types';

interface TaskSubmitDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}

type TaskType = 'compile' | 'learn' | 'soul' | 'publish';

const TASK_TYPES: TaskType[] = ['compile', 'learn', 'soul', 'publish'];

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
  marginBottom: '2px',
  display: 'block',
};

export function TaskSubmitDialog({ open, onClose, onSubmitted }: TaskSubmitDialogProps) {
  const [taskType, setTaskType] = useState<TaskType>('compile');
  const [compileItemIds, setCompileItemIds] = useState('');
  const [learnWeek, setLearnWeek] = useState('');
  const [publishDraftId, setPublishDraftId] = useState('');
  const [publishPlatform, setPublishPlatform] = useState('');
  const [publishSkillName, setPublishSkillName] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // 打开弹窗时重置表单
  useEffect(() => {
    if (open) {
      setTaskType('compile');
      setCompileItemIds('');
      setLearnWeek('');
      setPublishDraftId('');
      setPublishPlatform('');
      setPublishSkillName('');
      setToast(null);
    }
  }, [open]);

  if (!open) return null;

  const flashToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const buildParams = (): Record<string, unknown> => {
    switch (taskType) {
      case 'compile': {
        const ids = compileItemIds
          .split(',')
          .map(s => s.trim())
          .filter(s => s.length > 0);
        return ids.length > 0 ? { item_ids: ids } : {};
      }
      case 'learn':
        return { week: learnWeek.trim() };
      case 'soul':
        return {};
      case 'publish':
        return {
          draft_id: publishDraftId.trim(),
          platform: publishPlatform.trim(),
          skill_name: publishSkillName.trim(),
        };
    }
  };

  const handleSubmit = () => {
    if (busy) return;
    setBusy(true);
    const body: TaskSubmitParams = {
      task_type: taskType,
      params: buildParams(),
    };
    fetch('/api/knowledge/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        return data;
      })
      .then(data => {
        const taskId = data?.task_id ?? data?.id ?? '';
        flashToast(`✓ 任务已创建 (task_id: ${taskId})`);
        onSubmitted?.();
        setTimeout(() => {
          onClose();
        }, 600);
      })
      .catch(e => {
        flashToast(`✗ 创建失败: ${e?.message || String(e)}`);
      })
      .finally(() => setBusy(false));
  };

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
          width: '420px',
          maxWidth: '90vw',
        }}
      >
        {/* 顶部 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            📝 提交任务
          </h3>
          <button
            onClick={onClose}
            className="btn-ghost px-2 py-0.5 text-xs"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        {/* task_type */}
        <div className="mb-3">
          <label style={labelStyle}>task_type</label>
          <select
            style={inputStyle}
            value={taskType}
            onChange={e => setTaskType(e.target.value as TaskType)}
          >
            {TASK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        {/* 动态参数 */}
        {taskType === 'compile' && (
          <div className="mb-3">
            <label style={labelStyle}>item_ids (逗号分隔，可选)</label>
            <input
              type="text"
              style={inputStyle}
              value={compileItemIds}
              onChange={e => setCompileItemIds(e.target.value)}
              placeholder="id1, id2, ..."
            />
          </div>
        )}

        {taskType === 'learn' && (
          <div className="mb-3">
            <label style={labelStyle}>week (如 2026-W29)</label>
            <input
              type="text"
              style={inputStyle}
              value={learnWeek}
              onChange={e => setLearnWeek(e.target.value)}
              placeholder="2026-W29"
            />
          </div>
        )}

        {taskType === 'soul' && (
          <p className="text-[10px] mb-3" style={{ color: 'var(--text-muted)' }}>
            soul 任务无参数
          </p>
        )}

        {taskType === 'publish' && (
          <>
            <div className="mb-3">
              <label style={labelStyle}>draft_id</label>
              <input
                type="text"
                style={inputStyle}
                value={publishDraftId}
                onChange={e => setPublishDraftId(e.target.value)}
                placeholder="123"
              />
            </div>
            <div className="mb-3">
              <label style={labelStyle}>platform</label>
              <input
                type="text"
                style={inputStyle}
                value={publishPlatform}
                onChange={e => setPublishPlatform(e.target.value)}
                placeholder="wechat / x / weibo"
              />
            </div>
            <div className="mb-3">
              <label style={labelStyle}>skill_name</label>
              <input
                type="text"
                style={inputStyle}
                value={publishSkillName}
                onChange={e => setPublishSkillName(e.target.value)}
                placeholder="baoyu-post-to-wechat"
              />
            </div>
          </>
        )}

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={handleSubmit}
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', opacity: busy ? 0.6 : 1 }}
          >
            {busy ? '提交中…' : '提交任务'}
          </button>
          <button
            onClick={onClose}
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--text-muted)', opacity: busy ? 0.6 : 1 }}
          >
            取消
          </button>
          {toast && (
            <span
              className="text-[10px] ml-auto"
              style={{ color: toast.startsWith('✓') ? 'var(--color-ai)' : 'var(--color-error)' }}
            >
              {toast}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
