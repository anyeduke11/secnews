/**
 * MaintPage 契约测试 — DEV-0317 健康卡 + DEV-0318 清理/索引卡。
 *
 * 测试意图 (Rule 9): 维护页的职责是把 DB 真实状态如实呈现、清理操作真实生效。
 * DEV-0178 建页时前端类型凭想象 (db_size_mb/table_count/fragmentation,
 * POST /cleanup + body{cutoff_days}, VacuumResp.ok), 与 maintenance_service
 * 真实响应全部对不上 → 健康卡恒显「—」静默两个月、清理按钮永远空跑 (dry_run
 * 默认 true + 参数全被忽略)。本文件 mock 一律采用 **curl 实测响应形状** —
 * 契约再漂移即 CI 红。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { I18nProvider } from '../contexts/I18nContext';
import { MaintPage } from './MaintPage';

const mockFetch = vi.fn();

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERROR',
    json: vi.fn().mockResolvedValue(data),
  } as unknown as Response;
}

/** 真实响应形状 = curl GET /api/maintenance/health (2026-10-11 生产实测)。 */
const HEALTH_FIXTURE = {
  size_bytes: 181809152,
  size_mb: 173.39,
  page_count: 44387,
  page_size: 4096,
  freelist_pages: 137,
  fragmentation_pct: 0.3,
  journal_mode: 'wal',
  db_path: 'backend/hotspot.db',
};

/** 真实响应形状 = curl GET /api/maintenance/dirty-report (嵌套结构)。 */
const DIRTY_FIXTURE = {
  quality_check_logs: { total: 582564, older_than_7_days: 531515 },
  duplicate_hotspots: 2087,
  duplicate_knowledge_items: 75,
  orphan_raw_items: 58,
  invalid_urls: 0,
};

/** 真实响应形状 = maintenance_service.run_vacuum() (status/total_seconds)。 */
const VACUUM_FIXTURE = {
  status: 'ok',
  vacuum_seconds: 1.234,
  reindex_seconds: 0.567,
  analyze_seconds: 0.1,
  total_seconds: 1.901,
  health: HEALTH_FIXTURE,
};

/** 真实响应形状 = maintenance_service.cleanup_quality_logs() (归档语义, 非 deleted 标量)。 */
const CLEANUP_FIXTURE = {
  dry_run: false,
  retention_days: 7,
  cutoff: '2026-10-04T12:00:00+00:00',
  total_rows_before: 583410,
  rows_to_delete: 531515,
  rows_archived: 531515,
  rows_remaining_after: 51895,
  monthly_breakdown: {},
};

function mockHealthApi() {
  mockFetch.mockImplementation((url: string) => {
    if (String(url).startsWith('/api/maintenance/health')) {
      return Promise.resolve(jsonResponse(HEALTH_FIXTURE));
    }
    if (String(url).startsWith('/api/maintenance/dirty-report')) {
      return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
    }
    return Promise.resolve(jsonResponse({}));
  });
}

/** 找出某 URL 前缀的全部 fetch 调用参数。 */
function fetchCallsTo(prefix: string): string[] {
  return mockFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.startsWith(prefix));
}

function renderPage() {
  return render(
    <I18nProvider>
      <MaintPage />
    </I18nProvider>,
  );
}

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  localStorage.setItem('hotspot-locale', 'zh-CN');
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem('hotspot-locale');
});

