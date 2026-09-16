/**
 * DeepReaderPage — 清样深读 (/reader/:id, Phase 4 建, C2 批注接线 DEV-0190)
 *
 * 定位: wiki 条目的编辑部「清样」阅读视图 (衬线长文排版, 对齐方案A 原型 reader)。
 * 数据契约 (全真实 API):
 *  - 正文: GET /api/wiki/read?path=items/{id}.md (wiki_tools, 路径白名单已服务端校验)
 *  - 批注: GET/POST/DELETE /api/annotations (v1.7 Phase 2 既有 CRUD, migration 118 quote 列)
 * 锚点 (B+, DD-7): 批注存 quote (高亮原文) + range (原始 content 偏移)。
 * 渲染时四步解析抗正文漂移: ①快路径 slice==quote ②原偏移 ±2000 窗内重锚
 *   ③全文兜底 ④标 stale (侧栏「未定位」, 永不静默错放)。
 * 渲染: markdown 子集 (frontmatter 剥离 / h2 / h3 / 列表 / 段落 / 加粗), 行内码按原文显示。
 *  与 /deep/:type/:id (AI 深读分析) 并存: 那是判读流, 这是纯阅读流。
 *  实现注: 解析器只用字符串定位、不用含特殊字节的正则 (Mimosa 误报, 见 DEV-0183)。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch, getJSON, postJSON } from '../../lib/api';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import '../shared/editorial/pages.css';

interface WikiReadResult {
  path: string;
  content: string;
  size: number;
}

/** /api/annotations 列表项 (v1.7 Phase 2 契约, + migration 118 quote) */
interface AnnotationRow {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  quote: string | null;
  range_start: number | null;
  range_end: number | null;
  created_at: string;
}

type AnnStatus = 'located' | 'remapped' | 'stale';

interface ResolvedAnn {
  row: AnnotationRow;
  status: AnnStatus;
  /** body 相对坐标 (stale 时为 -1) */
  start: number;
  end: number;
}

