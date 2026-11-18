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
 *
 * B5.6 拆分: 本文件只保留容器 (状态 + 取数编排); 纯展示区块见同目录
 * DeepReaderArticle.tsx / DeepReaderComposer.tsx / DeepReaderRail.tsx,
 * 纯类型 / 常量 / 计算见 deepReaderModel.ts。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { createAnnotation, deleteAnnotation, listAnnotations, readWikiDoc } from '../../api/knowledge';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import { DeepReaderArticle } from './DeepReaderArticle';
import { DeepReaderComposer } from './DeepReaderComposer';
import { DeepReaderRail } from './DeepReaderRail';
import {
  findAll,
  parseDoc,
  resolveAnn,
  type AnnotationRow,
  type WikiReadResult,
} from './deepReaderModel';
import '../shared/editorial/pages.css';

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
    readWikiDoc<WikiReadResult>(path)
      .then(d => { if (alive) setDoc(d); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id]);

  const loadAnns = useCallback(() => {
    if (!id) return;
    listAnnotations<AnnotationRow>('wiki_item', id)
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
      await createAnnotation({
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
      await deleteAnnotation(annId);
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
            <DeepReaderArticle
              title={parsed.title}
              path={doc?.path}
              size={doc?.size}
              body={parsed.body}
              ranges={markRanges}
              articleRef={articleRef}
              onMouseUp={onArticleMouseUp}
            />

            {/* 选区批注: 选中文字后出现 */}
            {selQuote && (
              <DeepReaderComposer
                selQuote={selQuote}
                formOpen={formOpen}
                noteText={noteText}
                posting={posting}
                onNoteTextChange={setNoteText}
                onSubmit={submitAnnotation}
                onCancel={() => { setFormOpen(false); setNoteText(''); }}
                onOpenForm={() => setFormOpen(true)}
              />
            )}

            {notice && (
              <p style={{ maxWidth: 820, margin: '14px auto 0', fontSize: 12, color: notice.kind === 'ok' ? 'var(--sn-mint)' : 'var(--sn-amber)' }} role="status">
                {notice.text}
              </p>
            )}

            {/* 批注侧栏: 三态 (定位/迁移/未定位) */}
            <DeepReaderRail
              resolved={resolved}
              entityId={id}
              onLocate={locate}
              onDelete={deleteAnn}
            />
          </>
        )}
      </div>
  );
}
