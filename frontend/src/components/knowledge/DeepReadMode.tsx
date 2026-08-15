/**
 * DeepReadMode — 深度阅读模式
 *
 * 路由: /knowledge/deep-read/:id
 *
 * 双栏布局:
 *  左 (主): 文章全文 (标题 + 正文 + 元数据)
 *  右 (侧栏): LifecycleProgress + 相关概念 + 推荐条目
 */
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { LifecycleProgress } from './LifecycleProgress';
import type { KnowledgeItem } from '../../types';

interface RecommendResult {
  item: KnowledgeItem;
  score: number;
  shared_tags: string[];
}

interface RecommendResponse {
  version: string;
  entity_type: string;
  entity_id: string;
  items: RecommendResult[];
}

interface ChunkInfo {
  id: number;
  item_id: string;
  chunk_index: number;
  content: string;
  char_start: number;
  char_end: number;
  summary: string;
  created_at: string;
}

export function DeepReadMode() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [item, setItem] = useState<(KnowledgeItem & { content?: string; lifecycle?: string }) | null>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendResult[]>([]);
  const [recommendLoading, setRecommendLoading] = useState(false);
  const [chunks, setChunks] = useState<ChunkInfo[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  // 加载主条目
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setItem(null);
    setContent('');

    fetch(`/api/knowledge/items/${encodeURIComponent(id)}`)
      .then(async r => {
        if (!r.ok) {
          if (r.status === 404) throw new Error('条目未找到');
          throw new Error(`请求失败 (${r.status})`);
        }
        const data = await r.json();
        if (cancelled) return;
        setItem(data);
        setContent(data.content || '');
      })
      .catch(e => {
        if (!cancelled) setError(e?.message || '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // P3-2: 深度阅读埋点 — view + dwell (卸载时) + scroll (节流)
    // 注意力数据此前为 0 (前端从未 POST /api/attention/events → 热力图/评分空转)
    // 字段契约见 attention_scorer: dwell_seconds / depth_pct
    const startTs = Date.now();
    fetch('/api/attention/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: id, event_type: 'view', detail_json: { source: 'deep-read' } }),
    }).catch(() => {});

    let lastScrollSent = 0;
    const onScroll = () => {
      const now = Date.now();
      if (now - lastScrollSent < 5000) return; // 节流 5s
      lastScrollSent = now;
      const el = document.scrollingElement || document.documentElement;
      const maxScroll = el.scrollHeight - el.clientHeight;
      const depthPct = maxScroll > 0 ? Math.round((el.scrollTop / maxScroll) * 100) : 0;
      if (depthPct >= 10) {
        fetch('/api/attention/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: id, event_type: 'scroll', detail_json: { depth_pct: depthPct } }),
        }).catch(() => {});
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    return () => {
      cancelled = true;
      window.removeEventListener('scroll', onScroll);
      const dwellMs = Date.now() - startTs;
      if (dwellMs > 3000) {
        fetch('/api/attention/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: id, event_type: 'dwell', detail_json: { dwell_seconds: Math.round(dwellMs / 1000) } }),
        }).catch(() => {});
      }
    };
  }, [id]);

  // 加载推荐条目
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setRecommendLoading(true);

    fetch(`/api/recommend/knowledge/${encodeURIComponent(id)}?limit=5`)
      .then(async r => {
        if (!r.ok) return;
        const data: RecommendResponse = await r.json();
        if (!cancelled) setRecommendations(data.items || []);
      })
      .catch(() => { /* 推荐失败静默忽略 */ })
      .finally(() => {
        if (!cancelled) setRecommendLoading(false);
      });

    return () => { cancelled = true; };
  }, [id]);

  // 加载 chunks
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setChunksLoading(true);
    setChunks([]);

    fetch(`/api/knowledge/chunks/${encodeURIComponent(id)}`)
      .then(async r => {
        if (!r.ok) return;
        const data = await r.json();
        if (!cancelled) setChunks(data.chunks || []);
      })
      .catch(() => { /* chunks 加载失败静默忽略 */ })
      .finally(() => {
        if (!cancelled) setChunksLoading(false);
      });

    return () => { cancelled = true; };
  }, [id]);

  if (!id) {
    return (
      <div className="flex items-center justify-center py-16" style={{ color: 'var(--text-muted)' }}>
        <span className="text-sm">缺少条目 ID</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* 顶部导航栏 */}
      <div
        className="flex items-center gap-3 rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 text-xs flex items-center gap-1.5"
          style={{ color: 'var(--text-secondary)' }}
          onClick={() => navigate('/knowledge/compile')}
          aria-label="返回知识库"
        >
          <Icon size={12}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h1 className="text-sm font-bold flex-1" style={{ color: 'var(--text-primary)' }}>
          深度阅读
        </h1>
        {item && (
          <span
            className="text-[10px] px-2 py-0.5 rounded font-mono"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-ai) 12%, transparent)',
              color: 'var(--color-ai)',
            }}
          >
            {item.domain || 'unknown'}
          </span>
        )}
      </div>

      {/* 错误状态 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          {error}
        </div>
      )}

      {/* 加载状态 */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            加载中…
          </div>
        </div>
      )}

      {/* 双栏主体 */}
      {!loading && !error && item && (
        <div className="flex gap-3 items-start">
          {/* 左侧主栏: 文章全文 */}
          <div className="flex-1 min-w-0 space-y-3">
            <section
              className="rounded-[var(--radius-md)] p-4"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              {/* 标题 */}
              <h2
                className="text-lg font-bold mb-3 leading-relaxed"
                style={{ color: 'var(--text-primary)' }}
              >
                {item.title || '(无标题)'}
              </h2>

              {/* 元数据行 */}
              <div
                className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] pb-3 mb-3"
                style={{
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border-color)',
                }}
              >
                {item.source && (
                  <span className="flex items-center gap-1">
                    <Icon size={11}>
                      <circle cx="12" cy="12" r="9" />
                      <path d="M12 7v10M7 12h10" />
                    </Icon>
                    {item.source}
                  </span>
                )}
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--color-ai)' }}
                    className="hover:underline"
                  >
                    原文链接 ↗
                  </a>
                )}
                {item.ingested_at && (
                  <span>
                    录入: {new Date(item.ingested_at).toLocaleString('zh-CN')}
                  </span>
                )}
                {item.type && <span>类型: {item.type}</span>}
                {item.difficulty && <span>难度: {item.difficulty}</span>}
                {item.mastered !== undefined && (
                  <span>掌握度: {item.mastered}%</span>
                )}
              </div>

              {/* 标签 */}
              {item.tags && item.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {item.tags.map(tag => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded text-[10px]"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--color-ai) 10%, transparent)',
                        color: 'var(--color-ai)',
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* 正文 (Markdown, 只读) — 按 chunk 分段显示 */}
              <div
                className="text-sm leading-relaxed"
                style={{
                  color: 'var(--text-primary)',
                  lineHeight: 1.8,
                }}
              >
                {!content ? (
                  <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    无正文内容
                  </span>
                ) : chunks.length > 0 ? (
                  <div>
                    {chunks.map((chunk, i) => {
                      const chunkText = content.slice(chunk.char_start, chunk.char_end) || chunk.content;
                      if (!chunkText) return null;
                      return (
                        <React.Fragment key={chunk.chunk_index}>
                          {i > 0 && (
                            <div
                              style={{
                                borderBottom: '1px solid color-mix(in srgb, var(--border-color) 60%, transparent)',
                                margin: 'var(--space-2, 8px) 0',
                              }}
                            />
                          )}
                          <div
                            id={`chunk-${chunk.chunk_index}`}
                            className="group relative"
                            style={{
                              borderLeft: '2px solid color-mix(in srgb, var(--color-info) 15%, transparent)',
                              paddingLeft: '12px',
                              paddingTop: '2px',
                              paddingBottom: '2px',
                            }}
                          >
                            <div className="flex items-center gap-1.5 mb-1">
                              <span
                                className="text-[9px] font-mono px-1 py-0.5 rounded"
                                style={{
                                  backgroundColor: 'color-mix(in srgb, var(--color-info) 8%, transparent)',
                                  color: 'var(--color-info)',
                                }}
                              >
                                #{chunk.chunk_index + 1}
                              </span>
                              <button
                                type="button"
                                className="text-[9px] opacity-0 group-hover:opacity-100 transition-opacity hover:underline"
                                style={{ color: 'var(--color-ai)' }}
                                onClick={() => {
                                  document.getElementById(`chunk-${chunk.chunk_index}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                }}
                              >
                                跳转
                              </button>
                            </div>
                            <div
                              style={{
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                              }}
                            >
                              {chunkText}
                            </div>
                          </div>
                        </React.Fragment>
                      );
                    })}
                  </div>
                ) : chunksLoading ? (
                  <div className="flex items-center gap-1.5 py-2" style={{ color: 'var(--text-muted)' }}>
                    <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs">加载分段…</span>
                  </div>
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {content}
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* 右侧侧栏 */}
          <div
            className="w-64 shrink-0 space-y-3"
            style={{ position: 'sticky', top: 'var(--space-3, 12px)' }}
          >
            {/* LifecycleProgress */}
            <section
              className="rounded-[var(--radius-md)] p-3"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <h3
                className="text-[10px] font-bold uppercase tracking-wide mb-2"
                style={{ color: 'var(--text-muted)' }}
              >
                学习进度
              </h3>
              <LifecycleProgress currentStage={item.lifecycle || 'kl:raw'} />
            </section>

            {/* 相关概念 */}
            <section
              className="rounded-[var(--radius-md)] p-3"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <h3
                className="text-[10px] font-bold uppercase tracking-wide mb-2"
                style={{ color: 'var(--text-muted)' }}
              >
                相关概念
              </h3>
              {item.concepts && item.concepts.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {item.concepts.map(c => (
                    <span
                      key={c}
                      className="px-2 py-0.5 rounded text-[10px]"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--color-startup) 12%, transparent)',
                        color: 'var(--color-startup)',
                      }}
                    >
                      {c}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  暂无关联概念
                </p>
              )}
            </section>

            {/* 推荐条目 */}
            <section
              className="rounded-[var(--radius-md)] p-3"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <h3
                className="text-[10px] font-bold uppercase tracking-wide mb-2"
                style={{ color: 'var(--text-muted)' }}
              >
                推荐阅读
              </h3>
              {recommendLoading ? (
                <div className="flex items-center gap-1.5 py-2">
                  <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</span>
                </div>
              ) : recommendations.length > 0 ? (
                <ul className="space-y-2">
                  {recommendations.map((rec, i) => (
                    <li key={rec.item.id}>
                      <button
                        type="button"
                        className="w-full text-left text-xs leading-relaxed px-2 py-1.5 rounded-[var(--radius-sm)] transition-colors"
                        style={{ color: 'var(--text-primary)' }}
                        onClick={() => navigate(`/knowledge/deep-read/${rec.item.id}`)}
                        onMouseEnter={e => {
                          (e.currentTarget as HTMLElement).style.backgroundColor = 'var(--bg-hover)';
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent';
                        }}
                      >
                        <span className="block truncate" title={rec.item.title}>
                          {rec.item.title}
                        </span>
                        <span className="block text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          共享标签: {rec.shared_tags.join(', ')}
                        </span>
                      </button>
                      {i < recommendations.length - 1 && (
                        <div style={{ borderBottom: '1px solid var(--border-color)', margin: '4px 0' }} />
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  暂无推荐
                </p>
              )}
            </section>
          </div>
        </div>
      )}

      {/* 空状态: ID 有效但条目不存在 (由 error 覆盖, 此为兜底) */}
      {!loading && !error && !item && (
        <div
          className="rounded-[var(--radius-md)] p-6 text-center"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            条目未找到
          </p>
        </div>
      )}
    </div>
  );
}