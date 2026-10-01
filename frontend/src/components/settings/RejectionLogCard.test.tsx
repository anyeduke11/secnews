/**
 * RejectionLogCard — 拒收日志卡 (设置→运维, spec §6)。
 * 意图: reason 列双层解释 — explain (LLM 人话) 有则显 + 词典 flag 标签恒显。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RejectionLogCard } from './RejectionLogCard';

const LOG = {
  total: 2,
  page: 1,
  page_size: 50,
  items: [
    { id: 1, source_id: 'FreeBuf', item_title: 'Chrome 0day 在野利用',
      item_url: 'https://f.com/1', rejected_by: 'duplicate',
      reason: "flags=['content_hash_duplicate']", raw_data: '',
      created_at: '2026-10-01 10:00:00', explain: '与已收录的内容重复, 无需再次入库' },
    { id: 2, source_id: '安全客', item_title: '每周资讯播报',
      item_url: 'https://a.com/2', rejected_by: 'strict_mode',
      reason: "['empty_summary', 'category_mismatch']", raw_data: '',
      created_at: '2026-10-01 09:00:00', explain: null },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    if (String(input).startsWith('/api/quality/rejection-log')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LOG) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('RejectionLogCard — 拒收日志卡', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染标题与副标题 (自动生成解释说明)', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('拒收日志')).toBeInTheDocument());
    expect(screen.getByText(/每轮采集后自动生成解释/)).toBeInTheDocument();
  });

  it('explain 非空行显示 LLM 人话; 空行只有词典兜底', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/与已收录的内容重复/)).toBeInTheDocument());
    // 第二行 explain=null → 不显示人话, 但词典标签存在
    expect(screen.getByText('摘要为空')).toBeInTheDocument();
    expect(screen.getByText('内容与分类关键词不匹配')).toBeInTheDocument();
  });

  it('主拒因 (首 flag) 加粗', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('摘要为空')).toBeInTheDocument());
    const el = screen.getByText('摘要为空');
    expect(el.closest('b, strong, [data-main-flag]')).not.toBeNull();
  });
});
