/**
 * ReviewOverlay — 复习栈弹层三视图测试
 *
 * 测试意图 (2026-09-21 设计稿 §5):
 *  - 会话视图: 空格翻面 (正面标题 → 背面摘要+SM-2), 1/3/5 评分进下一张,
 *    评分请求体走 POST /api/reviews/{type}/{id}/grade; 结束汇总页展示
 *    已评数与评分分布, 每张可撤销 (POST undo)。
 *  - 数据视图: 7 日预报 / 保留率 / 历史流来自真实接口, 不造假数据。
 *  - 管理视图: 卡片表格可暂停 (PATCH {suspended:true}); 搜索加卡走
 *    GET /api/search → POST /api/reviews/{mapped_type}/{id} (knowledge→knowledge_item)。
 *  - Escape 关闭弹层; 全程 mock fetch, 不发真实请求。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import { useState } from 'react';

import { ReviewOverlay, type RvView } from './ReviewOverlay';

const DAY = (offsetDays: number, base = new Date()) =>
  new Date(base.getTime() + offsetDays * 86400000).toISOString();

const DUE_FIXTURE = {
  version: 'test',
  count: 2,
  items: [
    {
      id: 'hotspot-h1', entity_type: 'hotspot', entity_id: 'h1',
      easiness: 2.5, interval: 1, repetitions: 0, due_at: DAY(-1),
      last_grade: null, last_reviewed_at: null,
      title: 'AI 安全周报：供应链攻击抬头', url: 'https://example.com/w',
      category: 'security', excerpt: '本周三家供应商遭投毒。',
    },
    {
      id: 'item-k1', entity_type: 'knowledge_item', entity_id: 'k1',
      easiness: 2.3, interval: 2, repetitions: 1, due_at: DAY(0),
      last_grade: 4, last_reviewed_at: DAY(-2),
      title: 'SM-2 间隔重复笔记', url: null, category: 'method', excerpt: null,
    },
  ],
};

const CARDS_FIXTURE = {
  version: 'test',
  count: 2,
  items: [
    {
      id: 'hotspot-h1', entity_type: 'hotspot', entity_id: 'h1',
      easiness: 2.5, interval: 1, repetitions: 0, due_at: DAY(-1),
      last_grade: null, last_reviewed_at: null, suspended: 0,
      title: 'AI 安全周报：供应链攻击抬头', url: null, category: 'security', excerpt: null,
    },
    {
      id: 'item-k2', entity_type: 'knowledge_item', entity_id: 'k2',
      easiness: 2.1, interval: 3, repetitions: 2, due_at: DAY(3),
      last_grade: 3, last_reviewed_at: DAY(-3), suspended: 1,
      title: '零信任落地清单', url: null, category: 'method', excerpt: null,
    },
  ],
};

const STATS_FIXTURE = {
  stats: {
    total: 5, due: 2, avg_easiness: 2.4, retention_30d: 0.75,
    grade_distribution: { '5': 3, '3': 1 }, suspended_count: 1,
  },
};

const FORECAST_FIXTURE = {
  items: Array.from({ length: 7 }, (_, i) => ({
    date: `2026-09-2${i + 2}`,
    count: i === 0 ? 2 : i === 3 ? 1 : 0,
  })),
};

const HISTORY_FIXTURE = {
  count: 1,
  items: [{
    id: 9, entity_type: 'hotspot', entity_id: 'h1', grade: 5,
    new_interval: 6, reverted: 0, created_at: DAY(-1),
  }],
};

const SEARCH_FIXTURE = {
  result: {
    query: '零信任',
    items: [
      { entity_type: 'knowledge', entity_id: 'k9', title: '零信任入门九讲', category: 'method' },
      { entity_type: 'hotspot', entity_id: 'h9', title: '零信任厂商矩阵', category: 'security' },
    ],
  },
};

/** view 状态壳: 模拟父组件的 open/view 切换 */
function Harness({ initial, onClose }: { initial: RvView; onClose?: () => void }) {
  const [view, setView] = useState<RvView>(initial);
  const [open, setOpen] = useState(true);
  return (
    <ReviewOverlay
      open={open}
      view={view}
      onViewChange={setView}
      onClose={() => { setOpen(false); onClose?.(); }}
      onDataChanged={() => {}}
    />
  );
}

interface CallRecord { url: string; init?: RequestInit }

function makeFetch() {
  const calls: CallRecord[] = [];
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes('/grade')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ item: { interval: 6, due_at: DAY(6) } }),
      } as Response);
    }
    if (url.includes('/undo')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ item: {} }) } as Response);
    }
    if (url.startsWith('/api/reviews/due')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(DUE_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/forecast')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(FORECAST_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/history')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(HISTORY_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(STATS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/reviews/cards')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(CARDS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/search')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SEARCH_FIXTURE) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
  return { fn, calls };
}

