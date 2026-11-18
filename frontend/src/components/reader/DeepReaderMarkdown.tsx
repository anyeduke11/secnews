/**
 * DeepReaderMarkdown — 清样正文的 markdown 子集渲染 (B5.6 拆分: 从 DeepReaderPage 抽出)
 *
 * 渲染: markdown 子集 (frontmatter 剥离 / h2 / h3 / 列表 / 段落 / 加粗), 行内码按原文显示。
 * 实现注: 解析器只用字符串定位、不用含特殊字节的正则 (Mimosa 误报, 见 DEV-0183)。
 */
import { useMemo } from 'react';
import { clipRanges, type BodyRange } from './deepReaderModel';

/** 行内渲染: **加粗** + 批注 mark (ranges 为相对 text 的坐标, 线性扫描) */
function renderInline(
  text: string,
  keyPrefix: string,
  ranges: { id: string; start: number; end: number }[] = [],
) {
  const nodes: React.ReactNode[] = [];
  let buf = '';
  let bold = false;
  let i = 0;
  let k = 0;
  const active = new Set<string>();
  const openAt = new Map<number, string[]>();
  const closeAt = new Map<number, string[]>();
  for (const r of ranges) {
    const s = Math.max(0, Math.min(r.start, text.length));
    const e = Math.max(0, Math.min(r.end, text.length));
    if (e <= s) continue;
    if (!openAt.has(s)) openAt.set(s, []);
    if (!closeAt.has(e)) closeAt.set(e, []);
    openAt.get(s)!.push(r.id);
    closeAt.get(e)!.push(r.id);
  }
  const flush = () => {
    if (!buf) return;
    let inner: React.ReactNode = buf;
    if (bold) inner = <strong>{buf}</strong>;
    if (active.size > 0) {
      inner = <mark key={`${keyPrefix}-m${k++}`} data-ann-id={[...active].join(' ')} className="ed-annmark">{inner}</mark>;
    }
    nodes.push(<span key={`${keyPrefix}-s${k++}`}>{inner}</span>);
    buf = '';
  };
  while (i <= text.length) {
    // 边界: 先用「旧 active 集合」flush 缓冲, 再应用关/开 (close 必须在 flush 之后删除,
    // 否则收尾段会丢失 mark — 探针 DEV-0190 发现的渲染丢失 bug)
    if (openAt.has(i) || closeAt.has(i)) {
      flush();
      for (const id of closeAt.get(i) ?? []) active.delete(id);
      for (const id of openAt.get(i) ?? []) active.add(id);
    }
    if (i >= text.length) break;
    if (text.startsWith('**', i)) {
      flush();
      bold = !bold;
      i += 2;
      continue;
    }
    buf += text[i] === '\n' ? ' ' : text[i];
    i += 1;
  }
  flush();
  return nodes;
}

/** 块级渲染: 空行分段 → h2/h3/ul/p; 每块按 body 偏移裁剪批注区间 */
export function Markdownish({ body, ranges }: { body: string; ranges: BodyRange[] }) {
  const blocks = useMemo(() => {
    const out: { text: string; offset: number; kind: 'h2' | 'h3' | 'ul' | 'p' }[] = [];
    let off = 0;
    for (const part of body.split('\n\n')) {
      const lead = part.length - part.trimStart().length;
      const text = part.trim();
      if (text) {
        const isList = text.split('\n').every(l => l.startsWith('- ') || l.startsWith('* '));
        const kind = text.startsWith('### ') ? 'h3' : text.startsWith('## ') ? 'h2' : isList ? 'ul' : 'p';
        out.push({ text, offset: off + lead, kind });
      }
      off += part.length + 2;
    }
    return out;
  }, [body]);

  return (
    <>
      {blocks.map((b, bi) => {
        if (b.kind === 'h3') {
          const t = b.text.slice(4);
          return <h3 key={bi}>{renderInline(t, `h3-${bi}`, clipRanges(ranges, b.offset + 4, t.length))}</h3>;
        }
        if (b.kind === 'h2') {
          const t = b.text.slice(3);
          return <h2 key={bi}>{renderInline(t, `h2-${bi}`, clipRanges(ranges, b.offset + 3, t.length))}</h2>;
        }
        if (b.kind === 'ul') {
          const rawLines = b.text.split('\n');
          let lineStart = 0;
          return (
            <ul key={bi}>
              {rawLines.map((rawLine, li) => {
                const lead = rawLine.length - rawLine.trimStart().length;
                const abs = b.offset + lineStart + lead + 2; // +2 = '- '/'* ' 前缀
                lineStart += rawLine.length + 1;
                const content = rawLine.trim().slice(2);
                return <li key={li}>{renderInline(content, `li-${bi}-${li}`, clipRanges(ranges, abs, content.length))}</li>;
              })}
            </ul>
          );
        }
        return <p key={bi}>{renderInline(b.text, `p-${bi}`, clipRanges(ranges, b.offset, b.text.length))}</p>;
      })}
    </>
  );
}
