/**
 * ReviewFlipCard — 复习进度条 + SM-2 翻转卡片 (正面标题 / 背面内容 + 评分),
 * B5 从 ReviewMode 原样抽出, DOM、class 与 aria 文案未改。
 */
import { GRADE_LABELS, truncate, type KnowledgeDetail } from './reviewModel';

/** 进度条 */
export function ReviewProgress({ index, total }: { index: number; total: number }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-2.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          复习进度
        </span>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          第 {index + 1} / {total} 张
        </span>
      </div>
      <div
        className="w-full h-1.5 rounded-full overflow-hidden"
        style={{ backgroundColor: 'var(--border-color)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${((index + 1) / total) * 100}%`,
            backgroundColor: 'var(--color-info)',
          }}
        />
      </div>
    </div>
  );
}

/** 翻转卡片 (正面标题 / 背面内容 + 评分按钮) */
export function ReviewFlipCard({ flipped, onFlip, detail, title, content, hasDetail, submitting, onGrade }: {
  flipped: boolean;
  onFlip: () => void;
  detail: KnowledgeDetail | null;
  title: string;
  content: string;
  hasDetail: boolean;
  submitting: boolean;
  onGrade: (grade: number) => void;
}) {
  return (
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
            onClick={onFlip}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFlip(); } }}
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
              {title}
            </h4>

            {/* 标签 */}
            {detail && detail.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 justify-center mb-3">
                {detail.tags.slice(0, 5).map(tag => (
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
              {detail?.domain && (
                <span>{detail.domain}</span>
              )}
              {detail?.source && (
                <>
                  {detail.domain && <span aria-hidden="true">·</span>}
                  <span>{detail.source}</span>
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
                {title}
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
                {hasDetail && content
                  ? truncate(content, 600)
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
                    onClick={() => onGrade(g.value)}
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
  );
}
