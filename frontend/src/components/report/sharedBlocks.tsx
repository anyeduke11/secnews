/**
 * report/sharedBlocks — 周报 / 月报渲染逐字相同的纯展示片段。
 *
 * 只收录两份产物 DOM/class/文案完全一致的部分; 语义不同的部分 (统计行口径与
 * 栅格间距、快导航间距与序号分隔符、看点摘要的周/月前缀、往期面板、文章行)
 * 仍各留各文件, 不做合并, 以免改变周报与月报之间的差异。
 */
import { catColors, renderFormatted } from './utils';

/** 本期主线 (周报 / 月报逐字相同) */
export function ReportMainTheme({ mainTheme }: { mainTheme: string }) {
  return (
    <div
      className="p-5 rounded-lg"
      style={{
        backgroundColor: 'color-mix(in srgb, var(--accent) 6%, transparent)',
        borderLeft: '4px solid var(--accent)',
      }}
    >
      <h4 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color: 'var(--accent)' }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 17 10 11 13 14 19 8" />
          <polyline points="14 8 19 8 19 13" />
        </svg>
        本期主线
      </h4>
      <div className="text-xs leading-relaxed whitespace-pre-line" style={{ color: 'var(--text-secondary)', lineHeight: 1.8 }}>
        {renderFormatted(mainTheme)}
      </div>
    </div>
  );
}

/** 看点主题折叠头部按钮 (周报 / 月报逐字相同) */
export function ReportHighlightHeader({
  index,
  title,
  count,
  expanded,
  onToggle,
}: {
  index: number;
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between px-4 py-3 text-left focus-ring transition-colors hover:bg-[var(--bg-hover)]"
      style={{ borderBottom: expanded ? '1px solid var(--border-color)' : 'none' }}
    >
      <div className="flex items-center gap-3">
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
          style={{
            backgroundColor: `color-mix(in srgb, ${catColors[index % catColors.length]} 13%, transparent)`,
            color: catColors[index % catColors.length],
          }}
        >
          {String(index + 1).padStart(2, '0')}
        </span>
        <div>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {title}
          </span>
          <span className="text-[10px] ml-2 font-mono" style={{ color: 'var(--text-muted)' }}>
            {count} 篇
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {expanded ? '收起' : '展开'}
        </span>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          style={{
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s',
            color: 'var(--text-muted)',
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </button>
  );
}
