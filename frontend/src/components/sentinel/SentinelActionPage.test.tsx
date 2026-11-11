/**
 * SentinelActionPage — 行动层「今日行动」测试
 *
 * 测试意图:
 *  - 双栏契约 (复习 / 判读待办) 必须来自真实接口, 不接受示意稿
 *  - **写操作是本屏核心**: 推进判读待办 → PUT .../status 且必须两步链
 *    (pending→in_progress→completed); 复习评分 → POST /api/reviews/{type}/{id}/grade。
 *    全部断言乐观更新 + 失败回滚。
 *  - planning_actions / reviews 空数据 → 如实渲染空态, 不造假数据
 *  - R-13: 待办清单 (/api/todos) 已退役, 本屏不再有该数据源与写操作
 *  - 全程 mock fetch, 不发真实网络请求、不写库
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SentinelActionPage } from './SentinelActionPage';

const DAY = (offsetDays: number, base = new Date()) =>
  new Date(base.getTime() + offsetDays * 86400000).toISOString();

/** planning-actions 顶层就是数组 (无包裹对象) */
const ACTIONS_FIXTURE = [
  {
    id: 4258, item_id: '203160c47be8', action_type: 'refine', priority: 8,
    title: '精读入库: PDF 解析库内存越界', description: null,
    current_stage: 'kl:raw', target_stage: 'kl:refine',
    status: 'pending', created_at: DAY(-6), completed_at: null, dismissed_at: null,
  },
  {
    id: 4259, item_id: '04f200b38a81', action_type: 'publish', priority: 3,
    title: '产出输出: 本周边防简报', description: null,
    current_stage: 'kl:structure', target_stage: 'kl:publish',
    status: 'pending', created_at: DAY(-2), completed_at: null, dismissed_at: null,
  },
];

const REVIEWS_FIXTURE = {
  version: 'test',
  count: 2,
  items: [
    {
      id: 'hotspot-ai_x_1b8d', entity_type: 'hotspot', entity_id: 'ai_小互AI_1b8d52a1396d',
      easiness: 2.5, interval: 1, repetitions: 0, due_at: DAY(-1),
      last_grade: null, last_reviewed_at: null,
      created_at: DAY(-3), updated_at: DAY(-3),
    },
    {
      id: 'item-concept-gamma', entity_type: 'item', entity_id: 'concept-gamma',
      easiness: 2.3, interval: 2, repetitions: 1, due_at: DAY(0),
      last_grade: 4, last_reviewed_at: DAY(-2),
      created_at: DAY(-5), updated_at: DAY(-2),
    },
  ],
};

const REVIEW_STATS = { version: 'test', stats: { total: 3, due: 2, avg_easiness: 2.433 } };
const SECNEWS_STATS = { version: 'test', new_today: 18, pipeline_health: 'healthy', top_categories: [] };

/**
 * fetch mock 工厂: 返回 {fn, calls}; calls 由本工厂闭包记录 (即使 fn 再被包装一层
 * 仍可读到), 断言写接口的方法 / 路径 / 请求体都走它, 全程不发真实请求。
 */
interface CallRecord { url: string; init?: RequestInit }

function makeFetch(opts: {
  actions?: unknown;
  reviews?: unknown;
  reviewStats?: unknown;
  fail?: (url: string) => boolean;
} = {}) {
  const calls: CallRecord[] = [];
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (opts.fail?.(url)) {
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
    }
    if (url.startsWith('/api/kl/planning-actions')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(opts.actions ?? ACTIONS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/due')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(opts.reviews ?? REVIEWS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(opts.reviewStats ?? REVIEW_STATS) } as Response);
    }
    // ReviewOverlay (复习栈能力丰富): 数据/管理视图数据源
    if (url.startsWith('/api/reviews/forecast')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [{ date: '2026-01-01', count: 0 }] }),
      } as Response);
    }
    if (url.startsWith('/api/reviews/history')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) } as Response);
    }
    if (url.startsWith('/api/reviews/cards')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(opts.reviews ?? REVIEWS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/search')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ result: { items: [] } }) } as Response);
    }
    if (url.startsWith('/api/secnews/stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SECNEWS_STATS) } as Response);
    }
    // v0.8.6 M1 审批收件箱区块 (本页测试不涉其交互, 返回空队列)
    if (url.startsWith('/api/proposals')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [], total: 0, filter: { status: null, kind: null } }),
      } as Response);
    }
    // SentinelShell 心跳条
    if (url.startsWith('/api/sources/health')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ sources: [{ category: 'security', source_name: 'FreeBuf', status: 'active' }] }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
  return { fn, calls };
}

