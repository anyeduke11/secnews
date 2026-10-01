/**
 * rejectionReasons — 拒收 flag 词典 + reason 解析 (2026-10-01 spec §3)。
 *
 * 词典是兜底层: LLM explain (quality_rejection_log.explain 列) 未生成/
 * 失败时, 前端仍可展示每条拒因的可读解释。多 flag 组合全列出,
 * 首项 (主拒因) 由展示层加粗。
 */
export const REJECTION_FLAG_LABELS: Record<string, string> = {
  content_hash_duplicate: '与已收录内容重复',
  url_duplicate: '链接已收录过',
  similar_title_duplicate: '标题与已有条目高度相似',
  category_mismatch: '内容与分类关键词不匹配',
  title_summary_inconsistent: '标题与摘要对不上',
  empty_summary: '摘要为空',
  empty_title: '标题为空',
  author_unknown: '作者无法验证',
  title_spam_words: '标题含营销/低质词',
  noise_title: '标题属噪音内容(备案/版权/招聘等)',
};

/** reason 字符串 → flag 数组。兼容两种生产形态:
 *  "['a', 'b']" (strict_mode/score_below_min) 与 "flags=['a']" (duplicate)。
 *  非 flag 词 (flags/=) 不在词典且不匹配 snake_case 白名单式提取规则时丢弃。 */
export function parseRejectionFlags(reason: string): string[] {
  if (!reason) return [];
  const known = new Set(Object.keys(REJECTION_FLAG_LABELS));
  const tokens = reason.match(/[a-z][a-z_]+/g) ?? [];
  // 只保留: 词典已知 flag 或形如 gate flag 的 snake_case 词 (未知新 flag 原样展示的前提)
  return tokens.filter(t => t !== 'flags' && (known.has(t) || t.includes('_')));
}

/** flag → 中文标签; 未知 flag 原样返回。 */
export function flagLabel(flag: string): string {
  return REJECTION_FLAG_LABELS[flag] ?? flag;
}
