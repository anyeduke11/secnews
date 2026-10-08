import { describe, it, expect } from 'vitest';
import {
  getCategoryColor,
  getCategoryLabel,
  formatRelativeTime,
  getQualityColor,
  plainSummary,
} from '../types';

describe('getCategoryColor', () => {
  it('returns correct color for known categories', () => {
    expect(getCategoryColor('ai')).toBe('#00bcd4');
    expect(getCategoryColor('security')).toBe('#e85d5d');
    expect(getCategoryColor('finance')).toBe('#f0c929');
    expect(getCategoryColor('startup')).toBe('#7c6aff');
    // DEV-0178: bid 已全线下线
    expect(getCategoryColor('github')).toBe('#9b8bff');
  });

  it('returns fallback color for unknown category', () => {
    expect(getCategoryColor('unknown')).toBe('#7A6F5C');
    expect(getCategoryColor('')).toBe('#7A6F5C');
  });
});

describe('getCategoryLabel', () => {
  it('returns Chinese label for known categories', () => {
    expect(getCategoryLabel('ai')).toBe('科技 / AI');
    expect(getCategoryLabel('security')).toBe('网络安全');
    expect(getCategoryLabel('finance')).toBe('金融 / 投资');
    expect(getCategoryLabel('startup')).toBe('独立开发 / 创业');
    // DEV-0178: bid 已全线下线
    expect(getCategoryLabel('github')).toBe('GitHub 项目');
  });

  it('returns raw string for unknown category', () => {
    expect(getCategoryLabel('unknown')).toBe('unknown');
  });
});

describe('formatRelativeTime', () => {
  it('returns "刚刚" for less than 1 minute ago', () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe('刚刚');
  });

  it('returns minutes format for < 60 minutes ago', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe('5分钟前');
  });

  it('returns hours format for < 24 hours ago', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatRelativeTime(twoHoursAgo)).toBe('2小时前');
  });

  it('returns days format for < 7 days ago', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86400 * 1000).toISOString();
    expect(formatRelativeTime(threeDaysAgo)).toBe('3天前');
  });

  it('returns date format for >= 7 days ago', () => {
    const tenDaysAgo = new Date(Date.now() - 10 * 86400 * 1000);
    const result = formatRelativeTime(tenDaysAgo.toISOString());
    expect(result).toMatch(/\d+\/\d+ \d{2}:\d{2}/);
  });
});

describe('getQualityColor', () => {
  it('returns green for score >= 80', () => {
    expect(getQualityColor(80)).toBe('#2F7D4F');
    expect(getQualityColor(100)).toBe('#2F7D4F');
  });

  it('returns yellow for 50 <= score < 80', () => {
    expect(getQualityColor(50)).toBe('#8A6400');
    expect(getQualityColor(79)).toBe('#8A6400');
  });

  it('returns red for score < 50', () => {
    expect(getQualityColor(49)).toBe('#A32014');
    expect(getQualityColor(0)).toBe('#A32014');
  });

  it('returns fallback for null/undefined', () => {
    expect(getQualityColor(null)).toBe('#7A6F5C');
    expect(getQualityColor(undefined)).toBe('#7A6F5C');
  });
});

describe('plainSummary', () => {
  it('strips HTML tags and source-dated prefix (真实 RSS 残留样本)', () => {
    const raw = '<p>IT之家 10 月 8 日消息，据《商业内幕》今天（8 日）凌晨报道，<strong>OpenAI 一边反复警告风险</strong>，一边全速推进。</p>';
    expect(plainSummary(raw)).toBe(
      '据《商业内幕》今天（8 日）凌晨报道，OpenAI 一边反复警告风险，一边全速推进。',
    );
  });

  it('decodes common named and numeric entities', () => {
    expect(plainSummary('A &amp; B &#39;quoted&#39; C&#x4e2d;')).toBe("A & B 'quoted' C中");
  });

  it('keeps plain text untouched', () => {
    expect(plainSummary('已经是干净的摘要。')).toBe('已经是干净的摘要。');
  });

  it('returns empty for null/undefined/blank', () => {
    expect(plainSummary(null)).toBe('');
    expect(plainSummary(undefined)).toBe('');
    expect(plainSummary('<p>  </p>')).toBe('');
  });

  it('truncates at last sentence boundary within limit', () => {
    const long = '第一句。'.repeat(100); // 400 字, 100 个句号
    const out = plainSummary(long, 260);
    expect(out.length).toBeLessThanOrEqual(260);
    expect(out.endsWith('。')).toBe(true);
    expect(out).not.toContain('……');
  });

  it('hard-truncates with ellipsis when no sentence boundary', () => {
    const out = plainSummary('无标点'.repeat(200), 50);
    expect(out.length).toBeLessThanOrEqual(52); // 50 + 省略号
    expect(out.endsWith('……')).toBe(true);
  });
});
