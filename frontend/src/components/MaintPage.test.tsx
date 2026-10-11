/**
 * MaintPage 健康卡测试 — DEV-0317 契约锁定。
 *
 * 测试意图 (Rule 9): 健康卡的职责是把 DB 真实状态如实呈现。DEV-0178 建页时
 * 前端类型凭想象 (db_size_mb/table_count/fragmentation/cleanup_candidates),
 * 与 maintenance_service 真实响应全部对不上 → 恒显「—」静默两个月, 且页面
 * 零测试。本文件 mock 一律采用 **curl 实测响应形状** — 契约再漂移即 CI 红。
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

// ── helpers (组件内文本读取) ─────────────────────────────────
function card_text(): string {
  return document.querySelector('[data-testid="maint-card-health"]')?.textContent ?? '';
}
function within_card_error(card: HTMLElement): boolean {
  return !!card.querySelector('[role="alert"]') && card.textContent!.includes('加载失败');
}
