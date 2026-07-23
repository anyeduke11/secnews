// DeepReadView — v1.7 Phase 4 深度阅读视图
//
// 路由: /deep/:type/:id
//
// 三栏布局:
//  1. 左侧 ArticlePanel: 显示文章详情 (title/summary/source/url/score)
//  2. 中间 RecommendationSidebar: 基于标签的相关推荐
//  3. 右侧 NotePanel: 该实体的笔记 (增删改查)
//
// 验收 1: 阅读 3 篇 AI 文章后 AI 分类权重提升 — 后端 record_read 在 GET /api/hotspots/{id} 时触发
// 验收 2: 知识推荐侧栏显示相关条目 — RecommendationSidebar
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { RecommendationSidebar } from './RecommendationSidebar';
import { NotePanel } from './NotePanel';
import { useGoHome } from '../hooks/useGoHome';
import { Icon } from './Icon';

interface ArticleData {
  id: string;
  title: string;
  summary?: string;
  source?: string;
  url?: string;
  category?: string;
  published_at?: string;
  score?: number;
  [k: string]: unknown;
}

export function DeepReadView() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const navigate = useNavigate();
  const goHome = useGoHome();
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!type || !id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // 根据 type 选择 API: hotspot → /api/hotspots/{id}, knowledge → /api/knowledge/items/{id}
    const url =
      type === 'hotspot'
        ? `/api/hotspots/${encodeURIComponent(id)}`
        : type === 'knowledge'
          ? `/api/knowledge/items/${encodeURIComponent(id)}`
          : null;
    if (!url) {
      setError(`不支持的类型: ${type}`);
      setLoading(false);
      return;
    }
    fetch(url, { headers: { Accept: 'application/json' } })
      .then(async (r) => {
        if (!r.ok) throw new Error(`请求失败 (${r.status})`);
        const data = await r.json();
        if (cancelled) return;
        // 兼容 {item: {...}} 和直接 {...} 两种返回格式
        setArticle(data.item || data);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message || '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [type, id]);

  if (!type || !id) {
    return <div style={emptyStyle}>缺少 type 或 id 参数</div>;
  }

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
        <h1 style={titleStyle}>深度阅读</h1>
        <span style={typeBadgeStyle}>{type}</span>
      </div>

      {error && <div style={errorBannerStyle}>{error}</div>}

      {loading && <div style={emptyStyle}>加载文章…</div>}

      {!loading && article && (
        <div style={threeColStyle}>
          {/* 左侧: 文章详情 */}
          <article style={articleColStyle}>
            <h2 style={articleTitleStyle}>{article.title || '(无标题)'}</h2>
            {article.summary && (
              <p style={articleSummaryStyle}>{article.summary}</p>
            )}
            <div style={articleMetaStyle}>
              {article.source && (
                <span style={metaItemStyle}>来源: {article.source}</span>
              )}
              {article.published_at && (
                <span style={metaItemStyle}>
                  发布: {new Date(article.published_at).toLocaleString('zh-CN')}
                </span>
              )}
              {typeof article.score === 'number' && (
                <span style={metaItemStyle}>★ {article.score}</span>
              )}
            </div>
            {article.url && (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                style={linkStyle}
              >
                原文链接 ↗
              </a>
            )}
          </article>

          {/* 中间: 推荐侧栏 */}
          <RecommendationSidebar
            entityType={type}
            entityId={id}
            limit={5}
            onSelect={(r) => {
              // 点击推荐项 → 跳转到对应 deep read
              const targetType =
                type === 'hotspot' ? 'hotspot' : 'knowledge';
              navigate(`/deep/${targetType}/${r.item.id}`);
            }}
          />

          {/* 右侧: 笔记面板 */}
          <NotePanel entityType={type} entityId={id} />
        </div>
      )}
    </div>
  );
}

// ── styles ───────────────────────────────────────────────────────
const pageStyle: React.CSSProperties = {
  padding: 'var(--space-4, 16px)',
  maxWidth: 1400,
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

const typeBadgeStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 8px',
  borderRadius: 4,
  background: 'rgba(0, 212, 224, 0.15)',
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
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

const emptyStyle: React.CSSProperties = {
  padding: 'var(--space-6, 32px)',
  textAlign: 'center',
  color: 'var(--text-muted, #5b5b72)',
  fontSize: 14,
};

const threeColStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-4, 16px)',
  alignItems: 'flex-start',
};

const articleColStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: 'var(--space-4, 16px)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card, #0d0d14)',
};

const articleTitleStyle: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 700,
  color: 'var(--text-primary, #f0f0f7)',
  marginBottom: 'var(--space-3, 12px)',
  lineHeight: 1.4,
};

const articleSummaryStyle: React.CSSProperties = {
  fontSize: 14,
  color: 'var(--text-secondary, #9a9ab2)',
  lineHeight: 1.7,
  marginBottom: 'var(--space-3, 12px)',
  whiteSpace: 'pre-wrap',
};

const articleMetaStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 'var(--space-2, 8px) var(--space-3, 12px)',
  marginBottom: 'var(--space-3, 12px)',
  padding: 'var(--space-2, 8px) 0',
  borderTop: '1px solid var(--border-color, #1c1c2e)',
  borderBottom: '1px solid var(--border-color, #1c1c2e)',
};

const metaItemStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

const linkStyle: React.CSSProperties = {
  display: 'inline-block',
  fontSize: 12,
  color: 'var(--color-ai, #00d4e0)',
  textDecoration: 'none',
  padding: '4px 0',
};

export default DeepReadView;