const render_ = () => render(<MemoryRouter><SentinelActionPage /></MemoryRouter>);

describe('SentinelActionPage — 行动层今日行动', () => {
  let api: ReturnType<typeof makeFetch>;

  beforeEach(() => {
    api = makeFetch();
    vi.stubGlobal('fetch', api.fn);
    try { localStorage.removeItem('hotspot-theme'); } catch {}
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('渲染双栏骨架 + ACTION FLOOR kicker + 壳层导航 (layer=action)', async () => {
    const { container } = render_();
    await waitFor(() => expect(screen.getByText('判读待办')).toBeInTheDocument());

    expect(screen.getByText('ACTION FLOOR')).toBeInTheDocument();
    for (const h of ['ac-h-review', 'ac-h-out']) {
      expect(container.querySelector(`#${h}`)).toBeInTheDocument();
    }
    expect(container.querySelector('.ac-grid')).toBeInTheDocument();
    // R-13: 待办清单已退役 → 不再有 todos 面板与七日强度点阵
    expect(container.querySelector('#ac-h-todo')).toBeNull();
    expect(container.querySelector('.ac-days')).toBeNull();
    expect(screen.getByText('复习栈')).toBeInTheDocument();
    screen.getByText('判读待办');
    // 壳: 行动菜单 active (Phase 2 编辑部导航 .nv, active = accent 下划线)
    expect(container.querySelector('.nv.active')).toHaveTextContent('行动');
  });

  it('真实数据驱动: 判读队列/复习卡片与今日收录均来自接口', async () => {
    const { container } = render_();
    await waitFor(() => expect(screen.getByText('2 PENDING')).toBeInTheDocument());

    // planning_actions 顶层数组直接消费
    screen.getByText('精读入库: PDF 解析库内存越界');
    expect(screen.getByText('#4258')).toBeInTheDocument();
    expect(screen.getByText('P8')).toBeInTheDocument();
    expect(screen.getByText('kl:raw → kl:refine')).toBeInTheDocument();

    // 复习卡: 接口只有 entity_id, 如实渲染实体标识
    expect(screen.getByText('concept-gamma')).toBeInTheDocument();
    expect(container.querySelectorAll('.ac-card')).toHaveLength(2);

    // 今日收录来自 /api/secnews/stats
    expect(screen.getByText('18 篇')).toBeInTheDocument();

    // R-13: 退役的待办域不再发起请求
    expect(api.calls.some(c => c.url.startsWith('/api/todos'))).toBe(false);
  });

  it('完成判读待办走服务端状态机两步链 pending→in_progress→completed', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('精读入库: PDF 解析库内存越界')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: /^完成：精读入库/ }));
    await waitFor(() => expect(screen.getByText('已完成')).toBeInTheDocument());

    const puts = api.calls.filter(c => c.url === '/api/kl/planning-actions/4258/status');
    expect(puts).toHaveLength(2);
    expect(puts.map(c => JSON.parse(String(c.init!.body)).status)).toEqual(['in_progress', 'completed']);
    expect(puts.every(c => c.init?.method === 'PUT')).toBe(true);
  });

  it('判读待办第二步失败 → 停在已确认的 in_progress 并标「已推进一步」', async () => {
    let hits = 0;
    vi.stubGlobal('fetch', makeFetch({
      fail: url => {
        if (!url.includes('/planning-actions/4258/status')) return false;
        hits += 1;
        return hits === 2; // 第一步成功, 第二步失败
      },
    }).fn);
    render_();
    await waitFor(() => expect(screen.getByText('精读入库: PDF 解析库内存越界')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: /^完成：精读入库/ }));
    await waitFor(() => expect(screen.getByText('已推进一步')).toBeInTheDocument());
    expect(screen.getByText('进行中')).toBeInTheDocument();
  });

  it('暂缓判读待办同样两步链到 dismissed', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('产出输出: 本周边防简报')).toBeInTheDocument());

    // 队列每行都有「暂缓」按钮 → 用该行 <li> 精确定位, 不用全局 name 查询
    const row = screen.getByText('产出输出: 本周边防简报').closest('li') as HTMLElement;
    const btn = row.querySelector('.ac-dbtn') as HTMLButtonElement;
    fireEvent.click(btn);

    await waitFor(() => expect(within(row).getByText('已暂缓')).toBeInTheDocument());
    const puts = api.calls.filter(c => c.url === '/api/kl/planning-actions/4259/status');
    expect(puts.map(c => JSON.parse(String(c.init!.body)).status)).toEqual(['in_progress', 'dismissed']);
    expect(puts.every(c => c.init?.method === 'PUT')).toBe(true);
  });

  it('复习评分 → POST /api/reviews/{type}/{id}/grade {grade} 并把卡片移出到期队列', async () => {
    const inner = makeFetch();
    const spy = vi.fn((input: RequestInfo | URL, init?: RequestInit) => inner.fn(input, init));
    vi.stubGlobal('fetch', spy);
    render_();
    // 顶层卡 = 队列第一张 (hotspot / ai_小互AI_...)
    await waitFor(() => expect(screen.getByText('ai_小互AI_1b8d52a1396d')).toBeInTheDocument());

    const topRow = document.querySelector('.ac-card.top') as HTMLElement;
    expect(topRow.querySelector('.ac-ct')?.textContent).toBe('ai_小互AI_1b8d52a1396d');
    fireEvent.click(within(topRow).getByRole('button', { name: /记得牢/ }));

    // 请求 URL / body 直接读组件实际调用的包装 mock
    await waitFor(() => {
      const call = spy.mock.calls.find(c => String(c[0]).includes('/grade'));
      expect(call).toBeTruthy();
    });
    const [gradeUrl, gradeInit] = spy.mock.calls.find(c => String(c[0]).includes('/grade'))!;
    expect(String(gradeUrl)).toBe(`/api/reviews/hotspot/${encodeURIComponent('ai_小互AI_1b8d52a1396d')}/grade`);
    expect(gradeInit?.method).toBe('POST');
    expect(JSON.parse(String(gradeInit?.body))).toEqual({ grade: 5 });

    // 服务端未回 item → 视为已排走后程: 卡片出队, 原队列下一张升为可评分顶层卡
    await waitFor(() => {
      expect(screen.queryByText('往后第 1 张')).toBeNull();
    });
    expect(document.querySelector('.ac-card.top .ac-ct')?.textContent).toBe('concept-gamma');
    expect(within(document.querySelector('.ac-card.top') as HTMLElement)
      .getByRole('button', { name: /记得牢/ })).toBeInTheDocument();
  });

  it('复习与判读队列为空 → 如实空态, 不渲染假卡片', async () => {
    vi.stubGlobal('fetch', makeFetch({
      actions: [],
      reviews: { version: 'test', count: 0, items: [] },
    }).fn);
    render_();
    await waitFor(() => expect(screen.getByText('今日复习栈已清空')).toBeInTheDocument());
    expect(screen.getByText('判读队列已清空')).toBeInTheDocument();
    expect(screen.queryByText(/ATT&CK/)).not.toBeInTheDocument();
    expect(document.querySelectorAll('.ac-card')).toHaveLength(0);
  });

  it('某数据源不可用 → 顶部 amber 提示但页面不崩', async () => {
    vi.stubGlobal('fetch', makeFetch({
      fail: url => url.startsWith('/api/secnews/stats'),
    }).fn);
    render_();
    await waitFor(() => {
      const banner = document.querySelector('.ac-banner');
      expect(banner).not.toBeNull();
      expect(banner!.textContent).toContain('个数据源本次未返回');
    });
    expect(screen.getByText('判读待办')).toBeInTheDocument();
  });

  /* ============ 复习栈能力丰富 (migration 120) ============ */

  const ENRICHED_REVIEWS = {
    version: 'test',
    count: 1,
    items: [{
      ...REVIEWS_FIXTURE.items[0],
      title: 'AI 安全周报：供应链攻击抬头',
      url: 'https://example.com/weekly',
      category: 'security',
      excerpt: '三家供应商遭投毒',
    }],
  };

  it('enrich 命中 → 卡片显示真实标题, entity_id 降为副行, 查看原文外链', async () => {
    vi.stubGlobal('fetch', makeFetch({ reviews: ENRICHED_REVIEWS }).fn);
    const { container } = render_();
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());

    // 主行 = 标题; 副行 = 裸 entity_id; 外链走 safeHref 白名单
    expect(container.querySelector('.ac-card.top .ac-chint.num')?.textContent)
      .toBe('ai_小互AI_1b8d52a1396d');
    const link = container.querySelector('.ac-card.top a[href="https://example.com/weekly"]');
    expect(link).not.toBeNull();
    expect(link).toHaveTextContent('查看原文');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('评分后出现 "下次 N 天后见" 反馈与 5 秒撤销窗, 撤销触发 POST undo', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('ai_小互AI_1b8d52a1396d')).toBeInTheDocument());

    const topRow = document.querySelector('.ac-card.top') as HTMLElement;
    fireEvent.click(within(topRow).getByRole('button', { name: /记得牢/ }));

    // 反馈条: grade 响应无 item → 无 "下次" 文案, 但撤销窗必须出现
    await waitFor(() => expect(document.querySelector('.ac-gfeedback')).not.toBeNull());
    expect(document.querySelector('.ac-gfeedback')!.textContent).toContain('已评「');

    fireEvent.click(screen.getByRole('button', { name: '撤销' }));
    await waitFor(() => {
      const call = api.calls.find(c => c.url.includes('/undo') && c.init?.method === 'POST');
      expect(call).toBeTruthy();
    });
    expect(api.calls.find(c => c.url.includes('/undo'))!.url)
      .toBe(`/api/reviews/hotspot/${encodeURIComponent('ai_小互AI_1b8d52a1396d')}/undo`);
  });

  it('键盘 1/3/5 快捷评分 (面板态, 非输入框聚焦)', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('ai_小互AI_1b8d52a1396d')).toBeInTheDocument());

    fireEvent.keyDown(window, { key: '3' });
    await waitFor(() => {
      const call = api.calls.find(c => c.url.includes('/grade') && c.init?.method === 'POST');
      expect(call).toBeTruthy();
    });
    const gradeCall = api.calls.find(c => c.url.includes('/grade') && c.init?.method === 'POST')!;
    expect(JSON.parse(String(gradeCall.init!.body))).toEqual({ grade: 3 });
  });

  it('输入框内按键不触发快捷评分', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('ai_小互AI_1b8d52a1396d')).toBeInTheDocument());

    // R-13: 页面级「快速捕获」输入框已随待办域退役, 改用复习栈弹层内的搜索框守卫同一意图
    fireEvent.click(screen.getByRole('button', { name: '专注复习' }));
    const dialog = await screen.findByRole('dialog', { name: '复习栈工作台' });
    fireEvent.click(within(dialog).getByRole('tab', { name: '管理' }));
    const input = within(dialog).getByLabelText('搜索加入复习卡');
    fireEvent.keyDown(input, { key: '5' });
    expect(api.calls.some(c => c.url.includes('/grade'))).toBe(false);
  });

  it('复习栈底部入口 → 打开 ReviewOverlay 三视图弹层 (零新增路由)', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('ai_小互AI_1b8d52a1396d')).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '专注复习' }));
    const dialog = await screen.findByRole('dialog', { name: '复习栈工作台' });
    expect(dialog).toBeInTheDocument();
    // 会话视图消费同一 due 数据源 (enrich): 标题主行 + entity_id 副行各一处
    const hits = await within(dialog).findAllByText('ai_小互AI_1b8d52a1396d');
    expect(hits.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(within(dialog).getByRole('tab', { name: '管理' }));
    // 管理视图拉 /api/reviews/cards
    await waitFor(() => {
      expect(api.calls.some(c => c.url.startsWith('/api/reviews/cards'))).toBe(true);
    });

    fireEvent.click(screen.getByRole('button', { name: '关闭复习栈' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

