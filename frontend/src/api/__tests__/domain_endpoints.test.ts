/**
 * B3 域 API 端点契约 (frontend 重构 V1 · §5 数据层)
 *
 * 域模块是 URL + method + body 的唯一搬运点, 组件层不再直调 lib/api。
 * 这些断言锁定"搬过来的 URL 一个字符都没变", 任一侧改错即红:
 *  - report / security / skills 三个 B3 新建/收敛模块
 *
 * 模式: mock lib/api, 断言底层调用参数 (经 getJSON/postJSON/apiFetch 透传)。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getJSON: vi.fn(),
  postJSON: vi.fn(),
  apiFetch: vi.fn(),
}));

vi.mock('../../lib/api', () => ({
  getJSON: mocks.getJSON,
  postJSON: mocks.postJSON,
  apiFetch: mocks.apiFetch,
}));

import {
  getDailyOverview,
  getWeeklyAvailable,
  getWeeklyOverview,
  getMonthlyAvailable,
  getMonthlyOverview,
} from '../report';
import {
  getSecurityGraph,
  getComplianceFrameworks,
  getComplianceMatrix,
  getComplianceControls,
  getCveAttackMapping,
  getCveHeatmap,
  getSecurityEntityRelated,
} from '../security';
import {
  runSkill,
  submitSkillFeedback,
  validateSkillDraft,
  createSkill,
  listSkills,
  getSkillCountsBySource,
  createSkillItem,
  updateSkillItem,
  deleteSkillItem,
  updateKnowledgeSkill,
} from '../skills';

beforeEach(() => {
  mocks.getJSON.mockReset().mockResolvedValue({ ok: true });
  mocks.postJSON.mockReset().mockResolvedValue({ ok: true });
  mocks.apiFetch.mockReset().mockResolvedValue({ ok: true });
});

describe("report 域: /api/reports/*", () => {
  it("日报/月报可用列表走固定路径", async () => {
    await getDailyOverview();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/reports/daily/overview');

    await getWeeklyAvailable();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/reports/weekly/available');

    await getMonthlyAvailable();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/reports/monthly/available');
  });

  it("周报/月报概览把选择参数拼进 query", async () => {
    await getWeeklyOverview('2026-11-09');
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/reports/weekly/overview?week_start=2026-11-09');

    await getMonthlyOverview(-2);
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/reports/monthly/overview?offset=-2');
  });
});

describe("security 域: /api/security|compliance|cve/*", () => {
  it("图谱默认 view=full, 可切 view 并透传 AbortSignal (竞态取消依赖它)", async () => {
    await getSecurityGraph();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/security/graph?view=full', { signal: undefined });

    const ac = new AbortController();
    await getSecurityGraph('attack', { signal: ac.signal });
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/security/graph?view=attack', { signal: ac.signal });
  });

  it("合规矩阵把 event_types / frameworks 逗号拼接, 空数组不落 query", async () => {
    await getComplianceFrameworks();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/compliance/frameworks');

    await getComplianceMatrix(['ransomware', 'phishing'], ['等保', '关基']);
    expect(mocks.getJSON).toHaveBeenLastCalledWith(
      '/api/compliance/matrix?event_types=ransomware%2Cphishing&frameworks=%E7%AD%89%E4%BF%9D%2C%E5%85%B3%E5%9F%BA',
    );

    await getComplianceMatrix([]);
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/compliance/matrix?');

    await getComplianceControls('勒索 软件');
    expect(mocks.getJSON).toHaveBeenLastCalledWith(
      `/api/compliance/controls/${encodeURIComponent('勒索 软件')}`,
    );
  });

  it("CVE 攻击映射空入参直接返回空结果, 不发请求 (冷启动护栏)", async () => {
    const empty = await getCveAttackMapping([]);
    expect(empty).toEqual({ techniques: [], total_cves: 0, matched_cves: 0 });
    expect(mocks.getJSON).not.toHaveBeenCalled();

    await getCveAttackMapping(['CVE-2026-1', 'CVE-2026-2']);
    expect(mocks.getJSON).toHaveBeenLastCalledWith(
      `/api/cve/attack-mapping?cve_ids=${encodeURIComponent('CVE-2026-1,CVE-2026-2')}`,
    );
  });

  it("热力图默认 12 周; 实体关联编码 id + depth", async () => {
    await getCveHeatmap();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/cve/heatmap?weeks=12');

    await getCveHeatmap(26);
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/cve/heatmap?weeks=26');

    await getSecurityEntityRelated('cve/2026-1', 2);
    expect(mocks.getJSON).toHaveBeenLastCalledWith(
      `/api/security/entities/${encodeURIComponent('cve/2026-1')}/related?depth=2`,
    );
  });
});

describe("skills 域: 技能运行 / 反馈 / 构建 / CRUD", () => {
  it("run 与 feedback 走 skill-registry 子路径, id 编码", async () => {
    await runSkill('sk 01');
    expect(mocks.postJSON).toHaveBeenLastCalledWith(
      `/api/skill-registry/${encodeURIComponent('sk 01')}/run`,
      { inputs: null },
    );

    await submitSkillFeedback('run 01', 5);
    expect(mocks.postJSON).toHaveBeenLastCalledWith(
      `/api/skill-registry/runs/${encodeURIComponent('run 01')}/feedback`,
      { score: 5, comment: '' },
    );
  });

  it("builder 校验/创建 body 原样透传", async () => {
    const payload = { name: 'demo' };
    await validateSkillDraft(payload);
    expect(mocks.postJSON).toHaveBeenLastCalledWith('/api/skill-builder/validate', { payload });

    await createSkill({ name: 'demo2' });
    expect(mocks.postJSON).toHaveBeenLastCalledWith('/api/skill-builder', { name: 'demo2' });
  });

  it("列表/计数走 GET, 写操作走对应 method", async () => {
    const params = new URLSearchParams({ limit: '20' });
    await listSkills(params, { signal: undefined });
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/skills?limit=20', { signal: undefined });

    await getSkillCountsBySource();
    expect(mocks.getJSON).toHaveBeenLastCalledWith('/api/skills/count_by_source');

    await createSkillItem({ name: 'x' });
    expect(mocks.postJSON).toHaveBeenLastCalledWith('/api/skills', { name: 'x' });

    await updateSkillItem(7, { name: 'y' });
    expect(mocks.apiFetch).toHaveBeenLastCalledWith('/api/skills/7', {
      method: 'PATCH',
      body: JSON.stringify({ name: 'y' }),
    });

    await deleteSkillItem(7);
    expect(mocks.apiFetch).toHaveBeenLastCalledWith('/api/skills/7', { method: 'DELETE' });

    await updateKnowledgeSkill(9, { starred: true });
    expect(mocks.apiFetch).toHaveBeenLastCalledWith('/api/knowledge/skills/9', {
      method: 'PATCH',
      body: JSON.stringify({ starred: true }),
    });
  });
});