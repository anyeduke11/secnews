/**
 * infoFilter.types — InfoFilterCard 拆分共享类型/常量 (纯搬运, 无行为)
 */

/** i18n t() 签名 (与 I18nContext 内实现一致) */
export type TFn = (
  key: string,
  paramsOrFallback?: Record<string, string | number> | string,
  fallback?: string,
) => string;

export const MATCH_KINDS = ['source_name', 'source_id', 'category', 'tag'] as const;

export type MatchKind = typeof MATCH_KINDS[number];

export type RuleType = 'deny' | 'allow';