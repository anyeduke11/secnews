// BriefModeView — v1.7 Phase 4 简报模式视图
//
// 路由: /brief
//
// 功能:
//  1. 展示最新一条简报 (useDigest)
//  2. 摘要 + Top N 文章标题 + 跳转
//  3. 一键生成昨日简报 (POST /api/digests/generate)
//  4. 标记已读 (PUT /api/digests/read)
//
// 验收 4: 每日 08:00 生成简报 — 后端 scheduler 触发生成, 前端展示最新简报
import { useDigest } from '../hooks/useDigest';
import { useGoHome } from '../hooks/useGoHome';
import { Icon } from './Icon';

export function BriefModeView() {
  const goHome = useGoHome();
  const { digest, loading, error, refresh, generate, markRead } = useDigest();

  const handleGenerate = async () => {
    await generate();
    await markRead();
  };

  const handleMarkRead = async () => {
    await markRead();
    refresh();
  };

  return (
    <div style={pageStyle}>
      {/* 顶部栏 */}
      <div style={topBarStyle}>
        <button type="button" style={backBtnStyle} onClick={goHome} aria-label="返回首页">
          <Icon>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h1 style={titleStyle}>每日简报</h1>
        <button
          type="button"
          style={actionBtnStyle}
          onClick={handleGenerate}
          title="手动生成昨日简报"
        >
          ⟳ 生成
        </button>
      </div>

      {loading && <div style={emptyStyle}>加载简报…</div>}

      {error && (
        <div style={errorBannerStyle} role="alert">
          {error}
        </div>
      )}

      {!loading && !error && !digest && (
        <div style={emptyStyle}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
          <div>暂无简报</div>
          <div style={subHintStyle}>点击右上角「生成」手动创建昨日简报</div>
        </div>
      )}

      {!loading && !error && digest && (
        <div style={digestCardStyle}>
          <div style={cardHeaderStyle}>
            <span style={periodBadgeStyle}>{digest.period}</span>
            <span style={dateStyle}>
              {new Date(digest.created_at).toLocaleString('zh-CN')}
            </span>
          </div>
          <div style={summaryStyle}>{digest.summary}</div>
          {digest.item_ids && digest.item_ids.length > 0 && (
            <div style={idsStyle}>
              <span style={idsLabelStyle}>Top 文章 ID:</span>
              {digest.item_ids.map((iid, i) => (
                <code key={iid + i} style={idChipStyle}>
                  {iid}
                </code>
              ))}
            </div>
          )}
          {typeof digest.count === 'number' && (
            <div style={countStyle}>昨日共 {digest.count} 篇文章</div>
          )}
          <div style={actionsStyle}>
            <button
              type="button"
              style={markReadBtnStyle}
              onClick={handleMarkRead}
            >
              标记已读
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── styles ───────────────────────────────────────────────────────
const pageStyle: React.CSSProperties = {
  padding: 'var(--space-4, 16px)',
  maxWidth: 800,
  margin: '0 auto',
};

const topBarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-3, 12px)',
  marginBottom: 'var(--space-4, 16px)',
};

const backBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-1, 4px)',
  padding: '4px 10px',
  fontSize: 12,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary, #9a9ab2)',
  cursor: 'pointer',
};

const titleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 600,
  color: 'var(--text-primary, #f0f0f7)',
  flex: 1,
};

const actionBtnStyle: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--color-ai, #00d4e0)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(0, 212, 224, 0.08)',
  color: 'var(--color-ai, #00d4e0)',
  cursor: 'pointer',
};

const emptyStyle: React.CSSProperties = {
  padding: 'var(--space-6, 32px)',
  textAlign: 'center',
  color: 'var(--text-muted, #5b5b72)',
  fontSize: 14,
};

const subHintStyle: React.CSSProperties = {
  fontSize: 11,
  marginTop: 'var(--space-1, 4px)',
  color: 'var(--text-disabled, #414155)',
};

const errorBannerStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px) var(--space-3, 12px)',
  marginBottom: 'var(--space-3, 12px)',
  border: '1px solid var(--color-error, #ef4444)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(239, 68, 68, 0.08)',
  color: 'var(--color-error, #ef4444)',
  fontSize: 12,
};

const digestCardStyle: React.CSSProperties = {
  padding: 'var(--space-4, 16px)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card, #0d0d14)',
};

const cardHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
  marginBottom: 'var(--space-3, 12px)',
};

const periodBadgeStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 8px',
  borderRadius: 4,
  background: 'rgba(0, 212, 224, 0.15)',
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
};

const dateStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

const summaryStyle: React.CSSProperties = {
  fontSize: 15,
  color: 'var(--text-primary, #f0f0f7)',
  lineHeight: 1.7,
  marginBottom: 'var(--space-3, 12px)',
};

const idsStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: 'var(--space-1, 4px) var(--space-2, 8px)',
  marginBottom: 'var(--space-3, 12px)',
  padding: 'var(--space-2, 8px)',
  background: 'rgba(255, 255, 255, 0.02)',
  borderRadius: 'var(--radius-sm, 4px)',
};

const idsLabelStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
};

const idChipStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '1px 6px',
  borderRadius: 3,
  background: 'rgba(255, 255, 255, 0.05)',
  color: 'var(--text-secondary, #9a9ab2)',
  fontFamily: 'monospace',
};

const countStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary, #9a9ab2)',
  marginBottom: 'var(--space-3, 12px)',
  fontWeight: 600,
};

const actionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2, 8px)',
};

const markReadBtnStyle: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary, #9a9ab2)',
  cursor: 'pointer',
};

export default BriefModeView;
