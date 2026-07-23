// frontend/src/components/ReviewPage.test.tsx
// v1.7 Phase 2 — ReviewPage 组件测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReviewPage } from './ReviewPage';

// Mock useGoHome (避免 react-router 依赖)
vi.mock('../hooks/useGoHome', () => ({
  useGoHome: () => vi.fn(),
}));

// Mock Icon (避免 SVG 依赖)
vi.mock('./Icon', () => ({
  Icon: ({ children }: { children: React.ReactNode }) => <span data-icon="mock">{children}</span>,
}));

// 测试数据
const dueItems = [
  {
    id: 'concept-c1',
    entity_type: 'concept',
    entity_id: 'c1',
    easiness: 2.5,
    interval: 1,
    repetitions: 0,
    due_at: '2026-07-23T00:00:00Z',
    last_grade: null,
    last_reviewed_at: null,
    created_at: '2026-07-22T00:00:00Z',
    updated_at: '2026-07-22T00:00:00Z',
  },
  {
    id: 'knowledge-k1',
    entity_type: 'knowledge',
    entity_id: 'k1',
    easiness: 2.8,
    interval: 6,
    repetitions: 2,
    due_at: '2026-07-23T00:00:00Z',
    last_grade: 4,
    last_reviewed_at: '2026-07-17T00:00:00Z',
    created_at: '2026-07-10T00:00:00Z',
    updated_at: '2026-07-17T00:00:00Z',
  },
];

const stats = { total: 5, due: 2, avg_easiness: 2.65 };

const notesForK1 = [
  {
    id: 'note-1',
    entity_type: 'knowledge',
    entity_id: 'k1',
    content: '这是笔记 1',
    range_start: null,
    range_end: null,
    created_at: '2026-07-22T10:00:00Z',
    updated_at: '2026-07-22T10:00:00Z',
  },
];

describe('ReviewPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      // /api/reviews/due
      if (u.includes('/api/reviews/due')) {
        return new Response(JSON.stringify({ items: dueItems }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // /api/reviews/stats
      if (u.includes('/api/reviews/stats')) {
        return new Response(JSON.stringify({ stats }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // /api/annotations?entity_type=knowledge&entity_id=k1
      if (u.includes('/api/annotations')) {
        return new Response(JSON.stringify({ items: notesForK1 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // grade / default
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    global.fetch = fetchMock as any;
  });

  it('renders stats (total / due / avg_easiness)', async () => {
    render(<ReviewPage />);
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument(); // total
      expect(screen.getByText('2')).toBeInTheDocument(); // due
    });
    // avg_easiness 2.65 → toFixed(2) = "2.65"
    await waitFor(() => {
      expect(screen.getByText('2.65')).toBeInTheDocument();
    });
  });

  it('renders due review cards', async () => {
    render(<ReviewPage />);
    await waitFor(() => {
      expect(screen.getByText('c1')).toBeInTheDocument();
      expect(screen.getByText('k1')).toBeInTheDocument();
    });
  });

  it('shows empty state when no due items', async () => {
    fetchMock = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/reviews/due')) {
        return new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (u.includes('/api/reviews/stats')) {
        return new Response(
          JSON.stringify({ stats: { total: 0, due: 0, avg_easiness: 0 } }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    });
    global.fetch = fetchMock as any;

    render(<ReviewPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无到期复习项')).toBeInTheDocument();
    });
  });

  it('flips card on click and shows grade buttons', async () => {
    render(<ReviewPage />);
    await waitFor(() => expect(screen.getByText('c1')).toBeInTheDocument());

    // 点击 c1 卡片 (翻转)
    fireEvent.click(screen.getByText('c1'));
    // 翻转后应显示评分按钮 (0-5)
    await waitFor(() => {
      expect(screen.getByText('评分 (SM-2)')).toBeInTheDocument();
    });
    // 6 个评分按钮 (用 aria-label 精确定位, 避免与统计值 "5" 冲突)
    expect(screen.getByLabelText('评分 0 - 完全忘记')).toBeInTheDocument();
    expect(screen.getByLabelText('评分 5 - 瞬间记忆')).toBeInTheDocument();
  });

  it('selects card and loads notes in NoteEditor', async () => {
    render(<ReviewPage />);
    await waitFor(() => expect(screen.getByText('k1')).toBeInTheDocument());

    // 点击 k1 卡片 (选中 + 翻转)
    fireEvent.click(screen.getByText('k1'));

    // 应显示笔记面板 + 笔记内容
    await waitFor(() => {
      expect(screen.getByText('这是笔记 1')).toBeInTheDocument();
    });
  });

  it('submits grade on button click and refreshes queue', async () => {
    render(<ReviewPage />);
    await waitFor(() => expect(screen.getByText('c1')).toBeInTheDocument());

    // 选中并翻转 c1
    fireEvent.click(screen.getByText('c1'));
    await waitFor(() => expect(screen.getByText('评分 (SM-2)')).toBeInTheDocument());

    // 点击评分 5
    const gradeBtn = screen.getByLabelText('评分 5 - 瞬间记忆');
    fireEvent.click(gradeBtn);

    // 应调用 grade API
    await waitFor(() => {
      const gradeCalls = fetchMock.mock.calls.filter((c: any[]) => {
        const u = typeof c[0] === 'string' ? c[0] : c[0]?.url;
        return u && u.includes('/grade');
      });
      expect(gradeCalls.length).toBeGreaterThan(0);
    });
  });
});
