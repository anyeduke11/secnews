/**
 * ReviewComplete — 复习完成屏幕与统计面板 (B5 从 ReviewMode 原样抽出)
 */
import { Icon } from '../../Icon';
import { ReviewHeader } from './ReviewHeader';

export function ReviewComplete({ total, grades, onRestart }: {
  total: number;
  grades: number[];
  onRestart: () => void;
}) {
  const passCount = grades.filter(g => g >= 3).length;
  const failCount = grades.filter(g => g < 3).length;
  const avgGrade = grades.length > 0
    ? (grades.reduce((a, b) => a + b, 0) / grades.length).toFixed(1)
    : '—';

  return (
    <div className="space-y-3">
      <ReviewHeader />
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
          本次共复习 {total} 张卡片
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
          onClick={onRestart}
        >
          继续复习
        </button>
      </div>
    </div>
  );
}
