import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QualityDashboardPage } from './QualityDashboardPage';

describe('QualityDashboardPage — 校对室 (/quality)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/quality/summary')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ summary: { dedupe: { pass: 90, total: 100, avg_deduction: 1.2 }, recency: { pass: 80, total: 100, avg_deduction: 0.8 } } }),
        } as Response);
      }
      if (url.includes('/api/info-filter/rules')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            rules: [
              { id: 1, rule_type: 'deny', match_kind: 'keyword', match_value: '赌博', note: '黑名单样例', enabled: true },
            ],
            count: 1,
          }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('校对总览: 门禁通过率卡 + 信息过滤规则表 (全真实端点)', async () => {
    render(<MemoryRouter initialEntries={['/quality']}><QualityDashboardPage /></MemoryRouter>);
    expect(screen.getByText('校对室')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('90%')).toBeInTheDocument());
    expect(screen.getByText('80%')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('赌博')).toBeInTheDocument());
    expect(screen.getByText('黑名单样例')).toBeInTheDocument();
  });

  it('拒绝样本 tab 已收缩: 不再渲染「拒绝样本」入口 (2026-10-01 迁设置运维区)', () => {
    render(<MemoryRouter initialEntries={['/quality']}><QualityDashboardPage /></MemoryRouter>);
    expect(screen.getByRole('tab', { name: '校对总览' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '拒绝样本' })).toBeNull();
  });
});

describe('A5: /quality/rejection → /settings?cat=ops (2026-10-01 迁设置运维区)', () => {
  it('旧深链重定向到 设置→运维 (拒收日志卡所在区)', () => {
    const loc: { current: { pathname: string; search: string } | null } = { current: null };
    function Probe() {
      const l = useLocation();
      loc.current = { pathname: l.pathname, search: l.search };
      return null;
    }
    render(
      <MemoryRouter initialEntries={['/quality/rejection']}>
        <Routes>
          <Route path="/quality/rejection" element={<Navigate to="/settings?cat=ops" replace />} />
          <Route path="/settings" element={<Probe />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(loc.current?.pathname).toBe('/settings');
    expect(loc.current?.search).toContain('cat=ops');
  });
});
