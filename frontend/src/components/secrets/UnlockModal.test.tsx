/**
 * UnlockModal.test.tsx — D1 (Batch ⑧) OAuth 按钮测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UnlockModal } from './UnlockModal';

describe('UnlockModal — OAuth 按钮', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as any;
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('OAuth 未配置时不显示按钮', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        enabled: false, client_id: '', redirect_uri: '', authorize_url: '', scope: '',
      }),
    });

    render(<UnlockModal onSubmit={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.queryByTestId('oauth-unlock-btn')).toBeNull();
    });
  });

  it('OAuth 已配置时显示按钮', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        enabled: true,
        client_id: 'test-client',
        redirect_uri: 'https://app.example.com/cb',
        authorize_url: 'https://auth.example.com/authorize?response_type=code',
        scope: 'openid',
      }),
    });

    render(<UnlockModal onSubmit={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId('oauth-unlock-btn')).toBeTruthy();
    });
  });

  it('点击 OAuth 按钮写入 sessionStorage 并跳转', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        enabled: true,
        client_id: 'test-client',
        redirect_uri: 'https://app.example.com/cb',
        authorize_url: 'https://auth.example.com/authorize?response_type=code',
        scope: 'openid',
      }),
    });

    // 阻止实际跳转
    const origLocation = window.location;
    delete (window as any).location;
    (window as any).location = { href: '' };

    render(<UnlockModal onSubmit={vi.fn()} onClose={vi.fn()} />);
    const btn = await waitFor(() => screen.getByTestId('oauth-unlock-btn'));
    fireEvent.click(btn);

    await waitFor(() => {
      expect(sessionStorage.getItem('oauth_state')).toBeTruthy();
    });
    expect(window.location.href).toContain('state=');

    (window as any).location = origLocation;
  });

  it('master_key 输入 + 提交 onSubmit', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ enabled: false, client_id: '', redirect_uri: '', authorize_url: '', scope: '' }),
    });

    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<UnlockModal onSubmit={onSubmit} onClose={vi.fn()} />);

    const input = screen.getByPlaceholderText('主密钥') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'master-key-12345' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith('master-key-12345');
    });
  });

  it('短 master_key 报错', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ enabled: false, client_id: '', redirect_uri: '', authorize_url: '', scope: '' }),
    });

    render(<UnlockModal onSubmit={vi.fn()} onClose={vi.fn()} />);

    const input = screen.getByPlaceholderText('主密钥') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'short' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByText(/至少 12 字符/)).toBeTruthy();
    });
  });
});