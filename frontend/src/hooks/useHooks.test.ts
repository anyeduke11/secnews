import { describe, it, expect, vi } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// ── formatRelativeTime ───────────────────────────────────────

describe('formatRelativeTime', () => {
  it('returns "刚刚" for current time', async () => {
    const { formatRelativeTime } = await import('../types');
    expect(formatRelativeTime(new Date().toISOString())).toBe('刚刚');
  });

  it('returns "刚刚" for very recent time', async () => {
    const { formatRelativeTime } = await import('../types');
    const tenSecondsAgo = new Date(Date.now() - 10 * 1000).toISOString();
    expect(formatRelativeTime(tenSecondsAgo)).toBe('刚刚');
  });

  it('returns minutes format for < 60 minutes ago', async () => {
    const { formatRelativeTime } = await import('../types');
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe('5分钟前');
  });

  it('returns hours format for < 24 hours ago', async () => {
    const { formatRelativeTime } = await import('../types');
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatRelativeTime(twoHoursAgo)).toBe('2小时前');
  });

  it('returns days format for < 7 days ago', async () => {
    const { formatRelativeTime } = await import('../types');
    const threeDaysAgo = new Date(Date.now() - 3 * 86400 * 1000).toISOString();
    expect(formatRelativeTime(threeDaysAgo)).toBe('3天前');
  });
});

// ── getCategoryColor / getCategoryLabel ──────────────────────

describe('CATEGORIES helpers', () => {
  it('all categories have valid hex colors', async () => {
    const { CATEGORIES } = await import('../types');
    for (const cat of CATEGORIES) {
      expect(cat.color).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it('all category labels are non-empty strings', async () => {
    const { CATEGORIES } = await import('../types');
    for (const cat of CATEGORIES) {
      expect(cat.label).toBeTruthy();
      expect(typeof cat.label).toBe('string');
    }
  });

  it('CATEGORY_MAP has all categories', async () => {
    const { CATEGORY_MAP, CATEGORIES } = await import('../types');
    for (const cat of CATEGORIES) {
      expect(CATEGORY_MAP[cat.id]).toEqual(cat);
    }
  });
});

// ── getBidStatusColor ────────────────────────────────────────

describe('getBidStatusColor', () => {
  it('returns valid hex for all known statuses', async () => {
    const { getBidStatusColor } = await import('../types');
    const statuses = ['招标中', '中标', '成交', '变更', '终止', '询价', '比选'];
    for (const s of statuses) {
      const color = getBidStatusColor(s);
      expect(color).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it('returns fallback for null/undefined/unknown', async () => {
    const { getBidStatusColor } = await import('../types');
    expect(getBidStatusColor(null)).toBe('#888899');
    expect(getBidStatusColor(undefined)).toBe('#888899');
    expect(getBidStatusColor('未知状态')).toBe('#888899');
  });
});

// ── getQualityColor ──────────────────────────────────────────

describe('getQualityColor', () => {
  it('returns fallback for undefined', async () => {
    const { getQualityColor } = await import('../types');
    expect(getQualityColor(undefined)).toBe('#888899');
  });

  it('returns green for high scores', async () => {
    const { getQualityColor } = await import('../types');
    expect(getQualityColor(95)).toBe('#00c96a');
  });

  it('returns red for low scores', async () => {
    const { getQualityColor } = await import('../types');
    expect(getQualityColor(20)).toBe('#e85d5d');
  });

  it('returns yellow for medium scores', async () => {
    const { getQualityColor } = await import('../types');
    expect(getQualityColor(65)).toBe('#f0c929');
  });
});

// ── CATEGORY_MAP edge cases ──────────────────────────────────

describe('CATEGORY_MAP edge cases', () => {
  it('returns fallback color for unknown category via getCategoryColor', async () => {
    const { getCategoryColor } = await import('../types');
    expect(getCategoryColor('nonexistent')).toBe('#888899');
  });

  it('returns raw string for unknown category via getCategoryLabel', async () => {
    const { getCategoryLabel } = await import('../types');
    expect(getCategoryLabel('custom_category')).toBe('custom_category');
  });
});