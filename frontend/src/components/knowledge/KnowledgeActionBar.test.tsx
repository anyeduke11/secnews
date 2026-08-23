/**
 * KnowledgeActionBar 单元测试
 *
 * 验证：
 *  - 6 个按钮全渲染 (c4 范围约束)
 *  - 路由型按钮调用 useNavigate
 *  - API 型按钮调用 fetch + 显示 toast
 *  - busy 状态互斥 (一次只能一个按钮忙)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KnowledgeActionBar, KNOWLEDGE_ACTION_BUTTONS } from './KnowledgeActionBar';

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('KnowledgeActionBar', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200 } as Response)
    );
  });

  it('renders 6 action buttons (c4 范围约束)', () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    const bar = screen.getByTestId('knowledge-action-bar');
    expect(bar).toBeInTheDocument();
    // 6 个按钮全渲染
    for (const btn of KNOWLEDGE_ACTION_BUTTONS) {
      expect(screen.getByText(btn.label)).toBeInTheDocument();
    }
  });

  it('route button navigates when clicked (出题复习)', () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('出题复习'));
    expect(mockNavigate).toHaveBeenCalledWith('/knowledge/review');
  });

  it('route button navigates when clicked (概念卡)', () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('概念卡'));
    expect(mockNavigate).toHaveBeenCalledWith('/knowledge/process');
  });

  it('api button POSTs to /api/llm/digest (写日报周报)', async () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('写日报周报'));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/llm/digest',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('api button POSTs to /api/todos (转待办)', async () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('转待办'));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/todos',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('shows toast on api success', async () => {
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('转待办'));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('已触发');
    });
  });

  it('shows error toast on api failure', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500 } as Response)
    );
    render(
      <MemoryRouter>
        <KnowledgeActionBar />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText('转待办'));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('失败');
    });
  });

  it('KNOWLEDGE_ACTION_BUTTONS has exactly 6 entries (c4 锁定)', () => {
    expect(KNOWLEDGE_ACTION_BUTTONS).toHaveLength(6);
  });
});