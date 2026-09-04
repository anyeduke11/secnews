/**
 * Skill Registry (v0.8 Phase A) 前端类型与标签常量。
 *
 * 对齐 backend/api/skill_registry_api.py 序列化契约 (路径 /api/skill-registry,
 * 注意与 Phase 41 技能库的 /api/skills 是两张不同的表):
 *   - 列表项 = _summary(): 下述 SkillSummary 全字段, snake_case
 *   - 详情 = _detail(): 全字段 + input/output schema (+ C/D 类 prompt 全文)
 *
 * 注: CATEGORY_LABELS / SKILL_TYPE_LABELS 为 label 常量 (运行时导出),
 * 属任务 A4 显式交付物, 特例突破 types/ 纯类型约定。
 */

export type SkillCategory = 'operations' | 'compliance' | 'analysis' | 'report';

/** §2 技能分类法: A 巡检 / B 查询 / C 报告 / D 分析 (C/D 可携带 prompt) */
export type SkillTypeCode = 'A' | 'B' | 'C' | 'D';

/** GET /api/skill-registry 列表项 — 后端 _summary() 一一对应 */
export interface SkillSummary {
  id: string;
  name: string;
  desc: string;
  category: SkillCategory;
  skill_type: SkillTypeCode;
  runner: string;
  timeout_seconds: number;
  feature_gate: string | null;
  default_enabled: boolean;
  enabled: boolean;
  /** C/D 类为 true (详情接口才返回 prompt_template 全文) */
  has_prompt: boolean;
}

/** GET /api/skill-registry/{id} 详情 — 列表全字段 + schema (+ prompt) */
export interface SkillDetail extends SkillSummary {
  /** 字段名 → 类型名 (后端把 Python type 转 __name__ 字符串) */
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  /** 仅 C/D 类 (has_prompt=true) 返回 */
  prompt_template?: string;
}

/** skill_runs 行 (B6: GET /{id}/runs 与 GET /runs/{run_id}) — migration 091 对齐 */
export interface SkillRun {
  run_id: string;
  ticket_id: string | null;
  skill_id: string;
  /** 'running' | 'succeeded' | 'partial' | 'failed' */
  status: string;
  phase: string | null;
  inputs: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

/** feedback_log 行 (B6: POST /runs/{run_id}/feedback 返回) — migration 093 对齐 */
export interface SkillFeedback {
  id: number;
  skill_run_id: string;
  skill_id: string;
  /** 1-5 整数 (👍=5 / 👎=1) */
  score: number;
  comment: string;
  created_at: string;
}

/** 类别中文标签 — 与后端 category 枚举对齐 */
export const CATEGORY_LABELS: Record<SkillCategory, string> = {
  operations: '安全运营',
  compliance: '合规审计',
  analysis: '事件分析',
  report: '报告生成',
};

/** 技能类型中文标签 — §2 分类法 */
export const SKILL_TYPE_LABELS: Record<SkillTypeCode, string> = {
  A: '巡检',
  B: '查询',
  C: '报告',
  D: '分析',
};
