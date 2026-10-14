// frontend/src/components/sentinel/ReactionButtons.test.tsx
// DEV-0326 — useReactionAction: 4 资讯面共用的赞/踩调用壳。
//
// 测试意图 (Rule 9): 赞/踩对全部条目放行 (含非安全领域/未归类), 后端持久化,
// 前端不再有"未参与推荐"提示。本测试锁定"点击即发 POST 且不弹提示"这一契约,
// 防止旧 DEV-0314 丢弃提示被误加回。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ToastProvider } from '../Toast';
import { useReactionAction } from './ReactionButtons';
import { resetReactionsStore } from '../../hooks/useReactions';

const mockFetch = vi.fn();

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: vi.fn().mockResolvedValue(data),
    blob: vi.fn(),
    text: vi.fn().mockResolvedValue(JSON.stringify(data)),
  } as unknown as Response;
}

function apiWithPost(status: string) {
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method || 'GET';
    const u = String(url);
    if (method === 'GET' && u.startsWith('/api/interest/reactions')) {
      return Promise.resolve(jsonResponse({ items: {}, count: 0 }));
    }
    if (method === 'POST' && u === '/api/interest/signals') {
      return Promise.resolve(jsonResponse({ status, domain: null }));
    }
    return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
  });
}

function Harness() {
  const doReact = useReactionAction();
  return (
    <button onClick={() => { void doReact({ id: 'x', title: '标题-x' }, 'like'); }}>
      点赞
    </button>
  );
}

const OBSOLETE_MSG = '该条目未参与推荐：非安全领域内容或未归类';

beforeEach(() => {
  resetReactionsStore();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useReactionAction', () => {
  it('点击即发 POST 且不弹提示 (含未归类条目, DEV-0326)', async () => {
    apiWithPost('ok');
    render(<ToastProvider><Harness /></ToastProvider>);

    fireEvent.click(screen.getByText('点赞'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalledWith(
      '/api/interest/signals',
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(screen.queryByText(OBSOLETE_MSG)).toBeNull();
  });
});