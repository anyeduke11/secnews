/**
 * AddDependencyDialog — 添加依赖关系弹窗（source/target/dep_type 表单）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx 弹窗段。
 * props-only: 接收 onClose + onAdd 回调, 完全本地状态管理表单。
 */
import { useState } from 'react';
import { DepEntityType, DepType } from '../../../types/codegarden';
import { AddDependencyDialogProps } from './types';

export function AddDependencyDialog({ onClose, onAdd }: AddDependencyDialogProps) {
  const [sourceType, setSourceType] = useState<DepEntityType>('project');
  const [sourceId, setSourceId] = useState('');
  const [targetType, setTargetType] = useState<DepEntityType>('service');
  const [targetId, setTargetId] = useState('');
  const [depType, setDepType] = useState<DepType>('code');
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!sourceId.trim() || !targetId.trim()) {
      setErr('source_id 和 target_id 必填');
      return;
    }
    try {
      await onAdd({
        source_type: sourceType,
        source_id: sourceId.trim(),
        target_type: targetType,
        target_id: targetId.trim(),
        dep_type: depType,
      });
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-overlay)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-[var(--radius-md)] p-3"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            添加依赖关系
          </span>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">
            ✕
          </button>
        </div>
        <div className="space-y-2 text-[11px]">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Source 类型
              </label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as DepEntityType)}
                className="w-full text-[11px] px-2 py-1 rounded"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <option value="project">project</option>
                <option value="service">service</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Source ID
              </label>
              <input
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded font-mono"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                }}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Target 类型
              </label>
              <select
                value={targetType}
                onChange={(e) => setTargetType(e.target.value as DepEntityType)}
                className="w-full text-[11px] px-2 py-1 rounded"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <option value="project">project</option>
                <option value="service">service</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Target ID
              </label>
              <input
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded font-mono"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                }}
              />
            </div>
          </div>
          <div>
            <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              依赖类型
            </label>
            <select
              value={depType}
              onChange={(e) => setDepType(e.target.value as DepType)}
              className="w-full text-[11px] px-2 py-1 rounded"
              style={{
                backgroundColor: 'var(--bg-hover)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
              }}
            >
              <option value="code">code (代码)</option>
              <option value="service">service (服务)</option>
              <option value="data">data (数据)</option>
            </select>
          </div>
          {err && (
            <div className="text-[10px]" style={{ color: 'var(--color-error)' }}>
              {err}
            </div>
          )}
          <button
            onClick={submit}
            className="btn-ghost w-full py-1.5 text-[11px]"
            style={{ color: 'var(--color-ai)' }}
          >
            添加
          </button>
        </div>
      </div>
    </div>
  );
}
