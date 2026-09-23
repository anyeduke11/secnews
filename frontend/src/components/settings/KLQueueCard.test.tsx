/** KLQueueCard — KL 队列只读卡 (自采集配置拆出) */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { KLQueueCard } from './KLQueueCard';

describe('KLQueueCard — KL 队列卡', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/secnews/pipeline')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ queue: { pending: 3, running: 1, error: 2 } }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染 pending/running/error 三格', async () => {
    render(<KLQueueCard />);
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
