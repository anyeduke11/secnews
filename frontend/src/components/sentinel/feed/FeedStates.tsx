/**
 * FeedStates — 资讯主列的四态面板 (骨架 / 错误 / 空态), B4 从 SentinelHomePage 抽出。
 * 四个分支 (加载/错误/范围内空/关键词空) 共用同一视觉语言, 不再在页面内散落 SVG。
 *
 * D7 收口: 空态/错误态四个分支收敛为单一 FeedPanel (圆环图标 + 标题 + 说明 + 可选 CTA),
 * 同一枚 SVG 只保留一份定义 —— 拆分后每个分支各带一份图标是包体积回弹的主因之一。
 */
import type { ReactNode } from 'react';
import { ICON_ARROW_D } from './feedModel';

/** 空态圆环: 星形 (收藏/精选语义) 与 时钟 (时间/加载语义) */
const RING_STAR = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2.5l2 4.5 4.5.7-3.2 3.2.7 4.8L10 13.6l-4 2.1.7-4.8L3.5 7.7 8 7l2-4.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
);
const RING_CLOCK = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 5v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" /></svg>
);
const CTA_REFRESH = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7a4.5 4.5 0 1 1 1.3 3.2M2.5 7V4M2.5 7h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

/**
 * 统一空态/错误态面板。
 * icon: star=精选/收藏语义, clock=时间/加载语义; cta 省略时只出图标+文案。
 */
export function FeedPanel({ icon, title, desc, cta }: {
  icon: 'star' | 'clock';
  title: string;
  desc: ReactNode;
  cta?: { label: string; onClick: () => void; icon: 'refresh' | 'arrow' };
}) {
  return (
    <div className="empty-panel">
      <div className="empty-ring" aria-hidden="true">{icon === 'star' ? RING_STAR : RING_CLOCK}</div>
      <h3>{title}</h3>
      <p>{desc}</p>
      {cta && (
        <button className="empty-cta" onClick={cta.onClick}>{cta.label}
          {cta.icon === 'refresh' ? CTA_REFRESH : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d={ICON_ARROW_D} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          )}
        </button>
      )}
    </div>
  );
}

export function FeedSkeleton() {
  return (
    <div className="story-top" aria-busy="true">
      <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" /><div className="skel-line w2" />
    </div>
  );
}

export function FeedErrorPanel({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <FeedPanel
      icon="clock"
      title="数据加载失败"
      desc={`${error} — 请确认后端服务运行在 127.0.0.1:8000。`}
      cta={{ label: '重试', onClick: onRetry, icon: 'refresh' }}
    />
  );
}

export function FeedEmptyPanel({ keyword, collectMinutes, onCollect }: {
  keyword: string;
  collectMinutes: number;
  onCollect: () => void;
}) {
  return (
    <FeedPanel
      icon="star"
      title={keyword ? '没有匹配的条目' : '该范围暂无收录'}
      desc={keyword
        ? `关键词「${keyword}」在当前频道与时间窗内没有命中，换个说法或放宽时间范围试试。`
        : `采集管线每 ${collectMinutes} 分钟自动运行一轮，也可手动触发一轮立即补采。`}
      cta={{ label: '立即采集', onClick: onCollect, icon: 'arrow' }}
    />
  );
}
