// frontend/src/components/HotspotCard.test.tsx
// Phase 6 — HotspotCard 热点卡片测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HotspotCard } from './HotspotCard';
import type { HotspotItem } from '../types';

const baseItem: HotspotItem = {
  id: 'h1',
  title: '某安全漏洞披露',
  summary: '某高危 CVE',
  source: 'cnvd',
  url: 'https://example.com/cve',
  category: 'security',
  published_at: '2026-07-21T08:00:00Z',
  quality_score: 85,
  quality_flags: [],
};

describe('HotspotCard', () => {
  it('renders the title', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    expect(screen.getByText('某安全漏洞披露')).toBeInTheDocument();
  });

  it('renders category label (网络安全)', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    expect(screen.getByText('网络安全')).toBeInTheDocument();
  });

  it('renders quality score when present', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    // 实际渲染: 彩色圆点, aria-label="quality 85"
    expect(screen.getByLabelText('quality 85')).toBeInTheDocument();
  });

  it('renders AI category label (科技/AI)', () => {
    render(<HotspotCard item={{ ...baseItem, category: 'ai' }} index={0} />);
    expect(screen.getByText(/科技/)).toBeInTheDocument();
  });

  it('renders source', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    expect(screen.getByText('cnvd')).toBeInTheDocument();
  });

  it('favorite button has 未收藏 label initially', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    expect(screen.getByLabelText('收藏')).toBeInTheDocument();
  });

  it('favorite button has 取消收藏 label when isFavorited=true', () => {
    render(<HotspotCard item={baseItem} index={0} isFavorited={true} />);
    expect(screen.getByLabelText('取消收藏')).toBeInTheDocument();
  });

  it('clicking star calls onToggleFavorite with the item', () => {
    const onToggle = vi.fn();
    render(
      <HotspotCard item={baseItem} index={0} onToggleFavorite={onToggle} />
    );
    fireEvent.click(screen.getByLabelText('收藏'));
    expect(onToggle).toHaveBeenCalledWith(baseItem);
  });

  it('does not throw when onToggleFavorite is undefined', () => {
    render(<HotspotCard item={baseItem} index={0} />);
    expect(() => fireEvent.click(screen.getByLabelText('收藏'))).not.toThrow();
  });

  it('shows quality flags in title attribute', () => {
    const item = { ...baseItem, quality_flags: ['noise', 'duplicate'] };
    render(<HotspotCard item={item} index={0} />);
    const article = screen.getByText('某安全漏洞披露').closest('article')!;
    expect(article.getAttribute('title')).toContain('flags: noise, duplicate');
  });

  it('omits title attribute when no quality_score', () => {
    const item = { ...baseItem, quality_score: undefined };
    render(<HotspotCard item={item} index={0} />);
    const article = screen.getByText('某安全漏洞披露').closest('article')!;
    expect(article.getAttribute('title')).toBeNull();
  });

  it('renders bid_status badge for bid category', () => {
    const item = { ...baseItem, category: 'bid' as const, bid_status: '招标中' };
    render(<HotspotCard item={item} index={0} />);
    expect(screen.getByText('招标中')).toBeInTheDocument();
  });
});