describe('MaintPage 健康卡 (DEV-0317 契约)', () => {
  it('真实响应形状下四项数字全部呈现 (旧版字段漂移恒显「—」的回归守卫)', async () => {
    mockHealthApi();
    renderPage();

    const card = await screen.findByTestId('maint-card-health');
    // 数据库大小 = size_mb.toFixed(1)
    expect(card).toHaveTextContent('173.4 MB');
    // 空闲页 = freelist_pages (替代旧"表数"行 — 后端 health 无 table_count)
    expect(card).toHaveTextContent('空闲页');
    expect(card).toHaveTextContent('137');
    // 碎片率 = fragmentation_pct 直读 (已是百分数; 旧版 ×100 会把 0.3% 错报 30%)
    expect(card).toHaveTextContent('0.3%');
    // 可清理行 = quality_check_logs.older_than_7_days (嵌套真实形状)
    expect(card).toHaveTextContent('531515');
    // 「—」占位不得出现在有数据的行
    expect(card.textContent).not.toContain('—');
  });

  it('接口失败 → 显式错误态 (监控 fail-loud, 不再伪装成「—」空值)', async () => {
    mockFetch.mockImplementation(() => Promise.reject(new Error('network down')));
    renderPage();

    const card = await screen.findByTestId('maint-card-health');
    await waitFor(() => {
      expect(within_card_error(card)).toBe(true);
    });
  });

  it('点「刷新」重新拉取并更新数字', async () => {
    mockHealthApi();
    renderPage();
    await screen.findByTestId('maint-card-health');
    expect(card_text()).toContain('173.4');

    mockFetch.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/maintenance/health')) {
        return Promise.resolve(jsonResponse({ ...HEALTH_FIXTURE, size_mb: 250.5 }));
      }
      return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
    });
    fireEvent.click(screen.getByRole('button', { name: '刷新' }));
    await waitFor(() => expect(card_text()).toContain('250.5 MB'));
  });
});

describe('MaintPage 清理卡 (DEV-0318 契约)', () => {
  /** 走完整流程: 点「执行清理」→ 出现二次确认 → 点「确认删除」。 */
  async function confirmCleanup() {
    fireEvent.click(await screen.findByRole('button', { name: '执行清理' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认删除' }));
  }

  it('确认后调 cleanup-quality-logs?days=7&dry_run=false (query 参数, 真实删除)', async () => {
    mockHealthApi();
    mockFetch.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/maintenance/cleanup-quality-logs')) {
        return Promise.resolve(jsonResponse(CLEANUP_FIXTURE));
      }
      if (String(url).startsWith('/api/maintenance/health')) {
        return Promise.resolve(jsonResponse(HEALTH_FIXTURE));
      }
      return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
    });
    renderPage();

    await confirmCleanup();

    const calls = fetchCallsTo('/api/maintenance/cleanup-quality-logs');
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain('days=7');
    expect(calls[0]).toContain('dry_run=false');
    // 旧想象契约回归守卫: 不得再打 POST /cleanup (body cutoff_days 会被后端忽略)
    expect(fetchCallsTo('/api/maintenance/cleanup?').length).toBe(0);
    expect(
      mockFetch.mock.calls.some(
        (c) => String(c[0]) === '/api/maintenance/cleanup' || String(c[0]).startsWith('/api/maintenance/cleanup?'),
      ),
    ).toBe(false);

    // 归档语义渲染: 已归档/主表剩余 (旧 {deleted:number} 形状下这两行永不出现)
    const card = await screen.findByTestId('maint-card-cleanup');
    await waitFor(() => {
      expect(card).toHaveTextContent('已归档: 531515');
      expect(card).toHaveTextContent('主表剩余: 51895');
    });
  });

  it('保留天数输入框默认 7, 与健康卡「可清理行」(older_than_7_days) 同口径', async () => {
    mockHealthApi();
    renderPage();
    const input = await screen.findByTestId('maint-cleanup-days');
    expect(input).toHaveValue(7);
  });
});

describe('MaintPage 索引卡 (DEV-0318 契约)', () => {
  it('run_vacuum 真实响应 status=ok → 完成徽章 + 耗时秒数 (旧 ok/duration_ms 字段永不存在)', async () => {
    mockHealthApi();
    mockFetch.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/maintenance/vacuum')) {
        return Promise.resolve(jsonResponse(VACUUM_FIXTURE));
      }
      if (String(url).startsWith('/api/maintenance/health')) {
        return Promise.resolve(jsonResponse(HEALTH_FIXTURE));
      }
      return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
    });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: '执行' }));

    const card = await screen.findByTestId('maint-card-vacuum');
    await waitFor(() => {
      expect(card).toHaveTextContent('耗时: 1.901s');
      expect(card).toHaveTextContent('完成');
    });
  });
});

