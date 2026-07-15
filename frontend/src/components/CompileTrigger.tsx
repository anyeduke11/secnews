import React, { useState } from 'react';
import type { CompilePreview } from '../types';

interface CompileTriggerProps {
  onTaskCreated?: (task_id: number) => void;
}

export function CompileTrigger({ onTaskCreated }: CompileTriggerProps) {
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<CompilePreview | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const flashToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 2500);
  };

  const handleClick = () => {
    if (busy) return;
    setBusy(true);
    fetch('/api/knowledge/compile/preview')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: CompilePreview) => {
        setPreview(data);
        setBusy(false);
      })
      .catch(e => {
        flashToast(`✗ 失败: ${e?.message || String(e)}`, false);
        setBusy(false);
      });
  };

  const handleConfirm = () => {
    setBusy(true);
    fetch('/api/knowledge/compile', { method: 'POST' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: { task_id?: number; id?: number }) => {
        const tid = data.task_id ?? data.id ?? 0;
        flashToast(`✓ 编译任务已创建 (task_id: ${tid})`, true);
        if (tid && onTaskCreated) onTaskCreated(tid);
        else if (onTaskCreated) onTaskCreated(0);
        setPreview(null);
        setBusy(false);
      })
      .catch(e => {
        flashToast(`✗ 失败: ${e?.message || String(e)}`, false);
        setBusy(false);
      });
  };

  const handleCancel = () => {
    setPreview(null);
  };

  return (
    <div className="relative inline-flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={busy}
        className="btn-ghost px-3 py-1.5 text-xs"
        style={{
          color: 'var(--color-ai)',
          opacity: busy ? 0.6 : 1,
          cursor: busy ? 'wait' : undefined,
        }}
        title="预览并触发知识库编译任务"
        aria-label="编译知识库"
      >
        {busy ? '处理中…' : '编译知识库'}
      </button>

      {toast && (
        <span
          className="text-[10px] px-2 py-0.5 rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: 'var(--bg-hover)',
            color: toast.ok ? 'var(--color-ai)' : '#e85d5d',
          }}
        >
          {toast.msg}
        </span>
      )}

      {/* 确认弹窗 */}
      {preview && (
        <div
          onClick={handleCancel}
          style={{
            position: 'fixed', inset: 0, zIndex: 60,
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
              width: '380px',
              maxWidth: '90vw',
            }}
          >
            {preview.count === 0 ? (
              <div>
                <p className="text-xs mb-3" style={{ color: 'var(--text-primary)' }}>
                  没有需要编译的条目
                </p>
                <div className="flex justify-end">
                  <button
                    onClick={handleCancel}
                    className="btn-ghost px-3 py-1 text-xs"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    关闭
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <h3 className="text-sm font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                  编译确认
                </h3>
                <p className="text-xs mb-3" style={{ color: 'var(--text-primary)' }}>
                  检测到 <span style={{ color: 'var(--color-ai)', fontWeight: 600 }}>{preview.count}</span> 条需要编译的条目，是否触发编译?
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={handleCancel}
                    disabled={busy}
                    className="btn-ghost px-3 py-1 text-xs"
                    style={{ color: 'var(--text-muted)', opacity: busy ? 0.6 : 1 }}
                  >
                    取消
                  </button>
                  <button
                    onClick={handleConfirm}
                    disabled={busy}
                    className="btn-ghost px-3 py-1 text-xs"
                    style={{ color: 'var(--color-ai)', opacity: busy ? 0.6 : 1 }}
                  >
                    {busy ? '提交中…' : '确认编译'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
