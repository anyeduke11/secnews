// DeepReaderPage — 清样深读 (/reader/:id) 测试
// Phase 4 建 (正文渲染), C2 (DEV-0190) 批注接线: B+ 三态解析 / mark 高亮 / 定位 / 删除 / POST 选区流
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { DeepReaderPage } from './DeepReaderPage';

const WIKI_MD = [
  '---',
  'title: 零信任落地手记',
  'tags: [zero-trust]',
  '---',
  '',
  '# 零信任落地手记',
  '',
  '零信任的**核心假设**是网络边界不可信。',
  '',
  '## 落地三步',
  '',
  '- 盘点资产',
  '- 收敛身份',
  '- 持续验证',
  '',
  '收尾段落, 无标记符号。',
].join('\n');

/** B+ 锚点 fixture:
 *  - ann1: range 错位 (drift), quote 在正文 → ②窗内重锚 → remapped
 *  - ann2: quote 不在正文 → stale */
const ANNOS = {
  version: 'x',
  count: 2,
  items: [
    {
      id: 'ann-1', entity_type: 'wiki_item', entity_id: 'zt-notes',
      content: '这一句是核心论点', quote: '是网络边界不可信',
      range_start: 3, range_end: 11, created_at: '2026-09-16T08:00:00+00:00',
    },
    {
      id: 'ann-2', entity_type: 'wiki_item', entity_id: 'zt-notes',
      content: '漂移到找不到的批注', quote: '不存在的引文',
      range_start: 50, range_end: 57, created_at: '2026-09-16T08:01:00+00:00',
    },
  ],
};

/** useParams 需要 Route 上下文: 按 /reader/:id 真实挂载 */
function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reader/:id" element={<DeepReaderPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DeepReaderPage — 清样深读 (/reader/:id)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/wiki/read')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ path: 'items/zt-notes.md', content: WIKI_MD, size: WIKI_MD.length }),
        } as Response);
      }
      if (url.includes('/api/annotations?')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(ANNOS) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as unknown as { EventSource: unknown }).EventSource = class { close() {} onopen = null; };
    // jsdom 无 scrollIntoView
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as unknown as { EventSource: unknown }).EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('打 /api/wiki/read (items/{id}.md), frontmatter 剥离 + 标题取自 title:', async () => {
    renderAt('/reader/zt-notes');
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('零信任落地手记'));
    const readCalls = fetchMock.mock.calls.filter(c => String(c[0]).includes('/api/wiki/read'));
    expect(readCalls.length).toBe(1);
    expect(String(readCalls[0][0])).toContain('path=items%2Fzt-notes.md');
  });

  it('markdown 子集渲染: 加粗 / h2 / 列表 / 段落', async () => {
    renderAt('/reader/zt-notes');
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: '落地三步' })).toBeInTheDocument();
    expect(screen.getByText('核心假设').closest('strong')).toBeInTheDocument();
    expect(screen.getByText('盘点资产')).toBeInTheDocument();
    expect(screen.getByText('收尾段落, 无标记符号。')).toBeInTheDocument();
  });

  it('C2: B+ 解析三态 — remapped 渲染 mark, stale 仅侧栏; 批注拉取打既有端点', async () => {
    const { container } = renderAt('/reader/zt-notes');
    // 等 B+ 重锚完成 (mark 渲染 = anns 已拉取且 remapped 解析成功)
    await waitFor(() => expect(container.querySelector('mark.ed-annmark')).not.toBeNull());
    // ann1 range 错位但 quote 可定位 → remapped → mark 高亮
    const mark = container.querySelector('mark.ed-annmark');
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toContain('是网络边界不可信');
    expect(mark?.getAttribute('data-ann-id')).toBe('ann-1');
    // ann2 quote 不在正文 → stale (无对应 mark, 侧栏可见)
    expect(container.querySelectorAll('mark.ed-annmark').length).toBe(1);
    expect(screen.getByText('未定位')).toBeInTheDocument();
    expect(screen.getByText('已迁移')).toBeInTheDocument();
    expect(screen.getByText('漂移到找不到的批注')).toBeInTheDocument();
    // 既有批注端点 (v1.7 Phase 2 契约)
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('/api/annotations?entity_type=wiki_item'))).toBe(true);
  });

  it('C2: 定位按钮 scrollIntoView 到对应 mark; 删除按钮打 DELETE', async () => {
    const { container } = renderAt('/reader/zt-notes');
    await waitFor(() => expect(container.querySelector('mark.ed-annmark')).not.toBeNull());
    expect(screen.getByRole('button', { name: '定位' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '定位' }));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }));
    fireEvent.click(screen.getAllByRole('button', { name: /删除批注/ })[0]);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(c => String(c[0]).startsWith('/api/annotations/ann-1') && (c[1] as { method?: string })?.method === 'DELETE')).toBe(true);
    });
  });

  it('C2: 选区 → 批注按钮 → 表单提交 POST (quote + wiki_item 锚点)', async () => {
    const { container } = renderAt('/reader/zt-notes');
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());
    // 初始无选区组件
    expect(screen.queryByTestId('ann-composer')).toBeNull();

    // 模拟选中正文开头文字 (TreeWalker 找首个非空文本节点)
    const article = container.querySelector('article.ed-reader')!;
    const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
    let textNode: Text | null = null;
    for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
      if (n.data.trim().length >= 4) { textNode = n; break; }
    }
    expect(textNode).not.toBeNull();
    const range = document.createRange();
    range.setStart(textNode!, 0);
    range.setEnd(textNode!, Math.min(4, textNode!.data.length));
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    fireEvent.mouseUp(article);

    // 选区组件出现 → 展开表单 → 输入 → 保存
    expect(screen.getByTestId('ann-composer')).toBeInTheDocument();
    expect(screen.getByText(/批注引用:/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '批注选中内容' }));
    fireEvent.change(screen.getByLabelText('批注内容'), { target: { value: '第一条批注' } });
    fireEvent.click(screen.getByRole('button', { name: '保存批注' }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(c =>
        String(c[0]) === '/api/annotations' && (c[1] as { method?: string })?.method === 'POST');
      expect(post).toBeTruthy();
      const body = JSON.parse((post![1] as { body: string }).body);
      expect(body.entity_type).toBe('wiki_item');
      expect(body.entity_id).toBe('zt-notes');
      expect(body.quote.length).toBeGreaterThan(0);
      expect(body.content).toBe('第一条批注');
    });
  });
});
