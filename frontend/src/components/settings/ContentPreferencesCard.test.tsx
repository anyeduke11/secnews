/**
 * ContentPreferencesCard 组件测试 — DEV-0315 内容偏好 (类目/来源) 第二轴。
 *
 * 测试意图 (Rule 9): 显式偏好必须准确落到 settings.kv 的 PATCH 载荷
 * (类目 × 来源两轴, normal = 移除键), 失败要回滚不装成功。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { I18nProvider } from '../../contexts/I18nContext';
import { ContentPreferencesCard } from './ContentPreferencesCard';

const mockFetch = vi.fn();

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERROR',
    json: vi.fn().mockResolvedValue(data),
  } as unknown as Response;
}

const GET_BODY = {
  preferences: { categories: { tech: 'less' }, sources: { IT之家: 'less' } },
  valid_categories: ['ai', 'ai_security', 'security', 'finance', 'startup', 'github', 'tech', 'paper'],
  available_sources: [
    { source: 'IT之家', count: 30 },
    { source: 'FreeBuf', count: 12 },
    { source: 'HackerNews', count: 5 },
  ],
  levels: ['more', 'normal', 'less'],
};

function renderCard() {
  return render(<I18nProvider><ContentPreferencesCard /></I18nProvider>);
}

/** 分段控件三键位序: [0]=加强 [1]=默认 [2]=减弱 */
function rowButtons(testId: string): HTMLElement[] {
  return within(screen.getByTestId(testId)).getAllByRole('button');
}

function patchCalls(): { body: Record<string, unknown> }[] {
  return mockFetch.mock.calls
    .filter((c) => c[0] === '/api/settings/content-preferences' && (c[1]?.method ?? 'GET') === 'PATCH')
    .map((c) => ({ body: JSON.parse(String(c[1]?.body)) }));
}

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ContentPreferencesCard', () => {
  it('渲染类目 8 行 + 来源清单; 回读的偏好反映为按下态', async () => {
    mockFetch.mockResolvedValue(jsonResponse(GET_BODY));
    renderCard();

    await waitFor(() => expect(screen.getByTestId('content-prefs-cat-tech')).toBeInTheDocument());
    expect(screen.getByTestId('content-prefs-cat-paper')).toBeInTheDocument();
    expect(screen.getByTestId('content-prefs-src-FreeBuf')).toBeInTheDocument();

    // tech 回读为 less → 第三个键 (减弱) 按下
    const techKeys = rowButtons('content-prefs-cat-tech');
    expect(techKeys[2]).toHaveAttribute('aria-pressed', 'true');
    expect(techKeys[0]).toHaveAttribute('aria-pressed', 'false');
  });

  it('点「减弱」PATCH 全量偏好: 类目并入 + 来源保留', async () => {
    mockFetch.mockResolvedValue(jsonResponse(GET_BODY));
    renderCard();
    await waitFor(() => expect(screen.getByTestId('content-prefs-cat-github')).toBeInTheDocument());

    fireEvent.click(rowButtons('content-prefs-cat-github')[2]); // 减弱
    await waitFor(() => expect(patchCalls()).toHaveLength(1));

    expect(patchCalls()[0].body).toEqual({
      categories: { tech: 'less', github: 'less' },
      sources: { IT之家: 'less' },
    });
  });

  it('回到「默认」= 从载荷移除该键 (不存 normal)', async () => {
    mockFetch.mockResolvedValue(jsonResponse(GET_BODY));
    renderCard();
    await waitFor(() => expect(screen.getByTestId('content-prefs-cat-tech')).toBeInTheDocument());

    fireEvent.click(rowButtons('content-prefs-cat-tech')[1]); // 默认
    await waitFor(() => expect(patchCalls()).toHaveLength(1));

    expect(patchCalls()[0].body).toEqual({
      categories: {},
      sources: { IT之家: 'less' },
    });
  });

  it('来源轴「加强」写入 sources', async () => {
    mockFetch.mockResolvedValue(jsonResponse(GET_BODY));
    renderCard();
    await waitFor(() => expect(screen.getByTestId('content-prefs-src-FreeBuf')).toBeInTheDocument());

    fireEvent.click(rowButtons('content-prefs-src-FreeBuf')[0]); // 加强
    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    expect((patchCalls()[0].body as { sources: Record<string, string> }).sources).toEqual({
      IT之家: 'less',
      FreeBuf: 'more',
    });
  });

  it('保存失败 → 回滚到保存前状态 (不装成功)', async () => {
    mockFetch.mockImplementation((_url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'PATCH') {
        return Promise.resolve(jsonResponse({ detail: { message: 'boom' } }, 500));
      }
      return Promise.resolve(jsonResponse(GET_BODY));
    });
    renderCard();
    await waitFor(() => expect(screen.getByTestId('content-prefs-cat-github')).toBeInTheDocument());

    fireEvent.click(rowButtons('content-prefs-cat-github')[2]); // 减弱 → 失败
    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    // 回滚: github 回到默认态
    await waitFor(() => {
      expect(rowButtons('content-prefs-cat-github')[1]).toHaveAttribute('aria-pressed', 'true');
    });
  });

  it('来源搜索过滤', async () => {
    mockFetch.mockResolvedValue(jsonResponse(GET_BODY));
    renderCard();
    await waitFor(() => expect(screen.getByTestId('content-prefs-src-FreeBuf')).toBeInTheDocument());

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'hacker' } });
    expect(screen.getByTestId('content-prefs-src-HackerNews')).toBeInTheDocument();
    expect(screen.queryByTestId('content-prefs-src-FreeBuf')).toBeNull();
  });
});
