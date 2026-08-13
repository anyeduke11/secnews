/**
 * report/utils — ReportPage 内联工具函数与常量。
 *
 * 拆自原 ReportPage.tsx (1401 行): 格式化 helper + 颜色映射常量。
 * 纯结构拆分, 实现与原文件逐字等价。
 */

/** Format ISO date as M/D (fallback: slice of the ISO string). */
export function fmtDate(iso: string): string {
  try { const d = new Date(iso); return `${d.getMonth() + 1}/${d.getDate()}`; }
  catch { return iso.slice(5, 10); }
}

/** Render markdown-like formatting (**bold**) in text. */
export function renderFormatted(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>;
    }
    if (part.trim().startsWith('-') || part.trim().startsWith('  -')) {
      return <span key={i} className="block">{part}</span>;
    }
    return <span key={i}>{part}</span>;
  });
}

export function todayStr(): string {
  const d = new Date();
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${weekdays[d.getDay()]}`;
}

export function monthStr(offset = 0): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
}

/** 看点数字徽标配色 (三个报告模式共用同一组颜色, 与拆分前逐字一致)。 */
export const catColors = [
  '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B',
  '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6',
];
