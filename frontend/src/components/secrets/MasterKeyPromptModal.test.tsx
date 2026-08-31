/**
 * secrets/MasterKeyPromptModal.test — 验证替换 SecretsPage 三处 window.prompt 的替代组件
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MasterKeyPromptModal } from './MasterKeyPromptModal';

describe('MasterKeyPromptModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders title + hint + submit label', () => {
    render(
      <MasterKeyPromptModal
        title="导入加密 JSON"
        hint="请输入主密钥以解密"
        submitLabel="导入"
        onSubmit={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText('导入加密 JSON')).toBeInTheDocument();
    expect(screen.getByText('请输入主密钥以解密')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导入' })).toBeInTheDocument();
  });

  it('uses default submit label "确定" when not provided', () => {
    render(
      <MasterKeyPromptModal
        title="复制明文"
        onSubmit={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: '确定' })).toBeInTheDocument();
  });

  it('uses type="password" input (no plaintext leak in DOM)', () => {
    render(
      <MasterKeyPromptModal title="x" onSubmit={() => {}} onClose={() => {}} />,
    );
    const input = screen.getByPlaceholderText('主密钥') as HTMLInputElement;
    expect(input.type).toBe('password');
    expect(input.getAttribute('autoComplete')).toBe('new-password');
  });

  it('calls onSubmit with mk when form submitted', async () => {
    const onSubmit = vi.fn();
    render(
      <MasterKeyPromptModal title="x" onSubmit={onSubmit} onClose={() => {}} />,
    );
    const input = screen.getByPlaceholderText('主密钥');
    fireEvent.change(input, { target: { value: 'my-strong-master-key-1234' } });
    const submit = screen.getByRole('button', { name: '确定' });
    fireEvent.click(submit);
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith('my-strong-master-key-1234');
    });
  });

  it('does not call onSubmit when mk is empty', () => {
    const onSubmit = vi.fn();
    render(
      <MasterKeyPromptModal title="x" onSubmit={onSubmit} onClose={() => {}} />,
    );
    const submit = screen.getByRole('button', { name: '确定' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it('calls onClose when 取消 clicked', () => {
    const onClose = vi.fn();
    render(
      <MasterKeyPromptModal title="x" onSubmit={() => {}} onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
