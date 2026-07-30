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
  { path: '/todos', label: /加载中/ },
  { path: '/history', label: /加载中/ },
  { path: '/skills', label: /加载中/ },
  { path: '/secrets', label: /加载中/ },
  { path: '/sync', label: /加载中/ },
  { path: '/weekly-report', label: /加载中/ },
  { path: '/knowledge', label: /加载中/ },
  { path: '/knowledge/import', label: /加载中/ },
  { path: '/knowledge/process', label: /加载中/ },
  { path: '/knowledge/compile', label: /加载中/ },
  { path: '/knowledge/compound', label: /加载中/ },
  { path: '/codegarden', label: /加载中/ },
  { path: '/codegarden/phase2b', label: /加载中/ },
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

      // For lazy-loaded routes, the Suspense fallback ("加载中 ...") should appear.
      // For static routes like "/", the page content renders directly.
      await waitFor(
        () => {
          if (multiple) {
            expect(screen.getAllByText(label).length).toBeGreaterThan(0);
          } else {
            expect(screen.getByText(label)).toBeTruthy();
          }
        },
        { timeout: 3000 }
      );
    });
  });
});
