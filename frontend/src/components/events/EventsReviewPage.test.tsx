import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EventsReviewPage } from './EventsReviewPage';

const TYPES = {
  total: 2,
  items: [
    { id: 'evt_ransomware', name: '勒索软件事件', candidate_stats: { pending: 2, approved: 5, rejected: 1, total: 8, avg_confidence: 0.82 } },
    { id: 'evt_phishing', name: '钓鱼事件', candidate_stats: { pending: 0, approved: 3, rejected: 0, total: 3, avg_confidence: 0.9 } },
  ],
};

const CANDIDATES = {
  event_type_id: 'evt_ransomware',
  owner_status: 'pending',
  total: 2,
  items: [
    { candidate_id: 'etc_01', technique_id: 'T1486', stage: 'impact', confidence: 0.91, evidence_quote: '加密文件并勒索赎金', owner_status: 'pending' },
    { candidate_id: 'etc_02', technique_id: 'T1071', stage: 'c2', confidence: 0.74, evidence_quote: '回连 C2 域名', owner_status: 'pending' },
  ],
};

describe('EventsReviewPage — 通稿审核 (/action/events, 全真实 API)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/event-technique/candidates')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(CANDIDATES) } as Response);
      }
      if (url.includes('/api/event-technique/event-types') && url.includes('batch-approve')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ approved: 2, total: 2 }) } as Response);
      }
      if (url.includes('/api/event-technique/event-types')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(TYPES) } as Response);
      }
      if (url.includes('/approve')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('类型清单渲染进度统计, 数据源印章标注真实端点', async () => {
    render(<MemoryRouter><EventsReviewPage /></MemoryRouter>);
    expect(screen.getByText('通稿审核')).toBeInTheDocument();
    expect(screen.getByText('数据源: /api/event-technique (真实端点)')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('勒索软件事件')).toBeInTheDocument());
    expect(screen.getByText(/待审 2 · 已过 5 · 驳回 1/)).toBeInTheDocument();
  });

  it('选中类型 → 拉候选队列, 通过后行消失且类型进度重拉', async () => {
    render(<MemoryRouter><EventsReviewPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('勒索软件事件')).toBeInTheDocument());
    fireEvent.click(screen.getByText('勒索软件事件'));
    await waitFor(() => expect(screen.getByText('T1486')).toBeInTheDocument());
    expect(screen.getByText('T1071')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '通过' })[0]);
    await waitFor(() => expect(screen.queryByText('T1486')).toBeNull());
    // approve POST 打到正确端点
    const approveCalls = fetchMock.mock.calls.filter(c => String(c[0]).includes('/candidates/etc_01/approve'));
    expect(approveCalls.length).toBe(1);
  });

  it('驳回需填理由: 空理由时确认按钮禁用', async () => {
    render(<MemoryRouter><EventsReviewPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('勒索软件事件')).toBeInTheDocument());
    fireEvent.click(screen.getByText('勒索软件事件'));
    await waitFor(() => expect(screen.getByText('T1486')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: '驳回' })[0]);
    expect(screen.getByRole('button', { name: '确认驳回' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('驳回理由'), { target: { value: '证据不足' } });
    expect(screen.getByRole('button', { name: '确认驳回' })).toBeEnabled();
  });

  it('A2: 批量通过两段式确认 — 首次点击仅武装不发请求, 二次点击才 POST', async () => {
    render(<MemoryRouter><EventsReviewPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('勒索软件事件')).toBeInTheDocument());
    fireEvent.click(screen.getByText('勒索软件事件'));
    await waitFor(() => expect(screen.getByText('T1486')).toBeInTheDocument());

    const batchCalls = () => fetchMock.mock.calls.filter(c => String(c[0]).includes('batch-approve')).length;
    expect(batchCalls()).toBe(0);

    // 首次点击: 进入武装态 (文案变化), 无请求
    fireEvent.click(screen.getByRole('button', { name: /批量通过/ }));
    expect(screen.getByRole('button', { name: /确认批量通过/ })).toBeInTheDocument();
    expect(batchCalls()).toBe(0);

    // 二次点击: 真正发批量请求
    fireEvent.click(screen.getByRole('button', { name: /确认批量通过/ }));
    await waitFor(() => expect(batchCalls()).toBe(1));
    // 批量完成后回到常规文案
    await waitFor(() => expect(screen.getByRole('button', { name: '批量通过 (信 ≥0.7)' })).toBeInTheDocument());
  });
});
