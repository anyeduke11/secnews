import { describe, it, expect } from 'vitest';
import {
  getCategoryColor,
  getCategoryLabel,
  formatRelativeTime,
  getQualityColor,
  getBidStatusColor,
} from '../types';

describe('getCategoryColor', () => {
  it('returns correct color for known categories', () => {
    expect(getCategoryColor('ai')).toBe('#00bcd4');
    expect(getCategoryColor('security')).toBe('#e85d5d');
    expect(getCategoryColor('finance')).toBe('#f0c929');
    expect(getCategoryColor('startup')).toBe('#7c6aff');
    expect(getCategoryColor('bid')).toBe('#e8891a');
    expect(getCategoryColor('github')).toBe('#8b5cf6');
  });

  it('returns fallback color for unknown category', () => {
    expect(getCategoryColor('unknown')).toBe('#888899');
    expect(getCategoryColor('')).toBe('#888899');
  });
});

describe('getCategoryLabel', () => {
  it('returns Chinese label for known categories', () => {
    expect(getCategoryLabel('ai')).toBe('科技 / AI');
    expect(getCategoryLabel('security')).toBe('网络安全');
    expect(getCategoryLabel('finance')).toBe('金融 / 投资');
    expect(getCategoryLabel('startup')).toBe('独立开发 / 创业');
    expect(getCategoryLabel('bid')).toBe('招标资讯');
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
    expect(getQualityColor(80)).toBe('#00c96a');
    expect(getQualityColor(100)).toBe('#00c96a');
  });

  it('returns yellow for 50 <= score < 80', () => {
    expect(getQualityColor(50)).toBe('#f0c929');
    expect(getQualityColor(79)).toBe('#f0c929');
  });

  it('returns red for score < 50', () => {
    expect(getQualityColor(49)).toBe('#e85d5d');
    expect(getQualityColor(0)).toBe('#e85d5d');
  });

  it('returns fallback for null/undefined', () => {
    expect(getQualityColor(null)).toBe('#888899');
    expect(getQualityColor(undefined)).toBe('#888899');
  });
});

describe('getBidStatusColor', () => {
  it('returns correct colors for known statuses', () => {
    expect(getBidStatusColor('招标中')).toBe('#3b82f6');
    expect(getBidStatusColor('中标')).toBe('#00c96a');
    expect(getBidStatusColor('成交')).toBe('#00c96a');
    expect(getBidStatusColor('变更')).toBe('#f0c929');
    expect(getBidStatusColor('终止')).toBe('#e85d5d');
    expect(getBidStatusColor('询价')).toBe('#06b6d4');
    expect(getBidStatusColor('比选')).toBe('#06b6d4');
  });

  it('returns fallback for null/undefined/unknown', () => {
    expect(getBidStatusColor(null)).toBe('#888899');
    expect(getBidStatusColor(undefined)).toBe('#888899');
    expect(getBidStatusColor('未知状态')).toBe('#888899');
  });
});