/**
 * DeepReadPage — 分类型动态分节渲染测试
 *
 * 测试意图:
 * - 分节集合由后端按文章类型下发, 前端**不得**再假设固定 4 节
 *   (历史上 sections[sec.key] 按固定键取值 → 后端新增的节被静默丢弃、
 *    缺失的节渲染成空白卡, 且 TS 编译期不会报错)
 * - 任意 5~7 节、任意 key 都要渲染出来, 标题用服务端给的而不是本地常量
 * - tone 只按 mint/amber/red 三色锁上色, 未知 tone 回落不崩
 * - 首次生成的等待文案必须说明会真调 AI 且耗时较长 (否则用户以为卡死)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { DeepReadPage } from './DeepReadPage';

const response = (overrides: Record<string, unknown> = {}) => ({
  entity_type: 'hotspot',
  entity_id: 'h-1',
  content_md: '',
  category: 'bid',
  sections: [],
  sections_json: '{}',
  provider: 'sensenova',
  model: 'sensenova-6.8-flash-lite',
  tokens_in: 900,
  tokens_out: 700,
  cost_usd: 0,
  latency_ms: 11000,
  created_at: '2026-08-30T06:00:00+00:00',
  updated_at: '2026-08-30T06:00:00+00:00',
  ...overrides,
});

const sec = (key: string, title: string, tone = 'mint', body = `正文-${title}`) => ({
  key, title, tone, body,
});

/** 后端真实会给的"招标视角"分节 —— 与旧的固定 4 节完全不同 */
const BID_SECTIONS = [
  sec('key_takeaways', '要点速读'),
  sec('tender_card', '项目卡'),
  sec('qualification', '资格硬门槛', 'amber'),
  sec('scoring', '评分与商务项'),
  sec('key_dates', '时间节点', 'amber'),
  sec('next_actions', '我的动作'),
  sec('evidence_gaps', '存疑与未证实', 'amber'),
];

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/deep/hotspot/h-1']}>
      <Routes>
        <Route path="/deep/:type/:id" element={<DeepReadPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function mockOnce(payload: unknown, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(payload),
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('DeepReadPage — 动态分节渲染', () => {
  beforeEach(() => {
    localStorage.removeItem('hotspot-theme');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('渲染后端下发的全部 7 节，标题来自服务端而非本地常量', async () => {
    await mockOnce(response({ sections: BID_SECTIONS }));
    renderPage();

    for (const s of BID_SECTIONS) {
      // eslint-disable-next-line no-await-in-loop
      await waitFor(() => expect(screen.getByText(s.title)).toBeInTheDocument());
    }
    // 旧的硬编码 4 节标题不该凭空出现
    expect(screen.queryByText('关联')).not.toBeInTheDocument();
    expect(screen.queryByText('风险')).not.toBeInTheDocument();
  });

  it('后端只给 2 节时也只渲染 2 节，不补空白卡', async () => {
    await mockOnce(response({
      category: 'ai',
      sections: [sec('key_takeaways', '要点速读'), sec('capability_boundary', '能力边界')],
    }));
    renderPage();

    await waitFor(() => expect(screen.getByText('能力边界')).toBeInTheDocument());
    expect(screen.queryByText('本节暂无内容')).not.toBeInTheDocument();
  });

  it('未识别的 key 与 tone 不致命：仍渲染并回落到默认可见态', async () => {
    await mockOnce(response({
      sections: [sec('brand_new_section_from_server', '新视角小节', 'neon-pink')],
    }));
    renderPage();

    await waitFor(() => expect(screen.getByText('新视角小节')).toBeInTheDocument());
    expect(screen.getByText('正文-新视角小节')).toBeInTheDocument();
  });

  it('展示视角分类，让"按文章类型给不同解读"在界面上可见', async () => {
    await mockOnce(response({ category: 'security', sections: BID_SECTIONS.slice(0, 2) }));
    renderPage();

    await waitFor(() => expect(screen.getByText(/视角 security/)).toBeInTheDocument());
  });

  it('空正文的节显示中文提示而不是泄漏 markdown 下划线语法', async () => {
    await mockOnce(response({
      sections: [sec('remediation', '处置清单', 'mint', '   ')],
    }));
    renderPage();

    await waitFor(() => expect(screen.getByText('处置清单')).toBeInTheDocument());
    expect(screen.getByText('本节暂无内容')).toBeInTheDocument();
    expect(screen.queryByText(/_.*_/)).not.toBeInTheDocument();
  });

  it('首次加载文案承诺真实等待，而不是"生成 4 节"', async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    vi.stubGlobal('fetch', vi.fn().mockImplementation(
      () => new Promise((r) => { resolveFirst = r; }),
    ));
    renderPage();

    expect(screen.getByText(/正在按文章类型生成深度解读/)).toBeInTheDocument();
    expect(screen.queryByText(/4 节/)).not.toBeInTheDocument();

    resolveFirst({ ok: true, json: () => Promise.resolve(response({ sections: BID_SECTIONS })) });
    await waitFor(() => expect(screen.getByText('项目卡')).toBeInTheDocument());
  });

  it('后端错误要显式呈现而不是静默空白', async () => {
    await mockOnce({ detail: { message: 'LLM 返回空; 可能所有 provider 不可用' } }, false);
    renderPage();

    await waitFor(() => expect(screen.getByText(/provider 不可用|深读生成失败|加载深读失败/)).toBeInTheDocument());
  });
});
