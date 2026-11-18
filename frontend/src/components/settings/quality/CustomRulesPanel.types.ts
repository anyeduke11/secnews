/**
 * quality/CustomRulesPanel.types — CustomRulesPanel 内部类型与常量 (拆分自 CustomRulesPanel.tsx)
 *
 * 仅承载跨文件共用的纯类型/常量, 无运行时副作用。
 */

export interface CustomRule {
  id: number;
  name: string;
  rule_kind: 'expert' | 'semantic';
  match_kind: string;
  match_value: string;
  action: 'flag' | 'reject';
  deduction: number;
  scope_category: string;
  enabled: boolean;
}

export interface GateInfo {
  name: string;
  tier: 'hard' | 'soft';
  enabled: boolean;
}

export interface DryRunHit {
  item_id: string;
  title: string;
  deduction: number;
  reason: string;
}

export interface DryRunResult {
  sampled: number;
  expert: { reject_hits: DryRunHit[]; flag_hits: DryRunHit[] };
  semantic: { ran: number; cap: number; skipped: number; hits: DryRunHit[]; notes: string[] };
}

export const EXPERT_KINDS: ReadonlyArray<[string, string]> = [
  ['title_contains', '标题包含'],
  ['source_in', '来源属于(csv)'],
  ['category_equals', '分类等于'],
  ['url_matches', 'URL 正则'],
  ['summary_len_lt', '摘要短于(字符)'],
];

export interface FormState {
  name: string;
  rule_kind: 'expert' | 'semantic';
  match_kind: string;
  match_value: string;
  action: 'flag' | 'reject';
  deduction: number;
  scope_category: string;
}

export const EMPTY_FORM: FormState = {
  name: '', rule_kind: 'expert', match_kind: 'title_contains',
  match_value: '', action: 'flag', deduction: 10, scope_category: '',
};