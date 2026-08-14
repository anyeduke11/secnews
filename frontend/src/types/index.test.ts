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

describe('getBidStatusColor', () => {
  it('returns correct colors for known statuses', () => {
    expect(getBidStatusColor('招标中')).toBe('#2C5F8A');
    expect(getBidStatusColor('中标')).toBe('#2F7D4F');
    expect(getBidStatusColor('成交')).toBe('#2F7D4F');
    expect(getBidStatusColor('变更')).toBe('#8A6400');
    expect(getBidStatusColor('终止')).toBe('#A32014');
    expect(getBidStatusColor('询价')).toBe('#0B6E6E');
    expect(getBidStatusColor('比选')).toBe('#0B6E6E');
  });

  it('returns fallback for null/undefined/unknown', () => {
    expect(getBidStatusColor(null)).toBe('#7A6F5C');
    expect(getBidStatusColor(undefined)).toBe('#7A6F5C');
    expect(getBidStatusColor('未知状态')).toBe('#7A6F5C');
  });
});