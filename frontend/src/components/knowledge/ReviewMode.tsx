/**
 * ReviewMode — 间隔复习模式 (Phase 17)
 *
 * 基于 SM-2 算法的抽认卡复习界面。
 * 从 /api/reviews/due 获取到期复习队列，以翻转卡片形式展示知识条目，
 * 用户查看背面后给出 0-5 评分，评分自动提交至 /api/reviews/grade。
 *
 * 路由: /knowledge/review
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Icon } from '../Icon';

// ── 类型定义 ──────────────────────────────────────────────────

interface ReviewRecord {
  id: number;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface KnowledgeDetail {
  id: string;
  title: string;
  source: string;
  source_url: string;
  domain: string | null;
  tags: string[];
  concepts: string[];
  mastered: number;
  content?: string;
}

interface DueResponse {
  version: string;
  count: number;
  items: ReviewRecord[];
}

interface GradeResponse {
  version: string;
  status: string;
  item: ReviewRecord;
}

// ── 评分按钮配置 ──────────────────────────────────────────────

const GRADE_LABELS: { value: number; label: string; desc: string }[] = [
  { value: 0, label: '0', desc: '完全忘记' },
  { value: 1, label: '1', desc: '几乎想不起' },
  { value: 2, label: '2', desc: '有印象但模糊' },
  { value: 3, label: '3', desc: '勉强回忆' },
  { value: 4, label: '4', desc: '基本掌握' },
  { value: 5, label: '5', desc: '完全牢记' },
];

// ── 辅助函数 ──────────────────────────────────────────────────

/** 截断文本到指定长度，保留完整单词 */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).replace(/\s+\S*$/, '') + '…';
}

// ── 主组件 ────────────────────────────────────────────────────

