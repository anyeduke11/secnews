/**
 * sections — 设置导航分组结构 (B6-b 按业务流重排: 数据接入 / AI 与偏好 / 系统与运维)
 * 断言意图: 导航分组是产品信息架构契约 — 分组固定、每段必须归属某组且不落单,
 *          且每段归属反映"业务流位置"而非技术层次。
 */
import { describe, it, expect } from 'vitest';
import { SECTIONS, SECTION_GROUP_LABELS } from './sections';

describe('settings sections — B6-b 业务流三组导航', () => {
  it('分组标题固定为三组 (+ 总览不设标题)', () => {
    const labels = SECTION_GROUP_LABELS.filter(g => g.label).map(g => g.label);
    expect(labels).toEqual(['数据接入', 'AI 与偏好', '系统与运维']);
  });

  it('每个配置段都归属三组之一, 不出现孤立段', () => {
    const groups = new Set(SECTION_GROUP_LABELS.map(g => g.group));
    for (const s of SECTIONS) {
      expect(s.group).toBeTruthy();
      expect(groups.has(s.group)).toBe(true);
      // 除总览外, 任何段都不应挂在无标题组下 (否则导航里看不到入口)
      if (s.key !== 'overview') expect(s.group).not.toBe('overview');
    }
  });

  it('关键能力落在业务流预期组: 采集/代理 → 数据接入, 模型/通用 → AI 与偏好, 同步/运维 → 系统与运维', () => {
    const groupOf = (key: string) => SECTIONS.find(s => s.key === key)?.group;
    expect(groupOf('collection')).toBe('ingest');
    expect(groupOf('network')).toBe('ingest');
    expect(groupOf('models')).toBe('intelligence');
    expect(groupOf('general')).toBe('intelligence');
    expect(groupOf('connectivity')).toBe('system');
    expect(groupOf('ops')).toBe('system');
  });
});