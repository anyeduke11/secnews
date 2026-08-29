/**
 * SentinelActionPage — 行动层「今日行动」测试
 *
 * 测试意图:
 *  - 三栏契约 (复习 / 待办 / 判读待办) 与七日强度点阵必须来自真实接口, 不接受示意稿
 *  - **写操作是本屏核心**: 勾选待办 → PATCH /api/todos/{id}; 快速捕获 → POST /api/todos;
 *    推进判读待办 → PUT .../status 且必须两步链 (pending→in_progress→completed);
 *    复习评分 → POST /api/reviews/{type}/{id}/grade。全部断言乐观更新 + 失败回滚。
 *  - planning_actions / reviews 空数据 → 如实渲染空态, 不造假数据
 *  - API href 白名单: 非 http(s) 的 url 不得渲染成链接 (禁 javascript: 注入)
 *  - 全程 mock fetch, 不发真实网络请求、不写库
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SentinelActionPage } from './SentinelActionPage';

const DAY = (offsetDays: number, base = new Date()) =>
  new Date(base.getTime() + offsetDays * 86400000).toISOString();

/** 本地日期字符串 'YYYY-MM-DD' (避免 UTC/本地跨日导致断言随运行时刻漂移) */
const DATE = (offsetDays: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

const TODOS_FIXTURE = {
  version: 'test',
  total: 3,
  items: [
    {
      id: 12, source_type: 'manual', source_id: null, title: '把云 WAF 绕过复盘拆成 3 条加固项',
      url: 'https://example.com/waf', source: null, category: null,
      urgent: 1, important: 1, deadline: DATE(-2), note: null,
      status: 'open', created_at: DAY(-3), updated_at: DAY(-1), completed_at: null,
    },
    {
      id: 13, source_type: 'favorite', source_id: 'f9', title: '复核 LLM 网关加固笔记',
      // 恶意 URL: 必须被 ^https?: 白名单拦掉, 不渲染为 <a>
      url: 'javascript:alert(1)', source: 'FreeBuf', category: 'security',
      urgent: 0, important: 0, deadline: '', note: null,
      status: 'open', created_at: DAY(-2), updated_at: DAY(-2), completed_at: null,
    },
    {
      id: 14, source_type: 'manual', source_id: null, title: '晨读过完 12 条快讯',
      url: null, source: null, category: null,
      urgent: 0, important: 0, deadline: '', note: null,
      status: 'done', created_at: DAY(-4), updated_at: DAY(-1), completed_at: `${DATE(0)}T12:00:00`,
    },
  ],
};

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
    const method = (init?.method ?? 'GET').toUpperCase();
    if (opts.fail?.(url)) {
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
    }
    if (url.startsWith('/api/todos') && method === 'GET') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(TODOS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/todos') && method === 'PATCH') {
      const body = JSON.parse(String(init!.body));
      const id = Number(url.split('/').pop());
      const src = TODOS_FIXTURE.items.find(i => i.id === id)!;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          version: 'test',
          item: { ...src, ...body, completed_at: body.status === 'done' ? DAY(0) : null },
        }),
      } as Response);
    }
    if (url.startsWith('/api/todos') && method === 'POST') {
      const body = JSON.parse(String(init!.body));
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          version: 'test', created: true,
          item: {
            id: 99, source_type: 'manual', source_id: null, title: body.title, url: null,
            source: null, category: null, urgent: 0, important: 0, deadline: '', note: null,
            status: 'open', created_at: DAY(0), updated_at: DAY(0), completed_at: null,
          },
        }),
      } as Response);
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
    if (url.startsWith('/api/secnews/stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SECNEWS_STATS) } as Response);
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

  it('渲染三栏骨架 + ACTION FLOOR kicker + 壳层导航 (layer=action)', async () => {
    const { container } = render_();
    await waitFor(() => expect(screen.getByText('待办清单')).toBeInTheDocument());

    expect(screen.getByText('ACTION FLOOR')).toBeInTheDocument();
    for (const h of ['ac-h-review', 'ac-h-todo', 'ac-h-out']) {
      expect(container.querySelector(`#${h}`)).toBeInTheDocument();
    }
    expect(container.querySelector('.ac-grid')).toBeInTheDocument();
    expect(container.querySelector('.ac-days')).toBeInTheDocument();
    expect(screen.getByText('复习栈')).toBeInTheDocument();
    screen.getByText('判读待办');
    // 壳: 行动层 active
    expect(container.querySelector('.layer-link.active')).toHaveTextContent('行动层');
  });

  it('真实数据驱动: 待办/判读队列/复习卡片与今日收录均来自接口', async () => {
    const { container } = render_();
    await waitFor(() => expect(screen.getByText(/2 OPEN · 1 DONE/)).toBeInTheDocument());

    // todos 标题 + 编号等宽承载
    screen.getByText('把云 WAF 绕过复盘拆成 3 条加固项');
    screen.getByText('复核 LLM 网关加固笔记');
    expect(screen.getByText('#12')).toBeInTheDocument();
    // 逾期用 amber 文案 (纪律: red 专属漏洞告警)
    expect(screen.getByText('逾期 2 天')).toBeInTheDocument();

    // planning_actions 顶层数组直接消费
    screen.getByText('精读入库: PDF 解析库内存越界');
    expect(screen.getByText('#4258')).toBeInTheDocument();
    expect(screen.getByText('P8')).toBeInTheDocument();
    expect(screen.getByText('kl:raw → kl:refine')).toBeInTheDocument();
    expect(screen.getByText('2 PENDING')).toBeInTheDocument();

    // 复习卡: 接口只有 entity_id, 如实渲染实体标识
    expect(screen.getByText('concept-gamma')).toBeInTheDocument();
    expect(container.querySelectorAll('.ac-card')).toHaveLength(2);

    // 今日收录来自 /api/secnews/stats
    expect(screen.getByText('18 篇')).toBeInTheDocument();
  });

  it('七日强度点阵由 todos.completed_at 派生', async () => {
    render_();
    await waitFor(() => expect(screen.getByText(/本周节奏/)).toBeInTheDocument());
    // fixture: 仅 id=14 于今日中午完成 → 本周 1 天达标
    expect(screen.getByText('1 / 7 达标')).toBeInTheDocument();
    expect(screen.getByText('今日完成 1 项 · 本周累计 1 项')).toBeInTheDocument();
  });

  it('本周无完成记录 → 点阵 0 / 7 达标, 不编造强度', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/todos')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ version: 't', total: 0, items: [] }) } as Response);
      }
      return api.fn(input, init);
    }));
    render_();
    await waitFor(() => expect(screen.getByText('0 / 7 达标')).toBeInTheDocument());
    expect(screen.getByText('本周尚无完成记录 · 口径为待办完成时间')).toBeInTheDocument();
  });

  it('勾选待办 → PATCH /api/todos/{id} {status:done} 并乐观标记完成', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('把云 WAF 绕过复盘拆成 3 条加固项')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: /把云 WAF 绕过复盘/ }));
    await waitFor(() => {
      const call = api.calls.find(c => c.url === '/api/todos/12' && c.init?.method === 'PATCH');
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call!.init!.body))).toEqual({ status: 'done' });
    });
    // 乐观更新: 该行进入 done 分组 → open 计数从 2 变 1
    await waitFor(() => expect(screen.getByText(/1 OPEN · 2 DONE/)).toBeInTheDocument());
  });

  it('待办写入失败 → 回滚乐观态并给出 amber 失败提示 (不用 red)', async () => {
    vi.stubGlobal('fetch', makeFetch({ fail: url => url.includes('/api/todos/13') }).fn);
    render_();
    await waitFor(() => expect(screen.getByText('复核 LLM 网关加固笔记')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('checkbox', { name: /复核 LLM 网关加固笔记/ }));
    await waitFor(() => expect(screen.getByText('保存失败')).toBeInTheDocument());
    // 回滚后仍是未完成态 (open 计数不变)
    expect(screen.getByText(/2 OPEN · 1 DONE/)).toBeInTheDocument();
    expect(document.querySelector('.ac-tstate.fail')).toBeInTheDocument();
  });

  it('快速捕获 → POST /api/todos {source_type:manual,title} 并置顶新行', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('复核 LLM 网关加固笔记')).toBeInTheDocument());

    const input = screen.getByLabelText('快速捕获新待办');
    fireEvent.change(input, { target: { value: '周五前交防钓抽查名单' } });
    fireEvent.click(screen.getByRole('button', { name: /添加/ }));

    await waitFor(() => {
      const call = api.calls.find(c => c.url === '/api/todos' && c.init?.method === 'POST');
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call!.init!.body))).toMatchObject({ source_type: 'manual', title: '周五前交防钓抽查名单' });
    });
    await waitFor(() => expect(screen.getByText('周五前交防钓抽查名单')).toBeInTheDocument());
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

  it('非 http(s) 的 todo url 不渲染为链接 (白名单拦截)', async () => {
    render_();
    await waitFor(() => expect(screen.getByText('复核 LLM 网关加固笔记')).toBeInTheDocument());
    const link = document.querySelector('a[href="javascript:alert(1)"]');
    expect(link).toBeNull();
    // 合法 https 仍保留外链
    const ok = document.querySelector('a[href="https://example.com/waf"]');
    expect(ok).not.toBeNull();
    expect(ok).toHaveAttribute('rel', 'noopener noreferrer');
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
    expect(screen.getByText('待办清单')).toBeInTheDocument();
  });
});