export function ReviewMode() {
  // 数据状态
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [details, setDetails] = useState<Map<string, KnowledgeDetail>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 翻卡状态
  const [currentIndex, setCurrentIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  // 统计
  const [grades, setGrades] = useState<number[]>([]);
  const [completed, setCompleted] = useState(false);

  // ── 获取到期复习队列 ──

  const fetchDueReviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFlipped(false);
    setCurrentIndex(0);
    setGrades([]);
    setCompleted(false);

    try {
      const dueRes = await fetch('/api/reviews/due?limit=50');
      if (!dueRes.ok) throw new Error(`请求失败 (${dueRes.status})`);
      const dueData: DueResponse = await dueRes.json();
      const items = dueData.items || [];
      setReviews(items);

      if (items.length === 0) {
        setLoading(false);
        return;
      }

      // 并行获取每条复习记录对应的知识条目详情
      const detailMap = new Map<string, KnowledgeDetail>();
      const results = await Promise.allSettled(
        items.map(r =>
          fetch(`/api/knowledge/items/${encodeURIComponent(r.entity_id)}`)
            .then(async res => {
              if (!res.ok) return null;
              return (await res.json()) as KnowledgeDetail;
            })
        ),
      );
      results.forEach((result) => {
        if (result.status === 'fulfilled' && result.value) {
          detailMap.set(result.value.id, result.value);
        }
      });
      setDetails(detailMap);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDueReviews();
  }, [fetchDueReviews]);

  // ── 提交评分 ──

  const handleGrade = useCallback(async (grade: number) => {
    const review = reviews[currentIndex];
    if (!review || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch(
        `/api/reviews/${encodeURIComponent(review.entity_type)}/${encodeURIComponent(review.entity_id)}/grade`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ grade }),
        },
      );
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail?.message || `评分提交失败 (${res.status})`);
      }
      const data: GradeResponse = await res.json();
      if (data.status !== 'ok') throw new Error('评分提交失败');

      // 记录评分
      setGrades(prev => [...prev, grade]);
      setFlipped(false);

      // 判断是否完成
      if (currentIndex >= reviews.length - 1) {
        setCompleted(true);
      } else {
        setCurrentIndex(prev => prev + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '评分提交失败');
    } finally {
      setSubmitting(false);
    }
  }, [currentIndex, reviews, submitting]);

  // ── 当前卡片数据 ──

  const currentReview = reviews[currentIndex] ?? null;
  const currentDetail = currentReview
    ? details.get(currentReview.entity_id) ?? null
    : null;

  // ── 渲染: 加载状态 ──

  if (loading) {
    return (
      <div className="space-y-3">
        <div
          className="rounded-[var(--radius-md)] p-3"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2">
            <Icon size={16}>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
              间隔复习
            </h3>
          </div>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            SM-2 抽认卡复习，巩固长期记忆。
          </p>
        </div>
        <div className="flex items-center justify-center py-16">
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            加载复习队列…
          </div>
        </div>
      </div>
    );
  }

  // ── 渲染: 错误状态 ──

  if (error) {
    return (
      <div className="space-y-3">
        <div
          className="rounded-[var(--radius-md)] p-3"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2">
            <Icon size={16}>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
              间隔复习
            </h3>
          </div>
        </div>
        <div
          className="rounded-[var(--radius-md)] p-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          <div className="flex items-center gap-2">
            <Icon size={14}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </Icon>
            {error}
            <button
              type="button"
              className="ml-auto underline hover:no-underline"
              onClick={fetchDueReviews}
            >
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── 渲染: 空状态 (无到期复习) ──

  if (reviews.length === 0) {
    return (
      <div className="space-y-3">
        <div
          className="rounded-[var(--radius-md)] p-3"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2">
            <Icon size={16}>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
              间隔复习
            </h3>
          </div>
        </div>
        <div
          className="rounded-[var(--radius-md)] p-6 text-center"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-3"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 10%, transparent)',
              color: 'var(--color-info)',
            }}
          >
            <Icon size={20}>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
          </div>
          <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
            暂无到期复习
          </p>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            当前没有到期的复习条目。在「深度阅读」中打开知识条目（或收藏）后，
            它们会自动进入复习队列（1 天后到期）。
          </p>
          <button
            type="button"
            className="mt-3 px-3 py-1.5 text-xs rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 12%, transparent)',
              color: 'var(--color-info)',
              border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)',
            }}
            onClick={fetchDueReviews}
          >
            刷新
          </button>
        </div>
      </div>
    );
  }

  // ── 渲染: 完成屏幕 ──

  if (completed) {
    const passCount = grades.filter(g => g >= 3).length;
    const failCount = grades.filter(g => g < 3).length;
    const avgGrade = grades.length > 0
      ? (grades.reduce((a, b) => a + b, 0) / grades.length).toFixed(1)
      : '—';

    return (
      <div className="space-y-3">
        <div
          className="rounded-[var(--radius-md)] p-3"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2">
            <Icon size={16}>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
              间隔复习
            </h3>
          </div>
        </div>
        <div
          className="rounded-[var(--radius-md)] p-6 text-center"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
              color: 'var(--color-success)',
            }}
          >
            <Icon size={24}>
              <polyline points="20 6 9 17 4 12" />
            </Icon>
          </div>
          <h4 className="text-base font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
            复习完成！
          </h4>
          <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
            本次共复习 {reviews.length} 张卡片
          </p>

          {/* 统计面板 */}
          <div
            className="inline-flex items-center gap-4 px-4 py-2.5 rounded-[var(--radius-md)] mb-4"
            style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
          >
            <div className="text-center">
              <div className="text-lg font-bold" style={{ color: 'var(--color-success)' }}>
                {passCount}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>通过</div>
            </div>
            <div className="w-px h-8" style={{ backgroundColor: 'var(--border-color)' }} />
            <div className="text-center">
              <div className="text-lg font-bold" style={{ color: 'var(--color-error)' }}>
                {failCount}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>遗忘</div>
            </div>
            <div className="w-px h-8" style={{ backgroundColor: 'var(--border-color)' }} />
            <div className="text-center">
              <div className="text-lg font-bold" style={{ color: 'var(--color-info)' }}>
                {avgGrade}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>平均分</div>
            </div>
          </div>

          <button
            type="button"
            className="px-3 py-1.5 text-xs rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 12%, transparent)',
              color: 'var(--color-info)',
              border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)',
            }}
            onClick={fetchDueReviews}
          >
            继续复习
          </button>
        </div>
      </div>
    );
  }

  // ── 渲染: 复习进行中 ──

  const cardContent = currentDetail?.content || '';
  const cardTitle = currentDetail?.title || currentReview?.entity_id || '(无标题)';
  const hasDetail = currentDetail !== null;

  return (
    <div className="space-y-3">
      {/* 顶部描述 */}
      <div
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center gap-2">
          <Icon size={16}>
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </Icon>
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            间隔复习
          </h3>
        </div>
      </div>

      {/* 进度条 */}
      <div
        className="rounded-[var(--radius-md)] p-2.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            复习进度
          </span>
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            第 {currentIndex + 1} / {reviews.length} 张
          </span>
        </div>
        <div
          className="w-full h-1.5 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--border-color)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${((currentIndex + 1) / reviews.length) * 100}%`,
              backgroundColor: 'var(--color-info)',
            }}
          />
        </div>
      </div>

      {/* 翻转卡片 */}
      <div
        className="flip-card-container"
        style={{ perspective: '1000px', minHeight: '320px' }}
      >
        <div
          className={`flip-card-inner ${flipped ? 'flipped' : ''}`}
          style={{
            position: 'relative',
            width: '100%',
            minHeight: '320px',
            transition: 'transform 0.5s ease',
            transformStyle: 'preserve-3d',
            transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
          }}
        >
          {/* 正面: 标题 */}
          <div
            className="flip-card-front"
            style={{
              position: 'absolute',
              inset: 0,
              backfaceVisibility: 'hidden',
              WebkitBackfaceVisibility: 'hidden',
            }}
          >
            <div
              className="rounded-[var(--radius-md)] p-5 flex flex-col items-center justify-center cursor-pointer min-h-[320px]"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
              }}
              onClick={() => setFlipped(true)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFlipped(true); } }}
              aria-label="翻转卡片查看内容"
            >
              {/* 提示标签 */}
              <span
                className="text-[10px] px-2 py-0.5 rounded-full mb-3"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-info) 10%, transparent)',
                  color: 'var(--color-info)',
                }}
              >
                点击翻转
              </span>

              {/* 标题 */}
              <h4
                className="text-base font-bold text-center leading-relaxed mb-3"
                style={{ color: 'var(--text-primary)' }}
              >
                {cardTitle}
              </h4>

              {/* 标签 */}
              {currentDetail && currentDetail.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 justify-center mb-3">
                  {currentDetail.tags.slice(0, 5).map(tag => (
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

              {/* 领域/来源 */}
              <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                {currentDetail?.domain && (
                  <span>{currentDetail.domain}</span>
                )}
                {currentDetail?.source && (
                  <>
                    {currentDetail.domain && <span aria-hidden="true">·</span>}
                    <span>{currentDetail.source}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* 背面: 内容 */}
          <div
            className="flip-card-back"
            style={{
              position: 'absolute',
              inset: 0,
              backfaceVisibility: 'hidden',
              WebkitBackfaceVisibility: 'hidden',
              transform: 'rotateY(180deg)',
            }}
          >
            <div
              className="rounded-[var(--radius-md)] p-5 flex flex-col min-h-[320px]"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
              }}
            >
              {/* 内容区 */}
              <div className="flex-1 overflow-y-auto">
                <h4
                  className="text-sm font-bold mb-2"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {cardTitle}
                </h4>
                <div
                  className="text-xs leading-relaxed"
                  style={{
                    color: 'var(--text-secondary)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    lineHeight: 1.7,
                  }}
                >
                  {hasDetail && cardContent
                    ? truncate(cardContent, 600)
                    : (
                      <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                        无详细内容
                      </span>
                    )}
                </div>
              </div>

              {/* 评分按钮区 */}
              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-color)' }}>
                <p className="text-[10px] font-medium mb-2" style={{ color: 'var(--text-muted)' }}>
                  请回忆该知识，并自评掌握程度:
                </p>
                <div className="grid grid-cols-6 gap-1.5">
                  {GRADE_LABELS.map(g => (
                    <button
                      key={g.value}
                      type="button"
                      disabled={submitting}
                      className="flex flex-col items-center gap-0.5 px-1 py-1.5 rounded-[var(--radius-sm)] transition-colors text-[10px]"
                      style={{
                        backgroundColor: submitting
                          ? 'var(--border-color)'
                          : 'color-mix(in srgb, var(--text-muted) 8%, transparent)',
                        color: submitting ? 'var(--text-muted)' : 'var(--text-primary)',
                        border: '1px solid transparent',
                        opacity: submitting ? 0.5 : 1,
                        cursor: submitting ? 'not-allowed' : 'pointer',
                      }}
                      onMouseEnter={e => {
                        if (!submitting) {
                          const el = e.currentTarget as HTMLElement;
                          el.style.borderColor = 'var(--color-info)';
                          el.style.backgroundColor = 'color-mix(in srgb, var(--color-info) 12%, transparent)';
                        }
                      }}
                      onMouseLeave={e => {
                        const el = e.currentTarget as HTMLElement;
                        el.style.borderColor = 'transparent';
                        el.style.backgroundColor = 'color-mix(in srgb, var(--text-muted) 8%, transparent)';
                      }}
                      onClick={() => handleGrade(g.value)}
                      aria-label={`评分 ${g.value}: ${g.desc}`}
                      title={g.desc}
                    >
                      <span className="text-sm font-bold">{g.label}</span>
                      <span className="text-[8px] text-center leading-tight" style={{ color: 'var(--text-muted)' }}>
                        {g.desc}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}