/**
 * DeepReadMode — 深度阅读模式
 *
 * 路由: /knowledge/deep-read/:id
 *
 * 双栏布局:
 *  左 (主): 文章全文 (标题 + 正文 + 元数据)
 *  右 (侧栏): LifecycleProgress + 相关概念 + 推荐条目
 *
 * B5 续拆: 容器只保留路由参数 / 状态 / 取数与注意力埋点编排;
 * 纯类型 → deepReadModeModel.ts, 展示区块 → DeepReadHeader / DeepReadArticle / DeepReadSidebar。
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getKnowledgeItem, getKnowledgeItemChunks, getRecommendedKnowledge, KnowledgeApiError, postAttentionEvent } from '../../api/knowledge';
import { DeepReadArticle } from './DeepReadArticle';
import { DeepReadHeader } from './DeepReadHeader';
import { DeepReadSidebar } from './DeepReadSidebar';
import type { ChunkInfo, DeepReadItem, RecommendResponse, RecommendResult } from './deepReadModeModel';

export function DeepReadMode() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [item, setItem] = useState<DeepReadItem | null>(null);
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

    getKnowledgeItem(id)
      .then(data => {
        if (cancelled) return;
        setItem(data);
        setContent(data.content || '');
      })
      .catch(e => {
        // 404 语义保留: 条目不存在 (客户端 KnowledgeApiError.status) 与请求失败区分展示
        if (!cancelled) {
          setError(e instanceof KnowledgeApiError && e.status === 404 ? '条目未找到' : (e?.message || '加载失败'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // P3-2: 深度阅读埋点 — view + dwell (卸载时) + scroll (节流)
    // 注意力数据此前为 0 (前端从未 POST /api/attention/events → 热力图/评分空转)
    // 字段契约见 attention_scorer: dwell_seconds / depth_pct
    const startTs = Date.now();
    postAttentionEvent({ item_id: id, event_type: 'view', detail_json: { source: 'deep-read' } }).catch(() => {});

    let lastScrollSent = 0;
    const onScroll = () => {
      const now = Date.now();
      if (now - lastScrollSent < 5000) return; // 节流 5s
      lastScrollSent = now;
      const el = document.scrollingElement || document.documentElement;
      const maxScroll = el.scrollHeight - el.clientHeight;
      const depthPct = maxScroll > 0 ? Math.round((el.scrollTop / maxScroll) * 100) : 0;
      if (depthPct >= 10) {
        postAttentionEvent({ item_id: id, event_type: 'scroll', detail_json: { depth_pct: depthPct } }).catch(() => {});
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    return () => {
      cancelled = true;
      window.removeEventListener('scroll', onScroll);
      const dwellMs = Date.now() - startTs;
      if (dwellMs > 3000) {
        postAttentionEvent({
          item_id: id,
          event_type: 'dwell',
          detail_json: { dwell_seconds: Math.round(dwellMs / 1000) },
        }).catch(() => {});
      }
    };
  }, [id]);

  // 加载推荐条目
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setRecommendLoading(true);

    // 非 2xx 由 apiFetch 抛错 → 与原 `if (!r.ok) return` 同为静默放弃推荐
    getRecommendedKnowledge<RecommendResponse>(id, 5)
      .then(data => {
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

    getKnowledgeItemChunks(id)
      .then(data => {
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
      <DeepReadHeader item={item} onBack={() => navigate('/knowledge/compile')} />

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
          <DeepReadArticle item={item} content={content} chunks={chunks} chunksLoading={chunksLoading} />

          {/* 右侧侧栏 */}
          <DeepReadSidebar
            item={item}
            recommendations={recommendations}
            recommendLoading={recommendLoading}
            onOpen={(rid) => navigate(`/knowledge/deep-read/${rid}`)}
          />
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
