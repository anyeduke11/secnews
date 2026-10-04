/**
 * RejectionReplay colocated 测试 (v0.8.6 P1-5, 审计 F1-3)。
 *
 * WHY (Rule 9): 锁"任一拒收可看原文与原因"验收 — 原文外链 rel 安全、
 * raw 缺失诚实"未留存"不伪造、错误显 unavailable。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RejectionReplay } from './RejectionReplay';
import type { QualityRejection } from '../../../api/secnews';

vi.mock('../../../api/secnews', () => ({
  getQualityRejections: vi.fn(),
}));

import { getQualityRejections } from '../../../api/secnews';

const mockGet = vi.mocked(getQualityRejections);

function row(over: Partial<QualityRejection> = {}): QualityRejection {
  return {
    item_id: 'itm_1', gate_name: 'pipeline', score_deduction: 100,
    flags: ['url_invalid'], reason: "hard gate 'schema' rejected: url 不可达",
    error_msg: null, checked_at: '2026-10-03T08:00:00+00:00', mode: 'strict',
    raw: {
      title: '被拒条目', url: 'https://src.example.com/x',
      summary: '这是被拒条目的摘要', source_id: 'src-1',
      published_at: '2026-10-01T00:00:00+00:00',
    },
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RejectionReplay', () => {
  it('渲染拒收行: 原文外链 (noopener) + 原因 + flags', async () => {
    mockGet.mockResolvedValue({ items: [row()], total: 1, window_hours: 168 });
    render(<RejectionReplay />);
    await waitFor(() => expect(screen.getByTestId('rejection-row')).toBeTruthy());
    const link = screen.getByRole('link', { name: '被拒条目' });
    expect(link).toHaveAttribute('href', 'https://src.example.com/x');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByTestId('rejection-replay').textContent).toContain(
      "hard gate 'schema' rejected",
    );
    expect(screen.getByTestId('rejection-replay').textContent).toContain('url_invalid');
  });

  it('raw 缺失 → 诚实"原文未留存", 不伪造', async () => {
    mockGet.mockResolvedValue({
      items: [row({ raw: null })], total: 1, window_hours: 168,
    });
    render(<RejectionReplay />);
    await waitFor(() => expect(screen.getByTestId('rejection-row')).toBeTruthy());
    expect(screen.getByTestId('rejection-replay').textContent).toContain('原文未留存');
    expect(screen.queryByRole('link', { name: '被拒条目' })).toBeNull();
  });

  it('空态与错误态', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, window_hours: 168 });
    const { unmount } = render(<RejectionReplay />);
    await waitFor(() => expect(
      screen.getByTestId('rejection-replay').textContent,
    ).toContain('窗口内无拒收记录'));
    unmount();

    mockGet.mockRejectedValue(new Error('backend down'));
    render(<RejectionReplay />);
    await waitFor(() => expect(
      screen.getByTestId('rejection-replay').textContent,
    ).toContain('拒收回放不可用'));
  });
});
