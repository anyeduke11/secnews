// frontend/src/components/sentinel/SentinelShell.test.tsx
// 2026-09-10 壳统一批: 壳既服务三层页 (页面渲染壳) 也服务工具页 (PageLayout 渲染壳), 锁定三点:
//  1. usePipeReloadOnSse 在 Provider 之外 (三层页组件体) 也能触发心跳条重拉 — 此前拿到的是默认 no-op
//  2. layer=null: 三层 tab 无高亮, 更多菜单按当前路径高亮 (工具页的"我在哪")
//  3. ingested 未传时壳自取 24h total 并显示 "N 篇"
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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

  it('layer=null: 三层 tab 无高亮, 更多菜单按当前工具页路径高亮并标 aria-current', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <SentinelShell layer={null} ingested={null}><div>tool</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(document.querySelector('.layer-link.active')).toBeNull();
    const more = screen.getByRole('button', { name: '更多' });
    expect(more.className).toContain('active');
    fireEvent.click(more);
    const item = screen.getByRole('menuitem', { name: /全局设置/ });
    expect(item.getAttribute('aria-current')).toBe('page');
    expect(item.className).toContain('active');
  });

  it('layer 指定时对应 tab 高亮, 更多按钮不高亮', () => {
    render(
      <MemoryRouter initialEntries={['/judge']}>
        <SentinelShell layer="judge" ingested={null}><div>x</div></SentinelShell>
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: /判断层/ }).className).toContain('active');
    expect(screen.getByRole('button', { name: '更多' }).className).not.toContain('active');
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
