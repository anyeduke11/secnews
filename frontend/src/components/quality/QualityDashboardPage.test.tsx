import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useSearchParams } from 'react-router-dom';
import { QualityDashboardPage } from './QualityDashboardPage';
import { QueryMergeRedirect } from '../../routes';

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

  it('子标签切换: 拒绝样本 tab 渲染 QualityRejectionPage 内容', async () => {
    render(<MemoryRouter initialEntries={['/quality']}><QualityDashboardPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('90%')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: '拒绝样本' }));
    // QualityRejectionPage 真实组件挂入 (其自身数据由其内部拉取, 无 mock 时为空态/错误态, 不影响 tab 断言)
    await waitFor(() => expect(screen.getByRole('tab', { name: '拒绝样本' })).toHaveAttribute('aria-selected', 'true'));
  });
});

describe('A5: /quality/rejection → /quality?tab=rejection (query 合并透传, DEV-0188)', () => {
  it('旧深链附加参数不丢弃', () => {
    let seen = '';
    function Probe() {
      const sp = useSearchParams();
      seen = sp[0].toString();
      return null;
    }
    render(
      <MemoryRouter initialEntries={['/quality/rejection?foo=1&tab=old']}>
        <Routes>
          <Route path="/quality/rejection" element={<QueryMergeRedirect to="/quality" merge={{ tab: 'rejection' }} />} />
          <Route path="/quality" element={<Probe />} />
        </Routes>
      </MemoryRouter>,
    );
    // tab 被覆盖为 rejection, 其余参数 (foo=1) 保留
    expect(seen).toBe('foo=1&tab=rejection');
  });

  it('无附加参数 → 干净的 tab=rejection', () => {
    let seen = '';
    function Probe() {
      const sp = useSearchParams();
      seen = sp[0].toString();
      return null;
    }
    render(
      <MemoryRouter initialEntries={['/quality/rejection']}>
        <Routes>
          <Route path="/quality/rejection" element={<QueryMergeRedirect to="/quality" merge={{ tab: 'rejection' }} />} />
          <Route path="/quality" element={<Probe />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(seen).toBe('tab=rejection');
  });
});
