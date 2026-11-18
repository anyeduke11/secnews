/**
 * feedModel 单测 — 资讯域纯函数契约
 *
 * 测试意图 (Rule 9):
 * - safeHref 是 XSS 边界: 只放行 http(s), 任何 javascript:/data: 都必须返回 null,
 *   否则 feed 行会把后端脏 URL 渲染成可点击链接 (安全回归必须让此测试失败)
 * - relTime / heatOf 是展示兜底: 脏时间戳不得抛错, 热度必须夹在 0–5
 *   (越界会让 mini-heat 渲染出 6 个格子, 破坏版式)
 */
import { describe, it, expect } from 'vitest';
import { heatCells, heatOf, labelOf, relTime, safeHref, tagColorOf, CHANNEL_DEFS, TIME_RANGE_DEFS } from './feedModel';
import type { HotspotItem } from '../../../types';

describe('safeHref — URL 白名单', () => {
  it('放行 http / https', () => {
    expect(safeHref('https://example.com/a?b=1')).toBe('https://example.com/a?b=1');
    expect(safeHref('  http://example.com  ')).toBe('http://example.com');
  });

  it('拒绝 javascript: / data: / 相对路径 / 空值', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull();
    expect(safeHref('data:text/html,<script>')).toBeNull();
    expect(safeHref('/relative/path')).toBeNull();
    expect(safeHref('')).toBeNull();
    expect(safeHref(null)).toBeNull();
    expect(safeHref(undefined)).toBeNull();
  });
});

describe('relTime — 相对时间', () => {
  it('非法时间戳回退 "--" (不抛错)', () => {
    expect(relTime(undefined)).toBe('--');
    expect(relTime(null)).toBe('--');
    expect(relTime('not-a-date')).toBe('--');
  });

  it('按分钟 / 小时 / 天分级', () => {
    expect(relTime(new Date().toISOString())).toBe('刚刚');
    expect(relTime(new Date(Date.now() - 5 * 60_000).toISOString())).toBe('5 分钟前');
    expect(relTime(new Date(Date.now() - 3 * 3600_000).toISOString())).toBe('3 小时前');
    expect(relTime(new Date(Date.now() - 26 * 3600_000).toISOString())).toBe('昨天');
  });
});

describe('heatOf / heatCells — 热度格夹取', () => {
  const item = (patch: Partial<HotspotItem>) => patch as unknown as HotspotItem;

  it('score 0–100 映射到 0–5 且越界夹取', () => {
    expect(heatOf(item({ score: 0 }))).toBe(0);
    expect(heatOf(item({ score: 50 }))).toBe(3); // Math.round(2.5) = 3
    expect(heatOf(item({ score: 100 }))).toBe(5);
    expect(heatOf(item({ score: 250 }))).toBe(5);
    expect(heatOf(item({ score: -30 }))).toBe(0);
  });

  it('无 score 时回落 quality_score', () => {
    expect(heatOf(item({ score: undefined, quality_score: 80 }))).toBe(4);
  });

  it('heatCells 永远 5 格', () => {
    expect(heatCells(0)).toEqual([false, false, false, false, false]);
    expect(heatCells(2)).toEqual([true, true, false, false, false]);
    expect(heatCells(5)).toEqual([true, true, true, true, true]);
  });
});

describe('分类标签', () => {
  it('已知分类取 CATEGORIES 文案', () => {
    expect(labelOf('security')).toBe('网络安全');
  });

  it('未知分类原样返回 (不静默变形)', () => {
    expect(labelOf('unknown_cat')).toBe('unknown_cat');
  });

  it('tagColorOf 走 --sn-* token', () => {
    expect(tagColorOf('security')).toBe('var(--sn-cat-sec)');
    expect(tagColorOf('paper')).toBe('var(--sn-cat-vc)');
  });
});

describe('频道 / 时间窗定义', () => {
  it('频道表首项为全部, 且已剔除 bid (DEV-0175)', () => {
    expect(CHANNEL_DEFS[0].id).toBe('all');
    expect(CHANNEL_DEFS.some(c => c.id === 'bid')).toBe(false);
  });

  it('时间窗只用后端枚举内的 4 个值 (1d 会 400)', () => {
    expect(TIME_RANGE_DEFS.map(t => t.id)).toEqual(['24h', '3d', '7d', '30d']);
  });
});