describe('MaintPage 索引状态块 (DEV-0320 契约)', () => {
  /** 真实响应形状 = 进程内 index_health("full") 实测 (2026-10-11 生产三库)。 */
  const INDEX_HEALTH_FIXTURE = {
    mode: 'full',
    checked_at: '2026-10-11T10:07:00.121888+00:00',
    schemas: [
      {
        schema: 'main', file: 'hotspot.db',
        user_indexes: 259, auto_indexes: 81,
        tables_with_indexes: 119, stat1_covered: 73,
        check: 'ok', check_errors: [], check_ms: 222,
      },
      {
        schema: 'warm', file: 'hotspot-warm.db',
        user_indexes: 41, auto_indexes: 11,
        tables_with_indexes: 23, stat1_covered: 18,
        check: 'ok', check_errors: [], check_ms: 43,
      },
      {
        schema: 'cold', file: 'hotspot-cold.db',
        user_indexes: 2, auto_indexes: 1,
        tables_with_indexes: 2, stat1_covered: 1,
        check: 'ok', check_errors: [], check_ms: 80,
      },
    ],
    totals: { user_indexes: 302, auto_indexes: 93, schemas_ok: 3, schemas_total: 3 },
  };

  function mockIndexHealth(fixture: unknown) {
    mockFetch.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/maintenance/index-health')) {
        return Promise.resolve(jsonResponse(fixture));
      }
      if (String(url).startsWith('/api/maintenance/health')) {
        return Promise.resolve(jsonResponse(HEALTH_FIXTURE));
      }
      if (String(url).startsWith('/api/maintenance/dirty-report')) {
        return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
      }
      return Promise.resolve(jsonResponse({}));
    });
  }

  it('逐 schema 呈现真实索引状态: 计数 / integrity / ANALYZE 统计覆盖', async () => {
    mockIndexHealth(INDEX_HEALTH_FIXTURE);
    renderPage();

    const status = await screen.findByTestId('maint-index-status');
    const mainRow = await screen.findByTestId('maint-index-row-main');
    expect(mainRow).toHaveTextContent('main (hotspot.db)');
    expect(mainRow).toHaveTextContent('索引 259+81'); // user+auto 分列
    expect(mainRow).toHaveTextContent('ok 222ms');
    expect(mainRow).toHaveTextContent('统计 73');
    expect(status).toHaveTextContent('warm');
    expect(status).toHaveTextContent('统计 18');
    expect(status).toHaveTextContent('cold');
    // footer: mode 标签如实 + 汇总
    expect(status).toHaveTextContent('深度检查 (integrity)');
    expect(status).toHaveTextContent('3/3 库正常');
  });

  it('integrity 非 ok → check_errors 首条如实可见 (fail-loud, 不粉饰)', async () => {
    mockIndexHealth({
      ...INDEX_HEALTH_FIXTURE,
      schemas: [
        {
          schema: 'main', file: 'hotspot.db',
          user_indexes: 259, auto_indexes: 81,
          tables_with_indexes: 119, stat1_covered: 73,
          check: '2 issues',
          check_errors: ['Cell 5 missing for rowid 88 in index idx_hotspots_score'],
          check_ms: 301,
        },
      ],
      totals: { user_indexes: 259, auto_indexes: 81, schemas_ok: 0, schemas_total: 1 },
    });
    renderPage();

    const status = await screen.findByTestId('maint-index-status');
    expect(status).toHaveTextContent('2 issues');
    expect(status).toHaveTextContent('idx_hotspots_score');
    expect(status).toHaveTextContent('0/1 库正常');
  });

  it('index-health 接口失败 → 索引状态显式错误态, 健康卡不受影响 (失败态隔离)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/maintenance/index-health')) {
        return Promise.reject(new Error('boom'));
      }
      if (String(url).startsWith('/api/maintenance/health')) {
        return Promise.resolve(jsonResponse(HEALTH_FIXTURE));
      }
      return Promise.resolve(jsonResponse(DIRTY_FIXTURE));
    });
    renderPage();

    const status = await screen.findByTestId('maint-index-status');
    await waitFor(() => {
      expect(status.querySelector('[role="alert"]')).not.toBeNull();
      expect(status).toHaveTextContent('索引状态加载失败');
    });
    // 健康卡照常呈现 (两路并行互不拖累)
    expect(await screen.findByTestId('maint-card-health')).toHaveTextContent('173.4 MB');
  });
});

// ── helpers (组件内文本读取) ─────────────────────────────────
function card_text(): string {
  return document.querySelector('[data-testid="maint-card-health"]')?.textContent ?? '';
}
function within_card_error(card: HTMLElement): boolean {
  return !!card.querySelector('[role="alert"]') && card.textContent!.includes('加载失败');
}
