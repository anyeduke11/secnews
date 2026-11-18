/**
 * ReviewMode — 间隔复习模式 (Phase 17)
 *
 * 基于 SM-2 算法的抽认卡复习界面。
 * 从 /api/reviews/due 获取到期复习队列，以翻转卡片形式展示知识条目，
 * 用户查看背面后给出 0-5 评分，评分自动提交至 /api/reviews/grade。
 *
 * 路由: /knowledge/review
 *
 * B5 拆分: 本文件只保留容器 (状态 + 取数/评分编排); 展示区块在 ./review/
 */
import { useState, useEffect, useCallback } from 'react';
import { listDueReviews, submitReviewGrade } from '../../api/action';
import { getKnowledgeItem } from '../../api/knowledge';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { OnboardingHint } from '../layout/OnboardingHint';
import { ReviewHeader } from './review/ReviewHeader';
import { ReviewLoading, ReviewError, ReviewEmpty } from './review/ReviewStates';
import { ReviewComplete } from './review/ReviewComplete';
import { ReviewProgress, ReviewFlipCard } from './review/ReviewFlipCard';
import type { GradeResponse, KnowledgeDetail, ReviewRecord } from './review/reviewModel';

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
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  // ── 获取到期复习队列 ──

  const fetchDueReviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFlipped(false);
    setCurrentIndex(0);
    setGrades([]);
    setCompleted(false);

    try {
      const dueData = await listDueReviews<ReviewRecord>(50);
      if (dead.current) return;
      const items = dueData.items || [];
      setReviews(items);

      if (items.length === 0) {
        setLoading(false);
        return;
      }

      // 并行获取每条复习记录对应的知识条目详情
      // Batch 5: /api/knowledge/items/{id} 收敛到 api/knowledge.getKnowledgeItem
      // (失败兜底语义与原 `res.ok ? json : null` 一致: 失败条目跳过, 不阻断其余)
      const detailMap = new Map<string, KnowledgeDetail>();
      const results = await Promise.allSettled(
        items.map(r =>
          getKnowledgeItem(r.entity_id)
            .then(d => d as unknown as KnowledgeDetail)
            .catch(() => null),
        ),
      );
      results.forEach((result) => {
        if (result.status === 'fulfilled' && result.value) {
          detailMap.set(result.value.id, result.value);
        }
      });
      if (dead.current) return;
      setDetails(detailMap);
    } catch (e) {
      if (dead.current) return;
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      if (!dead.current) setLoading(false);
    }
  }, [dead]);

  useEffect(() => {
    fetchDueReviews();
  }, [fetchDueReviews]);

  // ── 提交评分 ──

  const handleGrade = useCallback(async (grade: number) => {
    const review = reviews[currentIndex];
    if (!review || submitting) return;

    setSubmitting(true);
    try {
      // 非 2xx 由 apiFetch 抛 ApiError, message 经 getApiErrorMessage 友好化
      const data = await submitReviewGrade<GradeResponse>(
        review.entity_type,
        review.entity_id,
        grade,
      );
      if (dead.current) return;
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
      if (dead.current) return;
      setError(e instanceof Error ? e.message : '评分提交失败');
    } finally {
      if (!dead.current) setSubmitting(false);
    }
  }, [currentIndex, reviews, submitting, dead]);

  // ── 当前卡片数据 ──

  const currentReview = reviews[currentIndex] ?? null;
  const currentDetail = currentReview
    ? details.get(currentReview.entity_id) ?? null
    : null;

  // ── 渲染: 加载状态 ──

  if (loading) {
    return <ReviewLoading />;
  }

  // ── 渲染: 错误状态 ──

  if (error) {
    return <ReviewError error={error} onRetry={fetchDueReviews} />;
  }

  // ── 渲染: 空状态 (无到期复习) ──

  if (reviews.length === 0) {
    return <ReviewEmpty onRefresh={fetchDueReviews} />;
  }

  // ── 渲染: 完成屏幕 ──

  if (completed) {
    return <ReviewComplete total={reviews.length} grades={grades} onRestart={fetchDueReviews} />;
  }

  // ── 渲染: 复习进行中 ──

  const cardContent = currentDetail?.content || '';
  const cardTitle = currentDetail?.title || currentReview?.entity_id || '(无标题)';
  const hasDetail = currentDetail !== null;

  return (
    <div className="space-y-3 ed-typo">
      <OnboardingHint storageKey="kb-review" title="复习模式">
        <p>按间隔复习已学概念，巩固掌握度。</p>
      </OnboardingHint>

      {/* 顶部描述 */}
      <ReviewHeader />

      {/* 进度条 */}
      <ReviewProgress index={currentIndex} total={reviews.length} />

      {/* 翻转卡片 */}
      <ReviewFlipCard
        flipped={flipped}
        onFlip={() => setFlipped(true)}
        detail={currentDetail}
        title={cardTitle}
        content={cardContent}
        hasDetail={hasDetail}
        submitting={submitting}
        onGrade={handleGrade}
      />
    </div>
  );
}
