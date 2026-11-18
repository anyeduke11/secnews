/**
 * skillBuilderModel — SkillBuilder 向导的纯类型 / 常量 / 校验计算 (B5.6 拆分自 SkillBuilder)。
 *
 * 只放无 React 依赖的内容, 供容器 (SkillBuilder.tsx) 与展示区块共享。
 */
import type { SkillCategory, SkillTypeCode } from '../../types/skill';

/** Schema 字段可选的 Python 类型。 */
export const PYTHON_TYPES = ['str', 'int', 'float', 'bool', 'list', 'dict', 'Any'];

/** 向导表单草稿 (字段与 POST /api/skill-builder payload 对齐)。 */
export interface DraftPayload {
  id: string;
  name: string;
  desc: string;
  category: SkillCategory;
  skill_type: SkillTypeCode;
  runner: 'builtin';
  timeout_seconds: number;
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  prompt_template: string;
  target_module: string;
  target_class: string;
  target_method: string;
}

/** 草稿初值 (Step 1 起点)。 */
export const EMPTY_DRAFT: DraftPayload = {
  id: '',
  name: '',
  desc: '',
  category: 'operations',
  skill_type: 'A',
  runner: 'builtin',
  timeout_seconds: 60,
  input_schema: {},
  output_schema: {},
  prompt_template: '',
  target_module: '',
  target_class: '',
  target_method: '',
};

/** 向导步号 (1~4)。 */
export type Step = 1 | 2 | 3 | 4;

/** 步进条各步标题。 */
export const STEP_TITLES: Record<Step, string> = {
  1: '基本信息',
  2: 'Schema 与 Prompt',
  3: 'Target 引用',
  4: '复核 & 保存',
};

/** Step 1 通过条件: id 至少 3 位且显示名非空。 */
export function isStep1Valid(draft: DraftPayload): boolean {
  return draft.id.length >= 3 && draft.name.length > 0;
}

/** Step 2 通过条件: C/D 类必须填 prompt_template (A 类巡检免)。 */
export function isStep2Valid(draft: DraftPayload): boolean {
  return draft.skill_type !== 'A' ? draft.prompt_template.length > 0 : true;
}

/** Step 3 通过条件: target_module 与 target_method 均非空。 */
export function isStep3Valid(draft: DraftPayload): boolean {
  return draft.target_module.length > 0 && draft.target_method.length > 0;
}
