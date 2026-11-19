/**
 * ModelPoolPanel 拆分零件 — 平台行 / 状态 chip / 路由档位常量
 *
 * 从 ModelPoolPanel.tsx 原样搬运, 仅 props 化; 行为 / DOM / 文案零变更。
 */
import type { PoolPlatform } from '../../api/settings';
import { StatusBadge } from '../../primitives/StatusBadge';

function PlatformChip({ p }: { p: PoolPlatform }) {
  if (!p.configured) {
    return <StatusBadge tone="neutral" dot>未配置</StatusBadge>;
  }
  if (p.available === true) {
    return <StatusBadge tone="ok" dot>可用 {p.model_count} 款模型</StatusBadge>;
  }
  if (p.available === false && p.error === 'no_key') {
    return <StatusBadge tone="neutral" dot>未配置</StatusBadge>;
  }
  if (p.available === false) {
    return <StatusBadge tone="risk" dot>{p.error?.startsWith('HTTP 40') ? '密钥无效' : '不可达'}</StatusBadge>;
  }
  return <StatusBadge tone="warn" dot blink>已配置 · 未知</StatusBadge>;
}

const TIER_OPTIONS: Array<{ key: string; label: string }> = [
  { key: 't1_score', label: 'STANDARD 档 (评分/NER/评测)' },
  { key: 't3_summary', label: 'HEAVY 档 (深度阅读/报告)' },
  { key: 't3_chunk_summary', label: 'FLASH 档 (摘要/轻量高频)' },
];

export interface PoolPlatformRowProps {
  p: PoolPlatform;
  keyDraft: string;
  routeOpen: boolean;
  routeDraft?: { tier: string; model: string };
  isWriting: boolean;
  onKeyDraftChange: (v: string) => void;
  onToggleRoute: () => void;
  onTierChange: (tier: string) => void;
  onModelChange: (model: string) => void;
  onSave: () => void;
  onWriteRoute: (tier: string, model: string) => void;
}

export function PoolPlatformRow({
  p,
  keyDraft,
  routeOpen,
  routeDraft,
  isWriting,
  onKeyDraftChange,
  onToggleRoute,
  onTierChange,
  onModelChange,
  onSave,
  onWriteRoute,
}: PoolPlatformRowProps) {
  return (
    <div className="st-rule" data-testid={`pool-${p.name}`}>
      <div>
        <p className="st-label">{p.label}</p>
        <p className="st-key">
          {p.name} · {p.key_env}
          {p.available === true && p.models.length > 0 && (
            <span> · {p.models.slice(0, 3).join(' / ')}{p.model_count > 3 ? ` …` : ''}</span>
          )}
          {p.error && p.error !== 'no_key' && <span> · {p.error}</span>}
        </p>
      </div>
      <div className="st-ctrl">
        <PlatformChip p={p} />
        {!p.configured && (
          <div className="st-ctrlrow">
            <input
              type="password"
              className="st-input"
              style={{ maxWidth: 180 }}
              placeholder={`${p.label} API Key`}
              aria-label={`${p.label} API Key`}
              value={keyDraft}
              onChange={e => onKeyDraftChange(e.target.value)}
            />
            <button
              type="button"
              className="st-btn primary"
              onClick={onSave}
              aria-label={`保存并检测 ${p.label}`}
            >
              保存并检测
            </button>
          </div>
        )}
        {(p.available === true || p.configured) && (
          <button
            type="button"
            className="st-btn"
            onClick={onToggleRoute}
            aria-expanded={routeOpen}
            aria-label={`写入路由 ${p.label}`}
          >
            写入路由
          </button>
        )}
      </div>
      {routeOpen && (p.available === true || p.configured) && (
        <div className="st-ctrlrow" style={{ width: '100%', marginTop: 6 }} data-testid={`route-${p.name}`}>
          <select
            className="st-select"
            style={{ maxWidth: 230 }}
            aria-label={`${p.label} 路由档位`}
            value={routeDraft?.tier ?? 't1_score'}
            onChange={e => onTierChange(e.target.value)}
          >
            {TIER_OPTIONS.map(t => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
          {p.available === true && p.models.length > 0 ? (
            <select
              className="st-select"
              style={{ maxWidth: 230 }}
              aria-label={`${p.label} 路由模型`}
              value={routeDraft?.model ?? p.models[0]}
              onChange={e => onModelChange(e.target.value)}
            >
              {p.models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input
              type="text"
              className="st-input"
              style={{ maxWidth: 230 }}
              placeholder="模型名 (可先「重新探测」自动获取)"
              aria-label={`${p.label} 路由模型 (手输)`}
              value={routeDraft?.model ?? ''}
              onChange={e => onModelChange(e.target.value)}
            />
          )}
          <button
            type="button"
            className="st-btn primary"
            disabled={isWriting || !(routeDraft?.model ?? '').trim()}
            onClick={() => onWriteRoute(routeDraft?.tier ?? 't1_score', (routeDraft?.model ?? '').trim())}
            aria-label={`确认写入 ${p.label} 路由`}
          >
            {isWriting ? '写入中…' : '确认写入'}
          </button>
        </div>
      )}
    </div>
  );
}