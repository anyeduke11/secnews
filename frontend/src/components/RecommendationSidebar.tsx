// RecommendationSidebar — v1.7 Phase 4 上下文推荐侧栏
//
// 功能:
//  1. 根据 entityType + entityId 调用 /api/recommend/{type}/{id} 拉取相关条目
//  2. 列表展示, 每条显示标题、共享标签、分数
//  3. 点击跳转到对应的 deep read 页面
//
// 验收 2: 知识推荐侧栏显示相关条目
import { useRecommendations } from '../hooks/useRecommendations';
import type { RecommendationItem } from '../hooks/useRecommendations';
import { Icon } from './Icon';

export interface RecommendationSidebarProps {
  entityType: string;
  entityId: string;
  limit?: number;
  onSelect?: (item: RecommendationItem) => void;
}

export function RecommendationSidebar({
  entityType,
  entityId,
  limit = 5,
  onSelect,
}: RecommendationSidebarProps) {
  const { items, loading, error } = useRecommendations(entityType, entityId, limit);

  return (
    <aside style={sidebarStyle} aria-label="相关推荐">
      <div style={headerStyle}>
        <Icon>
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </Icon>
        <span style={titleStyle}>相关推荐</span>
        {items.length > 0 && (
          <span style={countBadgeStyle}>{items.length}</span>
        )}
      </div>

      {loading && <div style={emptyStyle}>加载推荐…</div>}

      {error && (
        <div style={errorStyle} role="alert">
          {error}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div style={emptyStyle}>
          <div style={{ fontSize: 24, marginBottom: 4 }}>∅</div>
          <div>暂无相关条目</div>
          <div style={subHintStyle}>需有共享标签才会出现</div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <ul style={listStyle}>
          {items.map((r, i) => (
            <li
              key={r.item.id || i}
              style={itemStyle}
              onClick={() => onSelect?.(r)}
              role="button"
              tabIndex={0}
            >
              <div style={itemTitleStyle}>{r.item.title || '(无标题)'}</div>
              {r.item.summary && (
                <div style={itemSummaryStyle}>
                  {r.item.summary.length > 80
                    ? r.item.summary.slice(0, 80) + '…'
                    : r.item.summary}
                </div>
              )}
              <div style={itemMetaStyle}>
                {r.shared_tags.length > 0 && (
                  <span style={tagsStyle}>
                    {r.shared_tags.slice(0, 3).map((t) => (
                      <span key={t} style={tagStyle}>
                        #{t}
                      </span>
                    ))}
                  </span>
                )}
                <span style={scoreStyle}>★ {r.score}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

// ── styles ───────────────────────────────────────────────────────
const sidebarStyle: React.CSSProperties = {
  width: 320,
  flexShrink: 0,
  padding: 'var(--space-3, 12px)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card, #0d0d14)',
  maxHeight: '70vh',
  overflowY: 'auto',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
  marginBottom: 'var(--space-3, 12px)',
  paddingBottom: 'var(--space-2, 8px)',
  borderBottom: '1px solid var(--border-color, #1c1c2e)',
};

const titleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary, #f0f0f7)',
  flex: 1,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
};

const countBadgeStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 6px',
  borderRadius: 10,
  background: 'rgba(0, 212, 224, 0.15)',
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
};

const emptyStyle: React.CSSProperties = {
  padding: 'var(--space-4, 16px)',
  textAlign: 'center',
  color: 'var(--text-muted, #5b5b72)',
  fontSize: 12,
};

const subHintStyle: React.CSSProperties = {
  fontSize: 11,
  marginTop: 'var(--space-1, 4px)',
  color: 'var(--text-disabled, #414155)',
};

const errorStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px)',
  fontSize: 12,
  color: 'var(--color-error, #ef4444)',
  border: '1px solid var(--color-error, #ef4444)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(239, 68, 68, 0.05)',
};

const listStyle: React.CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2, 8px)',
};

const itemStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px) var(--space-3, 12px)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(255, 255, 255, 0.02)',
  cursor: 'pointer',
  transition: 'background 0.15s',
};

const itemTitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-primary, #f0f0f7)',
  marginBottom: 4,
  lineHeight: 1.4,
};

const itemSummaryStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary, #9a9ab2)',
  marginBottom: 6,
  lineHeight: 1.4,
};

const itemMetaStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 4,
};

const tagsStyle: React.CSSProperties = {
  display: 'inline-flex',
  flexWrap: 'wrap',
  gap: 4,
};

const tagStyle: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 5px',
  borderRadius: 3,
  background: 'rgba(0, 212, 224, 0.1)',
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
};

const scoreStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

export default RecommendationSidebar;
