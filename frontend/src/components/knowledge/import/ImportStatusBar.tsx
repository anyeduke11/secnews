/**
 * ImportStatusBar — Cubox 同步进度条与结果 Toast (B5 从 KnowledgeImport 原样抽出)
 */
import { PHASE_LABELS, type ImportToastMsg } from './importModel';

/** 同步进度条 (syncing 为真时由容器条件渲染) */
export function ImportProgressBar({ phase, current, total, elapsed }: {
  phase: string;
  current: number;
  total: number;
  elapsed: number;
}) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3 text-xs"
      style={{
        backgroundColor: 'color-mix(in srgb, var(--area-accent) 8%, transparent)',
        border: '1px solid var(--area-accent)',
      }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="flex items-center gap-2" style={{ color: 'var(--area-accent)' }}>
          <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
          {PHASE_LABELS[phase] || phase}
          {phase === 'processing' && total > 0 && (
            <span style={{ color: 'var(--text-muted)' }}>
              ({current}/{total})
            </span>
          )}
        </span>
        <span style={{ color: 'var(--text-muted)' }}>{elapsed}s</span>
      </div>
      {phase === 'processing' && total > 0 ? (
        <div
          className="w-full h-1.5 overflow-hidden"
          style={{ backgroundColor: 'color-mix(in srgb, var(--area-accent) 15%, transparent)' }}
        >
          <div
            className="h-full transition-all duration-500 ease-out"
            style={{
              width: `${Math.min(100, Math.round((current / total) * 100))}%`,
              backgroundColor: 'var(--area-accent)',
            }}
          />
        </div>
      ) : (
        <div
          className="w-full h-1 overflow-hidden"
          style={{ backgroundColor: 'color-mix(in srgb, var(--area-accent) 15%, transparent)' }}
        >
          <div
            className="h-full animate-pulse"
            style={{ backgroundColor: 'var(--area-accent)', width: '40%' }}
          />
        </div>
      )}
    </div>
  );
}

/** 结果 Toast (toast 非空时由容器条件渲染) */
export function ImportToast({ toast }: { toast: ImportToastMsg }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-2.5 text-xs"
      style={{
        backgroundColor: toast.kind === 'ok'
          ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
          : 'color-mix(in srgb, var(--color-error) 12%, transparent)',
        border: `1px solid ${toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)'}`,
        color: toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
      }}
    >
      {toast.msg}
    </div>
  );
}
