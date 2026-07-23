import { useState } from 'react';
import type { ReviewItem } from '../../hooks/useReviews';

/**
 * v1.7 Phase 2 — ReviewCard 复习卡片 (翻转 + SM-2 评分)
 *
 * Props:
 *  - item:    复习项 (含 entity_type/entity_id/due_at/...)
 *  - onGrade: (grade: 0-5) => void  评分回调
 *
 * 行为:
 *  - 正面: 显示 entity 标识 + "?" 提示 (点击翻转)
 *  - 背面: 显示 entity 详情 + 0-5 评分按钮 (SM-2: 0=完全忘记, 5=完美记忆)
 *  - 翻转动画用 CSS transform
 *
 * 验收 2: 评分后间隔按 SM-2 延长 (由父组件 onGrade → submitGrade → refresh 体现)
 */

export interface ReviewCardProps {
  item: ReviewItem;
  onGrade: (grade: number) => void;
}

const GRADE_LABELS: Record<number, string> = {
  0: '完全忘记',
  1: '毫无印象',
  2: '勉强记得',
  3: '回忆困难',
  4: '轻松回忆',
  5: '瞬间记忆',
};

export function ReviewCard({ item, onGrade }: ReviewCardProps) {
  const [flipped, setFlipped] = useState(false);

  const handleGrade = (g: number, e: React.MouseEvent) => {
    e.stopPropagation();
    onGrade(g);
  };

  return (
    <div
      className="review-card"
      style={cardStyle}
      onClick={() => setFlipped(!flipped)}
      role="button"
      tabIndex={0}
      aria-label={`复习卡片 ${item.entity_type}/${item.entity_id}, 点击翻转`}
    >
      {!flipped ? (
        <div style={frontStyle}>
          <div style={entityTypeStyle}>{item.entity_type}</div>
          <div style={entityIdStyle}>{item.entity_id}</div>
          <div style={hintStyle}>点击查看 · ?</div>
          {item.last_grade !== null && (
            <div style={lastGradeStyle}>上次评分: {item.last_grade}</div>
          )}
        </div>
      ) : (
        <div style={backStyle}>
          <div style={entityTypeStyle}>{item.entity_type}</div>
          <div style={entityIdStyle}>{item.entity_id}</div>
          <div style={metaStyle}>
            <span>重复 {item.repetitions}</span>
            <span>间隔 {item.interval}天</span>
            <span>难度 {item.easiness.toFixed(2)}</span>
          </div>
          <div style={gradeLabelStyle}>评分 (SM-2)</div>
          <div style={gradeBtnRowStyle}>
            {[0, 1, 2, 3, 4, 5].map((g) => (
              <button
                key={g}
                type="button"
                style={gradeBtnStyle(g)}
                onClick={(e) => handleGrade(g, e)}
                title={GRADE_LABELS[g]}
                aria-label={`评分 ${g} - ${GRADE_LABELS[g]}`}
              >
                {g}
              </button>
            ))}
          </div>
          <div style={gradeHintStyle}>
            {[0, 1, 2].map((g) => GRADE_LABELS[g]).join(' / ')} → 重置 ·{' '}
            {[3, 4, 5].map((g) => GRADE_LABELS[g]).join(' / ')} → 延长
          </div>
        </div>
      )}
    </div>
  );
}

// ── styles (tech-style: 青色主调, 透明卡片) ───────────────────────
const cardStyle: React.CSSProperties = {
  position: 'relative',
  background: 'var(--bg-card, #0d0d14)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  padding: 'var(--space-4, 16px)',
  cursor: 'pointer',
  transition: 'transform 0.2s, border-color 0.2s, box-shadow 0.2s',
  minHeight: 160,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  alignItems: 'center',
};

const frontStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
};

const backStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
  width: '100%',
};

const entityTypeStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
};

const entityIdStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  color: 'var(--text-primary, #f0f0f7)',
  fontFamily: 'monospace',
  wordBreak: 'break-all',
  textAlign: 'center',
};

const hintStyle: React.CSSProperties = {
  fontSize: 24,
  color: 'var(--text-muted, #5b5b72)',
  marginTop: 'var(--space-2, 8px)',
};

const lastGradeStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

const metaStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-3, 12px)',
  fontSize: 11,
  color: 'var(--text-secondary, #9a9ab2)',
  fontFamily: 'monospace',
};

const gradeLabelStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted, #888)',
  marginTop: 'var(--space-2, 8px)',
};

const gradeBtnRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-1, 4px)',
  marginTop: 'var(--space-1, 4px)',
};

function gradeBtnStyle(g: number): React.CSSProperties {
  // 0-2 红色系 (重置), 3 黄色, 4-5 青色 (延长)
  const color = g < 3 ? 'var(--color-error, #ef4444)' : g === 3 ? 'var(--color-warning, #eab308)' : 'var(--color-ai, #00d4e0)';
  return {
    width: 36,
    height: 36,
    fontSize: 14,
    fontWeight: 600,
    border: `1px solid ${color}`,
    borderRadius: 'var(--radius-sm, 4px)',
    background: 'transparent',
    color,
    cursor: 'pointer',
    transition: 'all 0.15s',
  };
}

const gradeHintStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-muted, #5b5b72)',
  textAlign: 'center',
  marginTop: 'var(--space-1, 4px)',
  lineHeight: 1.4,
};

export default ReviewCard;
