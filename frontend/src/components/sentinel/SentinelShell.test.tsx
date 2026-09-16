// frontend/src/components/sentinel/SentinelShell.test.tsx
// 2026-09-13 NAV4: 壳既服务四菜单页 (页面渲染壳) 也服务工具页 (PageLayout 渲染壳), 锁定三点:
//  1. usePipeReloadOnSse 在 Provider 之外 (页面组件体) 也能触发心跳条重拉
//  2. layer=null: 四菜单 tab 由 menuOf 自动高亮归属菜单 (工具页的"我在哪"已不需要更多菜单)
//  3. ingested 未传时壳自取 24h total 并显示 "N 篇"
//  P2 (2026-09-13): 更多菜单 (SentinelMoreMenu / UTILITY_GROUPS) 物理删除 — 工具页高亮改由 menuOf 接管
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';

const SOURCES = { sources: [{ category: 'security', source_name: 'FreeBuf', status: 'active' }], registered_total: 1, registered_active: 1, registered_stale: 0, registered_dead: 0 };

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.startsWith('/api/sources/health') ? SOURCES
      : url.startsWith('/api/hotspots') ? { total: 7 }
        : {};
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
}

/** 模拟三层页结构: 页面组件体内调 hook, 壳是它渲染出来的子节点 (hook 在 Provider 之外) */
function PageRendersShell() {
  const reloadPipe = usePipeReloadOnSse();
  return (
    <SentinelShell layer="data" ingested={null}>
      <button type="button" onClick={reloadPipe}>模拟 SSE collect_done</button>
    </SentinelShell>
  );
}

describe('SentinelShell', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  const healthCalls = () => fetchMock.mock.calls.filter(c => String(c[0]).startsWith('/api/sources/health')).length;

  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('usePipeReloadOnSse 在 Provider 之外 (页面渲染壳) 触发心跳条重拉', async () => {
    render(<MemoryRouter initialEntries={['/']}><PageRendersShell /></MemoryRouter>);
    await waitFor(() => expect(healthCalls()).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: '模拟 SSE collect_done' }));
    await waitFor(() => expect(healthCalls()).toBe(2));
  });

  it('layer=null: 四菜单 tab 由 menuOf 自动高亮归属菜单 (P2 后无更多菜单)', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route path="/settings" element={<SentinelShell layer={null} ingested={null}><div>tool</div></SentinelShell>} />
        </Routes>
      </MemoryRouter>,
    );
    // NAV4: 工具页通过 menuOf(pathname) 自动高亮归属菜单 (Phase 2: .nv = 排版式四菜单)
    expect(screen.getByRole('link', { name: /^设置/ }).className).toContain('active');
    // P2: 更多菜单物理删除, 不再存在「更多」按钮
    expect(screen.queryByRole('button', { name: '更多' })).toBeNull();
  });

  it('layer 指定时对应 tab 高亮', () => {
    render(
      <MemoryRouter initialEntries={['/action']}>
        <SentinelShell layer="action" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: /^行动/ }).className).toContain('active');
    // P2: 更多菜单已删除, /action 不再有「更多」按钮
    expect(screen.queryByRole('button', { name: '更多' })).toBeNull();
  });

  it('ingested 未传 → 壳自取 24h total 显示 "7 篇"; 传 null → 保持 "…"', async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/todos']}>
        <SentinelShell layer={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('7 篇')).toBeInTheDocument());
    unmount();
    render(
      <MemoryRouter initialEntries={['/todos']}>
        <SentinelShell layer={null} ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(fetchMock.mock.calls.filter(c => String(c[0]).startsWith('/api/hotspots')).length).toBe(1);
    // 心跳条其它格子无数据时也显示 "…", 只看「今日收录」这一格
    expect(screen.getByText('今日收录').nextElementSibling?.textContent).toBe('…');
  });
});

describe('SentinelShell 版面条 bandnav (Phase 2 编辑部形态, DEV-0181)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
    try { window.localStorage.removeItem('bandnav-collapsed'); } catch { /* jsdom 兜底 */ }
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    try { window.localStorage.removeItem('bandnav-collapsed'); } catch { /* jsdom 兜底 */ }
  });

  it('资讯菜单 (/): 渲染 5 个 chip, current = 情报流', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SentinelShell layer="data" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    const nav = screen.getByRole('navigation', { name: '版面条' });
    const chips = Array.from(nav.querySelectorAll('.bn-chip')).map(c => c.textContent);
    expect(chips).toEqual(['情报流', '采集管道', '发行统计', '质量校对', '历史']);
    expect(nav.querySelector('.bn-chip.current')).toHaveTextContent('情报流');
  });

  it('工具页 (layer=null + /todos): menuOf 自动归属行动菜单, 待办 chip current', () => {
    render(
      <MemoryRouter initialEntries={['/todos']}>
        <SentinelShell layer={null} ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    const nav = screen.getByRole('navigation', { name: '版面条' });
    expect(nav.querySelector('.bn-chip.current')).toHaveTextContent('待办');
  });

  it('点击 chip 走 react-router 导航', () => {
    function LocProbe() {
      const loc = useLocation();
      return <div data-testid="loc">{loc.pathname}</div>;
    }
    render(
      <MemoryRouter initialEntries={['/']}>
        <SentinelShell layer="data" ingested={null}><LocProbe /></SentinelShell>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText('历史'));
    expect(screen.getByTestId('loc')).toHaveTextContent('/history');
  });

  it('gate 关闭的 chip 不渲染 (mock /api/settings/features 返回空)', async () => {
    render(
      <MemoryRouter initialEntries={['/action']}>
        <SentinelShell layer="action" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    await waitFor(() => {
      const chips = Array.from(
        screen.getByRole('navigation', { name: '版面条' }).querySelectorAll('.bn-chip'),
      ).map(c => c.textContent);
      expect(chips).toEqual(['今日行动', '通稿审核', '待办', '报告']); // 泳道 (codegarden) 被 gate 过滤
    });
  });

  it('A7: 收起版面条 — chips 隐藏 + localStorage 持久化 + root class 联动; 展开恢复', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <SentinelShell layer="data" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(screen.getByText('情报流')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '收起版面条' }));
    expect(screen.queryByText('情报流')).toBeNull();
    expect(screen.getByRole('button', { name: '展开版面条' })).toBeInTheDocument();
    // 持久化 + root class 联动 sticky 偏移变量 (--sn-bandnav-h: 33px → 24px)
    expect(window.localStorage.getItem('bandnav-collapsed')).toBe('1');
    expect(document.querySelector('.sentinel')?.className).toContain('bandnav-collapsed');

    // 重挂载仍收起 (持久化生效)
    unmount();
    render(
      <MemoryRouter initialEntries={['/']}>
        <SentinelShell layer="data" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(screen.queryByText('情报流')).toBeNull();

    // 展开: chips 恢复 + 持久化清除
    fireEvent.click(screen.getByRole('button', { name: '展开版面条' }));
    expect(screen.getByText('情报流')).toBeInTheDocument();
    expect(window.localStorage.getItem('bandnav-collapsed')).toBe('0');
    expect(document.querySelector('.sentinel')?.className).not.toContain('bandnav-collapsed');
  });
});
