/**
 * ContentPreferencesCard 组件测试 — DEV-0316 三层 (自动学习 / AI 建议 / 手动高级)。
 *
 * 测试意图 (Rule 9):
 * - 默认零配置: 自动学习结果直接可见, 手动区折叠 (用户不再面对 200+ 按钮);
 * - 采纳建议 = 写入手动层 (人主律, 建议不自动生效);
 * - 手动 PATCH 载荷精确 (轴/键/level), 失败回滚不装成功。
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

const CATS = ['ai', 'ai_security', 'security', 'finance', 'startup', 'github', 'tech', 'paper'];
const SOURCES = [
  { source: 'IT之家', count: 30 },
  { source: 'FreeBuf', count: 12 },
  { source: 'HackerNews', count: 5 },
];

type Table = Record<string, string>;
interface Body { categories: Table; sources: Table }

function getBody(prefs: Body = { categories: {}, sources: {} }, auto: Body = { categories: {}, sources: {} }) {
  return {
    preferences: prefs,
    auto_preferences: auto,
    valid_categories: CATS,
    available_sources: SOURCES,
    levels: ['more', 'normal', 'less'],
  };
}

const RECS_BODY = {
  categories: { tech: 'less' },
  sources: { 'IT之家': 'more' },
  reasons: { tech: '杂讯偏多', 'IT之家': '你常赞它的报道' },
  cached_at: '2026-10-11T00:00:00+00:00',
  note: '',
};

/** 默认路由: GET 偏好 / GET 建议 / PATCH 成功 */
function mockApi(prefs?: Body, auto?: Body) {
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    const u = String(url);
    if (method === 'GET' && u.startsWith('/api/interest/content-prefs/recommendations')) {
      return Promise.resolve(jsonResponse(RECS_BODY));
    }
    if (method === 'GET' && u.startsWith('/api/settings/content-preferences')) {
      return Promise.resolve(jsonResponse(getBody(prefs, auto)));
    }
    if (method === 'PATCH' && u.startsWith('/api/settings/content-preferences')) {
      return Promise.resolve(jsonResponse({ status: 'ok', preferences: JSON.parse(String(init?.body)) }));
    }
    return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
  });
}

function renderCard() {
  return render(
    <I18nProvider>
      <ContentPreferencesCard />
    </I18nProvider>,
  );
}

async function openAdvanced() {
  fireEvent.click(await screen.findByTestId('content-prefs-advanced-toggle'));
  await screen.findByTestId('content-prefs-cat-tech');
}

function rowButtons(testId: string): HTMLElement[] {
  return within(screen.getByTestId(testId)).getAllByRole('button');
}

function patchCalls() {
  return mockFetch.mock.calls
    .filter((c) => String(c[0]).startsWith('/api/settings/content-preferences') && (c[1]?.method ?? 'GET') === 'PATCH')
    .map((c) => JSON.parse(String(c[1]?.body)) as { categories: Record<string, string>; sources: Record<string, string> });
}

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  // jsdom navigator.language=en-US → Provider 默认英文; 本文件断言中文文案
  localStorage.setItem('hotspot-locale', 'zh-CN');
});

afterEach(() => {
  vi.unstubAllGlobals();
  // 防 I18nProvider locale 泄漏到后续用例 (默认 zh-CN 断言中文文案)
  localStorage.removeItem('hotspot-locale');
});

describe('ContentPreferencesCard (DEV-0316 三层)', () => {
  it('默认态: 自动学习区展示推导结果, 手动区折叠 (不铺 200+ 按钮)', async () => {
    mockApi(undefined, { categories: { tech: 'less' }, sources: {} });
    renderCard();

    await screen.findByTestId('content-prefs-auto');
    // 自动推导的 tech=减弱 以 chip 展示 (中文标签「IT / 科技」)
    const auto = screen.getByTestId('content-prefs-auto');
    expect(within(auto).getByText(/减弱/)).toBeInTheDocument();
    // 手动区默认折叠: 高级按钮在, 类目行不在
    expect(screen.getByTestId('content-prefs-advanced-toggle')).toBeInTheDocument();
    expect(screen.queryByTestId('content-prefs-cat-tech')).toBeNull();
  });

  it('无自动结果 → 诚实空态文案', async () => {
    mockApi();
    renderCard();
    await screen.findByTestId('content-prefs-auto');
    expect(screen.getByTestId('content-prefs-auto')).toHaveTextContent('暂未触发');
  });

  it('展开高级 → 类目 8 行 + 来源行出现; 点「减弱」PATCH 载荷精确', async () => {
    mockApi();
    renderCard();
    await openAdvanced();

    fireEvent.click(rowButtons('content-prefs-cat-github')[2]); // 减弱
    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    expect(patchCalls()[0]).toEqual({
      categories: { github: 'less' },
      sources: {},
    });
  });

  it('AI 建议展示 + 采纳 → 写入手动层 (PATCH 含建议键)', async () => {
    mockApi();
    renderCard();
    const advisor = await screen.findByTestId('content-prefs-advisor');
    expect(within(advisor).getByText('杂讯偏多')).toBeInTheDocument();

    // 采纳按钮 (tech=less 那条)
    const adoptBtns = within(advisor).getAllByRole('button', { name: '采纳' });
    fireEvent.click(adoptBtns[0]);
    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    expect(patchCalls()[0].categories).toEqual({ tech: 'less' });
  });

  it('保存失败 → 回滚 (不装成功, 错误 chip 可见)', async () => {
    mockApi();
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      const u = String(url);
      if (method === 'PATCH') return Promise.resolve(jsonResponse({ detail: { message: 'boom' } }, 500));
      if (u.startsWith('/api/interest/content-prefs/recommendations')) return Promise.resolve(jsonResponse(RECS_BODY));
      return Promise.resolve(jsonResponse(getBody()));
    });
    renderCard();
    await openAdvanced();

    fireEvent.click(rowButtons('content-prefs-cat-tech')[2]);
    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    // 回滚: tech 行回到「默认」按下态
    await waitFor(() => {
      expect(rowButtons('content-prefs-cat-tech')[1]).toHaveAttribute('aria-pressed', 'true');
    });
    expect(screen.getByText('保存失败, 已还原')).toBeInTheDocument();
  });

  it('来源搜索过滤 (高级展开内)', async () => {
    mockApi();
    renderCard();
    await openAdvanced();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'hacker' } });
    expect(screen.getByTestId('content-prefs-src-HackerNews')).toBeInTheDocument();
    expect(screen.queryByTestId('content-prefs-src-FreeBuf')).toBeNull();
  });
});
