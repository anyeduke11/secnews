/**
 * App.test.tsx — route-level smoke tests
 *
 * Covers:
 * - Renders the home page at "/"
 * - Renders each lazy route without error (via Suspense fallback)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

// Polyfill browser APIs unavailable in jsdom
vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})));
vi.stubGlobal('ResizeObserver', vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})));
vi.stubGlobal('localStorage', {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(() => null),
});

// Mock hooks that make API calls
vi.mock('./hooks/useHotspotData', () => ({
  useHotspotData: () => ({
    items: [],
    total: 0,
    categoryCounts: {},
    loading: true,
    loadingPage: false,
    error: null,
    lastUpdated: null,
    hasMore: false,
    page: 1,
    pageSize: 100,
    totalPages: 1,
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    refresh: vi.fn(),
    latestIngestionCount: 0,
    latestIngestionAt: null,
  }),
}));

vi.mock('./hooks/useTodos', () => ({
  useTodos: () => ({
    items: [],
    total: 0,
    count: null,
    availableFavorites: [],
    filter: { status: 'all', urgent: null, important: null, keyword: '' },
    loading: false,
    error: null,
    setFilter: vi.fn(),
    refresh: vi.fn(),
    add: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    isFavoriteInTodo: vi.fn(() => false),
  }),
}));

vi.mock('./hooks/useRefreshInterval', () => ({
  useRefreshInterval: () => ({
    interval: 5,
    setInterval: vi.fn(),
    refreshFromServer: vi.fn(),
  }),
}));

vi.mock('./hooks/useSSE', () => ({
  useSSE: () => ({ connected: false }),
}));

const ROUTES = [
  { path: '/', label: /热点地图/i, multiple: true },
  { path: '/category/ai', label: /热点地图/i, multiple: true },
  { path: '/todos', label: /正在排版/ },
  { path: '/history', label: /正在排版/ },
  { path: '/skills', label: /正在排版/ },
  { path: '/secrets', label: /正在排版/ },
  { path: '/sync', label: /正在排版/ },
  { path: '/weekly-report', label: /正在排版/ },
  { path: '/knowledge', label: /正在排版/ },
  { path: '/knowledge/import', label: /正在排版/ },
  { path: '/knowledge/process', label: /正在排版/ },
  { path: '/knowledge/compile', label: /正在排版/ },
  { path: '/knowledge/compound', label: /正在排版/ },
  { path: '/codegarden', label: /正在排版/ },
  { path: '/codegarden/phase2b', label: /正在排版/ },
];

describe('App routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  ROUTES.forEach(({ path, label, multiple = false }) => {
    it(`renders route "${path}" without crashing`, async () => {
      render(
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      );

      // For lazy-loaded routes, the Suspense fallback ("正在排版…") should appear;
      // 若 chunk 加载过快 fallback 已卸载, 则断言路由内容已渲染 (Outlet 非空)。
      // For static routes like "/", the page content renders directly.
      await waitFor(
        () => {
          if (multiple) {
            expect(screen.getAllByText(label).length).toBeGreaterThan(0);
          } else {
            const fallback = screen.queryByText(label);
            const outlet = document.querySelector('[class*="max-w-"]');
            expect(fallback ?? outlet?.firstElementChild).toBeTruthy();
          }
        },
        { timeout: 3000 }
      );
    });
  });
});
