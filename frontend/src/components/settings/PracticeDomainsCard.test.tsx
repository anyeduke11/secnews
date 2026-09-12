/**
 * PracticeDomainsCard 组件测试 (Workbench Focus PRD P0.3, DEV-0176)。
 *
 * 覆盖: 渲染 8 域 chips / 点击选中即 PATCH / 再点取消 / 空画像提示 /
 * 保存失败回滚选中态。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PracticeDomainsCard } from './PracticeDomainsCard';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

const VALID_DOMAINS = [
  'network_security',
  'pentest',
  'vuln_research',
  'incident_response',
  'appsec',
  'crypto_security',
  'data_security',
  'compliance',
  'ai_security',
  'threat_hunting',
];

// 与后端 PRACTICE_DOMAIN_LABELS 同源
const LABELS: Record<string, string> = {
  network_security: '网络安全',
  pentest: '渗透攻防',
  vuln_research: '漏洞挖掘',
  incident_response: '应急响应',
  appsec: '应用安全',
  crypto_security: '密码安全',
  data_security: '数据安全',
  compliance: '合规管理',
  ai_security: 'AI 安全',
  threat_hunting: '威胁狩猎',
};

function mockGet(domains: string[] = []) {
  mockFetch.mockImplementation((url: string, options?: any) => {
    if (url === '/api/settings/interests' && !options?.method) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            domains,
            valid_domains: VALID_DOMAINS,
            labels: LABELS,
          }),
      });
    }
    if (url === '/api/settings/interests' && options?.method === 'PATCH') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
    }
    return Promise.resolve({ ok: false });
  });
}

describe('PracticeDomainsCard', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('渲染 10 个实践域 chip (aria-pressed 反映选中态)', async () => {
    mockGet(['ai_security']);
    render(<PracticeDomainsCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'AI 安全' })).toHaveAttribute('aria-pressed', 'true');
    });
    expect(screen.getByRole('button', { name: '漏洞挖掘' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getAllByRole('button')).toHaveLength(10);
  });

  it('点击未选中的域立即 PATCH 保存并显示已保存', async () => {
    mockGet([]);
    render(<PracticeDomainsCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '威胁狩猎' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: '威胁狩猎' }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/settings/interests',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ domains: ['threat_hunting'] }),
        }),
      );
    });
    // 无 I18nProvider 时 useI18n 回退 key 字符串 (仓库已知行为)
    await waitFor(() => {
      expect(screen.getByText('settings.practice_domains.saved')).toBeInTheDocument();
    });
  });

  it('空画像显示不过滤提示', async () => {
    mockGet([]);
    render(<PracticeDomainsCard />);

    await waitFor(() => {
      expect(screen.getByText('settings.practice_domains.empty')).toBeInTheDocument();
    });
  });

  it('保存失败时回滚选中态并提示', async () => {
    mockGet([]);
    mockFetch.mockImplementation((url: string, options?: any) => {
      if (url === '/api/settings/interests' && !options?.method) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              domains: [],
              valid_domains: VALID_DOMAINS,
              labels: LABELS,
            }),
        });
      }
      if (url === '/api/settings/interests' && options?.method === 'PATCH') {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({ ok: false });
    });

    render(<PracticeDomainsCard />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '应用安全' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: '应用安全' }));

    await waitFor(() => {
      expect(screen.getByText('settings.practice_domains.save_failed')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '应用安全' })).toHaveAttribute('aria-pressed', 'false');
  });
});
