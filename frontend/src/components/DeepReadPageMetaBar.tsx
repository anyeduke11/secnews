// 拆分自 DeepReadPage.tsx: 顶部元信息条 (类型/ID + provider/model/延迟/tokens/cost)
// 与「重新生成」「返回」两个动作按钮, 纯展示件。
import { DeepReadResponse } from '../types';

const metaItemStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--space-1, 4px)',
  fontSize: 11,
  color: 'var(--text-muted)',
  fontFamily: 'monospace',
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'color-mix(in srgb, var(--border-color) 40%, transparent)',
};

type DeepReadPageMetaBarProps = {
  type: string;
  id: string;
  data: DeepReadResponse | null;
  loading: boolean;
  pickedFramework: string;
  onRegenerate: (fw?: string) => void;
  onBack: () => void;
};

export function DeepReadPageMetaBar({
  type,
  id,
  data,
  loading,
  pickedFramework,
  onRegenerate,
  onBack,
}: DeepReadPageMetaBarProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 'var(--space-2, 8px)',
        padding: 'var(--space-3, 12px)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md, 8px)',
        background: 'var(--bg-card)',
      }}
    >
      <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 'var(--space-1, 4px)' }}>
        {type}/{id}
      </span>
      {data && (
        <>
          {data.category && (
            <span style={{ ...metaItemStyle, color: 'var(--color-ai)' }}>
              视角 {data.category}
            </span>
          )}
          <span style={metaItemStyle}>{data.provider || '-'}</span>
          <span style={metaItemStyle}>{data.model || '-'}</span>
          <span style={metaItemStyle}>{data.latency_ms}ms</span>
          <span style={metaItemStyle}>in {data.tokens_in} / out {data.tokens_out}</span>
          {/* 服务当前把 cost_usd 记为 0; 只在真记了账时展示, 不把 0 当既成事实呈现 */}
          {data.cost_usd > 0 && (
            <span style={metaItemStyle}>${data.cost_usd.toFixed(4)}</span>
          )}
          <span style={{ ...metaItemStyle, color: 'var(--text-muted)' }}>
            {new Date(data.updated_at).toLocaleString('zh-CN')}
          </span>
        </>
      )}
      <div style={{ flex: 1 }} />
      <button
        onClick={() => onRegenerate(pickedFramework || undefined)}
        disabled={loading}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-1, 4px)',
          padding: '4px 12px',
          borderRadius: 'var(--radius-sm, 4px)',
          border: '1px solid var(--border-color)',
          background: loading
            ? 'color-mix(in srgb, var(--color-ai) 20%, transparent)'
            : 'color-mix(in srgb, var(--color-ai) 12%, transparent)',
          color: 'var(--color-ai)',
          fontSize: 12,
          cursor: loading ? 'not-allowed' : 'pointer',
          lineHeight: '20px',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 4v6h6M23 20v-6h-6" />
          <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" />
        </svg>
        {loading ? '生成中…' : '重新生成'}
      </button>
      <button
        onClick={onBack}
        style={{
          padding: '4px 12px',
          borderRadius: 'var(--radius-sm, 4px)',
          border: '1px solid var(--border-color)',
          background: 'transparent',
          color: 'var(--text-muted)',
          fontSize: 12,
          cursor: 'pointer',
        }}
      >
        返回
      </button>
    </div>
  );
}