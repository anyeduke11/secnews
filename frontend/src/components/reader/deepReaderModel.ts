/**
 * deepReaderModel — 清样深读 (DeepReaderPage) 的纯类型 / 常量 / 计算
 * (B5.6 拆分: 从 DeepReaderPage 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见同目录 DeepReader*.tsx。
 * 解析器只用字符串定位、不用含特殊字节的正则 (Mimosa 误报, 见 DEV-0183)。
 */

// ── 类型 ────────────────────────────────────────────────────

export interface WikiReadResult {
  path: string;
  content: string;
  size: number;
}

/** /api/annotations 列表项 (v1.7 Phase 2 契约, + migration 118 quote) */
export interface AnnotationRow {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  quote: string | null;
  range_start: number | null;
  range_end: number | null;
  created_at: string;
}

export type AnnStatus = 'located' | 'remapped' | 'stale';

export interface ResolvedAnn {
  row: AnnotationRow;
  status: AnnStatus;
  /** body 相对坐标 (stale 时为 -1) */
  start: number;
  end: number;
}

export interface BodyRange {
  id: string;
  start: number;
  end: number;
}

// ── 常量 ────────────────────────────────────────────────────

export const STATUS_LABEL: Record<AnnStatus, string> = {
  located: '已定位',
  remapped: '已迁移',
  stale: '未定位',
};
export const STATUS_COLOR: Record<AnnStatus, string> = {
  located: 'var(--sn-mint)',
  remapped: 'var(--color-info)',
  stale: 'var(--sn-ink-3)',
};

// ── 计算 ────────────────────────────────────────────────────

/** 去包裹引号 (frontmatter title 值) */
function unquote(s: string): string {
  let out = s.trim();
  if (out.length >= 2) {
    const head = out.charAt(0);
    const tail = out.charAt(out.length - 1);
    if (head === tail && (head === "'" || head === '"')) {
      out = out.substring(1, out.length - 1).trim();
    }
  }
  return out;
}

/** 剥离 frontmatter 取 title; 返回 body 在 raw content 中的起始偏移 (B+ 解析需要) */
export function parseDoc(raw: string): { title: string; body: string; bodyOffset: number } {
  const lines = raw.split('\n');
  let consumedLines = 0;
  let title = '';
  if (lines.length > 0 && lines[0].trim() === '---') {
    let end = -1;
    for (let i = 1; i < lines.length; i += 1) {
      if (lines[i].trim() === '---') {
        end = i;
        break;
      }
      if (!title && lines[i].startsWith('title:')) {
        title = unquote(lines[i].slice(6));
      }
    }
    if (end > -1) consumedLines = end + 1;
  }
  if (!title) {
    for (let i = consumedLines; i < lines.length; i += 1) {
      if (lines[i].startsWith('# ')) {
        title = lines[i].slice(2).trim();
        consumedLines = i + 1;
        break;
      }
    }
  }
  // 跳过 body 起始的空行 (不计入 body 坐标)
  while (consumedLines < lines.length && lines[consumedLines].trim() === '') {
    consumedLines += 1;
  }
  let bodyOffset = 0;
  for (let i = 0; i < consumedLines; i += 1) bodyOffset += lines[i].length + 1;
  return { title: title || '未命名条目', body: lines.slice(consumedLines).join('\n'), bodyOffset };
}

/** 在 hay 中找 needle 全部出现位置 */
export function findAll(hay: string, needle: string): number[] {
  const out: number[] = [];
  if (!needle) return out;
  let i = hay.indexOf(needle);
  while (i > -1) {
    out.push(i);
    i = hay.indexOf(needle, i + 1);
  }
  return out;
}

/** B+ 四步解析: 批注 → body 相对坐标 + 状态 (永不静默错放) */
export function resolveAnn(a: AnnotationRow, raw: string, bodyOffset: number): ResolvedAnn {
  const rs = a.range_start;
  const re = a.range_end;
  if (rs == null || re == null || re <= rs) {
    return { row: a, status: 'stale', start: -1, end: -1 };
  }
  const quote = a.quote ?? raw.slice(rs, re);
  const locate = (rawStart: number): ResolvedAnn => {
    const bStart = rawStart - bodyOffset;
    return { row: a, status: 'remapped', start: bStart, end: bStart + quote.length };
  };
  // ① 快路径
  if (raw.slice(rs, rs + quote.length) === quote) {
    return { row: a, status: 'located', start: rs - bodyOffset, end: rs - bodyOffset + quote.length };
  }
  // ② 原偏移 ±2000 窗内重锚 (取最近出现)
  const winStart = Math.max(0, rs - 2000);
  const windowHits = findAll(raw.slice(winStart, rs + 2000 + quote.length), quote);
  if (windowHits.length > 0) {
    const hint = rs - winStart;
    const nearest = windowHits.reduce((best, p) => (Math.abs(p - hint) < Math.abs(best - hint) ? p : best), windowHits[0]);
    return locate(winStart + nearest);
  }
  // ③ 全文兜底 (取最近)
  const globalHits = findAll(raw, quote);
  if (globalHits.length > 0) {
    const nearest = globalHits.reduce((best, p) => (Math.abs(p - rs) < Math.abs(best - rs) ? p : best), globalHits[0]);
    return locate(nearest);
  }
  // ④ stale
  return { row: a, status: 'stale', start: -1, end: -1 };
}

/** 批注区间裁剪到 [abs, abs+len) 窗口并平移为局部坐标 */
export function clipRanges(ranges: BodyRange[], abs: number, len: number): BodyRange[] {
  return ranges
    .map(r => ({ id: r.id, start: r.start - abs, end: r.end - abs }))
    .filter(r => r.start < len && r.end > 0)
    .map(r => ({ ...r, start: Math.max(0, r.start), end: Math.min(len, r.end) }));
}
