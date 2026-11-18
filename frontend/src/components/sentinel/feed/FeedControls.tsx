/**
 * FeedControls — 阅读模式/频道条 + 检索条 (搜索 / 时间窗 / URL 导入 / 计数)。
 * B4 从 SentinelHomePage 抽出: 纯展示 + 回调, 状态仍由页容器持有。
 *
 * D7 收口: 静态布局值下沉 CSS 类 (行内 style 只保留 sticky top —— DEV-0188 契约测试
 * 断言的就是 bars[1].style.top, 不能挪进 CSS)。
 */
import type { CSSProperties } from 'react';
import { CHANNEL_DEFS, TIME_RANGE_DEFS, type ReadMode } from './feedModel';
import { UrlImport } from './UrlImport';

export interface FeedModeBarProps {
  mode: ReadMode;
  onModeChange: (mode: ReadMode) => void;
  newsUnread: number;
  channel: string;
  onChannelChange: (channel: string) => void;
  total: number;
  categoryCounts: Record<string, number>;
}

export function FeedModeBar({ mode, onModeChange, newsUnread, channel, onChannelChange, total, categoryCounts }: FeedModeBarProps) {
  return (
    <div className="controlbar">
      <div className="modes" role="group" aria-label="阅读模式">
        {([['brief', '全量'], ['scan', '精选'], ['deep', '深度']] as const).map(([m, label]) => (
          <button key={m} className="mode-btn" aria-pressed={mode === m} onClick={() => onModeChange(m)}>{label}</button>
        ))}
        <button className="mode-btn mode-alert-on" aria-pressed={mode === 'alert'} onClick={() => onModeChange('alert')}>告警
          {newsUnread > 0 && <span className="alert-unread-badge" aria-label={`${newsUnread} 条未读告警`}>{newsUnread}</span>}
        </button>
      </div>
      <nav className="channels" aria-label="内容频道">
        {CHANNEL_DEFS.map(ch => {
          const n = ch.id === 'all' ? total : categoryCounts[ch.id] ?? 0;
          return (
            <button
              key={ch.id}
              className={`chip${channel === ch.id ? ' active' : ''}`}
              style={{ '--sn-dot': ch.color } as CSSProperties}
              aria-pressed={channel === ch.id}
              onClick={() => onChannelChange(ch.id)}
            >
              <i aria-hidden="true" />{ch.label}
              {n > 0 && <span className="num">{n}</span>}
            </button>
          );
        })}
      </nav>
    </div>
  );
}

export interface FeedSearchBarProps {
  keywordInput: string;
  onKeywordInput: (value: string) => void;
  onClearKeyword: () => void;
  timeRange: string;
  onTimeRangeChange: (timeRange: string) => void;
  onImported: () => void;
  scopeLabel: string;
  total: number;
  page: number;
  totalPages: number;
  favoriteCount: number;
  loadingPage: boolean;
}

export function FeedSearchBar(props: FeedSearchBarProps) {
  const {
    keywordInput, onKeywordInput, onClearKeyword, timeRange, onTimeRangeChange,
    onImported, scopeLabel, total, page, totalPages, favoriteCount, loadingPage,
  } = props;
  return (
    <div
      className="controlbar controlbar-search"
      style={{ top: 'calc(var(--sn-bandnav-h) + 52px)' }}
    >
      <div className="search-box search-box-feed">
        <span className="search-icon search-icon-feed" aria-hidden="true">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
        </span>
        <input
          type="search"
          name="sentinel-hotspot-search"
          value={keywordInput}
          onChange={e => onKeywordInput(e.target.value)}
          placeholder="搜索标题 / 摘要（中文按子串匹配）"
          aria-label="搜索热点关键词"
          autoComplete="off"
        />
        {keywordInput && (
          <button type="button" className="search-clear" aria-label="清空搜索" onClick={onClearKeyword}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        )}
      </div>

      <span className="time-range" role="group" aria-label="时间范围">
        {TIME_RANGE_DEFS.map(t => (
          <button
            key={t.id}
            type="button"
            className={`chip num${timeRange === t.id ? ' active' : ''}`}
            title={t.hint}
            aria-pressed={timeRange === t.id}
            onClick={() => onTimeRangeChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </span>

      <UrlImport onDone={onImported} />

      <span className="flash-count num feed-scope" title="时间窗语义以后端 TimeRange 为准；收藏数取自 /api/favorites（上限 1000 条）">
        {scopeLabel} {total} 篇 · 第 {page}/{totalPages} 页 · 收藏 ≤{favoriteCount}
        {loadingPage ? ' · 翻页中' : ''}
      </span>
    </div>
  );
}