const STATUS_LABEL: Record<AnnStatus, string> = {
  located: '已定位',
  remapped: '已迁移',
  stale: '未定位',
};
const STATUS_COLOR: Record<AnnStatus, string> = {
  located: 'var(--sn-mint)',
  remapped: 'var(--color-info)',
  stale: 'var(--sn-ink-3)',
};

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
function parseDoc(raw: string): { title: string; body: string; bodyOffset: number } {
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
function findAll(hay: string, needle: string): number[] {
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
function resolveAnn(a: AnnotationRow, raw: string, bodyOffset: number): ResolvedAnn {
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

interface BodyRange {
  id: string;
  start: number;
  end: number;
}

/** 批注区间裁剪到 [abs, abs+len) 窗口并平移为局部坐标 */
function clipRanges(ranges: BodyRange[], abs: number, len: number): BodyRange[] {
  return ranges
    .map(r => ({ id: r.id, start: r.start - abs, end: r.end - abs }))
    .filter(r => r.start < len && r.end > 0)
    .map(r => ({ ...r, start: Math.max(0, r.start), end: Math.min(len, r.end) }));
}

/** 块级渲染: 空行分段 → h2/h3/ul/p; 每块按 body 偏移裁剪批注区间 */
function Markdownish({ body, ranges }: { body: string; ranges: BodyRange[] }) {
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

/** 读取选区纯文本 (限长 500, 与后端 quote 上限一致) */
function selectionQuote(): string {
  const sel = window.getSelection();
  const t = (sel?.toString() ?? '').replace(/\s+/g, ' ').trim();
  return t.slice(0, 500);
}

export function DeepReaderPage() {
  const { id = '' } = useParams();
  const [doc, setDoc] = useState<WikiReadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [annRows, setAnnRows] = useState<AnnotationRow[] | null>(null);
  const [selQuote, setSelQuote] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [posting, setPosting] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const articleRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setDoc(null);
    // wiki_tools 白名单: [子目录/]name.md, 条目默认走 items/ 命名空间
    const path = id.endsWith('.md') ? id : `items/${id}.md`;
    getJSON<WikiReadResult>(`/api/wiki/read?path=${encodeURIComponent(path)}`)
      .then(d => { if (alive) setDoc(d); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id]);

  const loadAnns = useCallback(() => {
    if (!id) return;
    getJSON<{ items?: AnnotationRow[]; count?: number }>(
      `/api/annotations?entity_type=wiki_item&entity_id=${encodeURIComponent(id)}`,
    )
      .then(d => { setAnnRows(d.items ?? []); })
      .catch(() => { setAnnRows([]); });
  }, [id]);

  useEffect(() => { loadAnns(); }, [loadAnns]);

  const parsed = useMemo(() => (doc ? parseDoc(doc.content) : null), [doc]);

  // B+ 解析: 批注 → body 坐标 + 状态
  const resolved = useMemo(() => {
    if (!doc || !parsed || !annRows) return [];
    return annRows.map(a => resolveAnn(a, doc.content, parsed.bodyOffset));
  }, [doc, parsed, annRows]);

  const markRanges = useMemo(
    () => resolved
      .filter(r => r.status !== 'stale')
      .map(r => ({ id: r.row.id, start: r.start, end: r.end })),
    [resolved],
  );

  function onArticleMouseUp() {
    setSelQuote(selectionQuote());
    setFormOpen(false);
  }

  async function submitAnnotation() {
    if (!doc || !selQuote || !noteText.trim()) return;
    setPosting(true);
    setNotice(null);
    try {
      // range = quote 在原文的位置 (B+ 的 hint); 找不到时按比例估算
      const hits = findAll(doc.content, selQuote);
      const start = hits.length > 0
        ? hits[0]
        : Math.floor(doc.content.length * 0.1);
      await postJSON('/api/annotations', {
        entity_type: 'wiki_item',
        entity_id: id,
        content: noteText.trim(),
        quote: selQuote,
        range_start: start,
        range_end: start + selQuote.length,
      });
      setNotice({ kind: 'ok', text: '批注已保存' });
      setNoteText('');
      setFormOpen(false);
      setSelQuote('');
      window.getSelection()?.removeAllRanges();
      loadAnns();
    } catch (e) {
      setNotice({ kind: 'err', text: `保存失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setPosting(false);
    }
  }

  async function deleteAnn(annId: string) {
    try {
      await apiFetch(`/api/annotations/${encodeURIComponent(annId)}`, { method: 'DELETE' });
      loadAnns();
    } catch (e) {
      setNotice({ kind: 'err', text: `删除失败: ${e instanceof Error ? e.message : String(e)}` });
    }
  }

  function locate(annId: string) {
    document.querySelector(`mark[data-ann-id~="${annId}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  return (
      <div className="ed-wrap">
        {loading ? (
          <EmptyState title="清样排版中…" />
        ) : error ? (
          <EmptyState
            title="清样取阅失败"
            description={`${error} — 确认条目 id 对应 wiki items/{id}.md, 或先从知识库条目进入。`}
          />
        ) : !parsed ? (
          <EmptyState title="内容为空" />
        ) : (
          <>
            <div style={{ maxWidth: 820, margin: '0 auto', marginBottom: 14 }}>
              <Stamp color="info" variant="hollow">批注: /api/annotations (真实端点)</Stamp>
            </div>
            <article
              ref={articleRef}
              className="ed-reader"
              onMouseUp={onArticleMouseUp}
            >
              <h1>{parsed.title}</h1>
              <div className="ed-reader-meta">
                <span>{doc?.path}</span>
                {doc?.size ? <span>{(doc.size / 1024).toFixed(1)} KB</span> : null}
              </div>
              <Markdownish body={parsed.body} ranges={markRanges} />
            </article>

            {/* 选区批注: 选中文字后出现 */}
            {selQuote && (
              <div style={{ maxWidth: 820, margin: '18px auto 0' }} data-testid="ann-composer">
                <div className="pgx-quote-box" style={{ border: '1px solid var(--line-strong)', borderRadius: 'var(--radius-md)', padding: 12, background: 'var(--bg-card)' }}>
                  <div className="pgx-quote-text" style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>
                    批注引用:「{selQuote}」
                  </div>
                  {formOpen ? (
                    <div style={{ display: 'flex', gap: 8, flexDirection: 'column' }}>
                      <textarea
                        className="editorial-input"
                        aria-label="批注内容"
                        rows={3}
                        value={noteText}
                        onChange={e => setNoteText(e.target.value)}
                        placeholder="写下你的批注…"
                      />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button type="button" className="ed-btn primary" disabled={posting || !noteText.trim()} onClick={submitAnnotation}>
                          {posting ? '保存中…' : '保存批注'}
                        </button>
                        <button type="button" className="ed-btn" onClick={() => { setFormOpen(false); setNoteText(''); }}>
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="ed-btn" onClick={() => setFormOpen(true)}>
                      批注选中内容
                    </button>
                  )}
                </div>
              </div>
            )}

            {notice && (
              <p style={{ maxWidth: 820, margin: '14px auto 0', fontSize: 12, color: notice.kind === 'ok' ? 'var(--sn-mint)' : 'var(--sn-amber)' }} role="status">
                {notice.text}
              </p>
            )}

            {/* 批注侧栏: 三态 (定位/迁移/未定位) */}
            <aside className="ed-annrail" data-testid="ann-rail" aria-label="批注列表">
              <div className="ed-sechead">
                <span>批注 ({resolved.length})</span>
                <span className="ed-note">wiki_item / {id}</span>
              </div>
              {resolved.length === 0 ? (
                <p className="pgx-muted" style={{ fontSize: 12, color: 'var(--ink-3)' }}>
                  选中正文文字即可写下第一条批注。
                </p>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {resolved.map(r => (
                    <li key={r.row.id} className="ed-card" style={{ padding: '10px 12px', gap: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <i aria-hidden="true" style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[r.status], flexShrink: 0 }} />
                        <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--sn-mono)' }}>
                          {STATUS_LABEL[r.status]}
                        </span>
                        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                          {r.status !== 'stale' && (
                            <button type="button" className="ed-btn" onClick={() => locate(r.row.id)}>定位</button>
                          )}
                          <button type="button" className="ed-btn" aria-label={`删除批注: ${r.row.content.slice(0, 12)}`} onClick={() => deleteAnn(r.row.id)}>删除</button>
                        </span>
                      </div>
                      {r.row.quote && (
                        <div style={{ fontSize: 12, color: 'var(--ink-2)', borderLeft: '2px solid var(--line-strong)', paddingLeft: 8 }}>
                          「{r.row.quote.slice(0, 80)}{r.row.quote.length > 80 ? '…' : ''}」
                        </div>
                      )}
                      <div style={{ fontSize: 13, lineHeight: 1.6 }}>{r.row.content}</div>
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          </>
        )}
      </div>
  );
}
