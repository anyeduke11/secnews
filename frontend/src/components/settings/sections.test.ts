/**
 * sections — R-15 (v0.8.8) 设置导航四组结构 (数据源 / 管道与门控 / AI 与模型 / 运维与诊断)
 * 断言意图: 导航分组是产品信息架构契约 — 四组固定、每段必须归属某组且不落单。
 */
import { describe, it, expect } from 'vitest';
import { SECTIONS, SECTION_GROUP_LABELS } from './sections';

describe('settings sections — R-15 四组导航', () => {
  it('分组标题固定为四组 (+ 总览不设标题)', () => {
    const labels = SECTION_GROUP_LABELS.filter(g => g.label).map(g => g.label);
    expect(labels).toEqual(['数据源', '管道与门控', 'AI 与模型', '运维与诊断']);
  });

  it('每个配置段都归属四组之一, 不出现孤立段', () => {
    const groups = new Set(SECTION_GROUP_LABELS.map(g => g.group));
    for (const s of SECTIONS) {
      expect(s.group).toBeTruthy();
      expect(groups.has(s.group)).toBe(true);
      // 除总览外, 任何段都不应挂在无标题组下 (否则导航里看不到入口)
      if (s.key !== 'overview') expect(s.group).not.toBe('overview');
    }
  });

  it('关键能力落在预期组: 模型 → AI, 采集 → 管道与门控, 维护 → 运维与诊断', () => {
    const groupOf = (key: string) => SECTIONS.find(s => s.key === key)?.group;
    expect(groupOf('models')).toBe('ai');
    expect(groupOf('collection')).toBe('pipeline');
    expect(groupOf('ops')).toBe('ops');
    // 信源通道与凭据同属数据源
    expect(groupOf('network')).toBe('sources');
    expect(groupOf('connectivity')).toBe('sources');
  });
});