describe('ReviewOverlay — 复习栈弹层三视图', () => {
  let api: ReturnType<typeof makeFetch>;

  beforeEach(() => {
    api = makeFetch();
    vi.stubGlobal('fetch', api.fn);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('会话视图: 正面标题 + 空格翻面看摘要与 SM-2 参数', async () => {
    render(<Harness initial="session" />);
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());
    // 正面不泄露摘要
    expect(screen.queryByText(/本周三家供应商遭投毒/)).not.toBeInTheDocument();
    expect(screen.getByText('1 / 2 · 已评 0')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: ' ' });
    await waitFor(() => expect(screen.getByText(/本周三家供应商遭投毒/)).toBeInTheDocument());
    expect(screen.getByText('EF')).toBeInTheDocument();
  });

  it('会话视图: 评分走 POST grade 进下一张; 评完出汇总页可逐张撤销', async () => {
    render(<Harness initial="session" />);
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /记得牢/ }));
    await waitFor(() => {
      const call = api.calls.find(c => c.url.includes('/grade'));
      expect(call).toBeTruthy();
    });
    const gradeRec = api.calls.find(c => c.url.includes('/grade'))!;
    expect(gradeRec.url).toBe('/api/reviews/hotspot/h1/grade');
    expect(JSON.parse(String(gradeRec.init?.body))).toEqual({ grade: 5 });

    // 第二张 (无摘要卡 → 背面提示语)
    await waitFor(() => expect(screen.getByText('SM-2 间隔重复笔记')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /模糊/ }));
    await waitFor(() => expect(screen.getByText('本次复习完成')).toBeInTheDocument());

    // 汇总: 已评 2 张 + 分布 + 逐张撤销
    expect(screen.getByText(/已评/)).toHaveTextContent('2');
    expect(screen.getByText('记得牢 1')).toBeInTheDocument();
    expect(screen.getByText('模糊 1')).toBeInTheDocument();

    const undoBtns = screen.getAllByRole('button', { name: '撤销' });
    expect(undoBtns).toHaveLength(2);
    fireEvent.click(undoBtns[0]);
    await waitFor(() => {
      const call = api.calls.find(c => c.url.includes('/undo'));
      expect(call).toBeTruthy();
    });
    const undoRec = api.calls.find(c => c.url.includes('/undo'))!;
    expect(undoRec.url).toBe('/api/reviews/hotspot/h1/undo');
    await waitFor(() => expect(screen.getByText('已撤销')).toBeInTheDocument());
  });

  it('空队列 → 汇总页如实显示 0 张, 不造假卡', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/reviews/due')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<Harness initial="session" />);
    await waitFor(() => expect(screen.getByText('本次复习完成')).toBeInTheDocument());
    expect(screen.getByText('到期队列为空, 没有需要复习的卡片。')).toBeInTheDocument();
  });

  it('数据视图: 7 日预报柱 + 保留率 + 历史流 (reverted 标记)', async () => {
    render(<Harness initial="data" />);
    await waitFor(() => expect(screen.getByText('7 日到期预报')).toBeInTheDocument());
    expect(screen.getByText('保留率 30d')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('75%')).toBeInTheDocument());
    expect(screen.getByText(/在册/)).toHaveTextContent('5');
    expect(screen.getByText(/暂停/)).toHaveTextContent('1');
    // 历史流: g5 · 下次 6d
    await waitFor(() => expect(screen.getByText('g5 · 下次 6d')).toBeInTheDocument());
  });

  it('管理视图: 表格含暂停状态卡; 暂停/恢复走 PATCH {suspended}', async () => {
    render(<Harness initial="manage" />);
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());

    // k2 处于 suspended → 状态列显示「暂停」
    const k2row = screen.getByText('零信任落地清单').closest('tr') as HTMLElement;
    expect(within(k2row).getByText('暂停')).toBeInTheDocument();

    const row = screen.getByText('AI 安全周报：供应链攻击抬头').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '暂停' }));
    await waitFor(() => {
      const call = api.calls.find(c => c.init?.method === 'PATCH');
      expect(call).toBeTruthy();
    });
    const patchRec = api.calls.find(c => c.init?.method === 'PATCH')!;
    expect(patchRec.url).toBe('/api/reviews/hotspot/h1');
    expect(JSON.parse(String(patchRec.init!.body))).toEqual({ suspended: true });
  });

  it('管理视图: 搜索加卡 — knowledge 来源映射为 knowledge_item', async () => {
    render(<Harness initial="manage" />);
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());

    const input = screen.getByLabelText('搜索加入复习卡');
    fireEvent.change(input, { target: { value: '零信任' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));

    await waitFor(() => expect(screen.getByText('零信任入门九讲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: '加入复习' })[0]);

    await waitFor(() => {
      const call = api.calls.find(c => c.init?.method === 'POST');
      expect(call).toBeTruthy();
    });
    const postRec = api.calls.find(c => c.init?.method === 'POST')!;
    expect(postRec.url).toBe('/api/reviews/knowledge_item/k9');
    // 已加入态
    await waitFor(() => expect(screen.getByText('已加入')).toBeInTheDocument());
  });

  it('Escape 关闭弹层 (回调 onClose)', async () => {
    const onClose = vi.fn();
    render(<Harness initial="data" onClose={onClose} />);
    await waitFor(() => expect(screen.getByText('7 日到期预报')).toBeInTheDocument());
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('tab 切换: 会话 → 数据 → 管理按需拉取对应接口', async () => {
    render(<Harness initial="session" />);
    await waitFor(() => expect(screen.getByRole('tab', { name: '数据' })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('tab', { name: '数据' }));
    await waitFor(() => expect(screen.getByText('7 日到期预报')).toBeInTheDocument());
    expect(api.calls.some(c => c.url.startsWith('/api/reviews/forecast'))).toBe(true);

    fireEvent.click(screen.getByRole('tab', { name: '管理' }));
    await waitFor(() => expect(screen.getByText('AI 安全周报：供应链攻击抬头')).toBeInTheDocument());
    expect(api.calls.some(c => c.url.startsWith('/api/reviews/cards'))).toBe(true);
  });
});
