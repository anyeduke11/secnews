/**
 * 极简 Markdown 渲染 (v1.0 T11)
 *
 * 仓库零 markdown 依赖 (无 react-markdown / markdown-to-jsx). 复用
 * DeepReadPage.stripInlineMarkdown 思路, 自实现**最小**集:
 *  - `**bold**` → <strong>
 *  - `*italic*` / `_italic_` → <em>
 *  - `# / ## / ###` 标题 → <h1> / <h2> / <h3> (行首)
 *  - `- / *` 无序列表 → <ul><li>
 *  - 段落分隔: 双换行
 *
 * 不支持 (与仓库策略一致): 表格, 嵌套列表, 代码块 (claim 不含代码)
 * 任何无法识别的语法**原样保留** (不抛错)
 *
 * 用法::
 *   <div dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(claim) }} />
 *   React 已经做了 XSS 转义在 dangerouslySetInnerHTML 上不安全; 但前端
 *   judgment claim 是后端 Pydantic 序列化产物, 服务层已限制 ≤ 10KB + 不含 HTML.
 *   进一步 XSS 防护在 server 端 (text/html Content-Type + CSP) 而非 client 渲染层.
 */
export function renderInlineMarkdown(md: string | null | undefined): string {
  if (!md) return '';
  // HTML escape (防 XSS)
  const escaped = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  // 行级处理: 标题 (行首) / 列表 / 段落
  const lines = escaped.split('\n');
  const out: string[] = [];
  let inList = false;
  let para: string[] = [];

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${inlineSpan(para.join(' '))}</p>`);
      para = [];
    }
  };
  const closeList = () => {
    if (inList) {
      out.push('</ul>');
      inList = false;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushPara();
      closeList();
      continue;
    }
    // 标题
    const h = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (h) {
      flushPara();
      closeList();
      const lvl = h[1].length;
      out.push(`<h${lvl}>${inlineSpan(h[2])}</h${lvl}>`);
      continue;
    }
    // 列表
    const li = /^[-*]\s+(.+)$/.exec(trimmed);
    if (li) {
      flushPara();
      if (!inList) {
        out.push('<ul>');
        inList = true;
      }
      out.push(`<li>${inlineSpan(li[1])}</li>`);
      continue;
    }
    closeList();
    para.push(trimmed);
  }
  flushPara();
  closeList();
  return out.join('');
}

function inlineSpan(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, '$1<em>$2</em>')
    .replace(/(^|\W)_([^_]+)_(?=\W|$)/g, '$1<em>$2</em>');
}
