// frontend/src/components/EmptyState.test.tsx
// Phase 6 — EmptyState 原子组件测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title="暂无热点" />);
    expect(screen.getByText('暂无热点')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(<EmptyState title="t" description="可手动刷新" />);
    expect(screen.getByText('可手动刷新')).toBeInTheDocument();
  });

  it('hides description in compact mode', () => {
    render(<EmptyState title="t" description="hidden desc" compact />);
    expect(screen.queryByText('hidden desc')).not.toBeInTheDocument();
  });

  it('renders action button when actionLabel and onAction provided', () => {
    const onAction = vi.fn();
    render(<EmptyState title="t" actionLabel="立即刷新" onAction={onAction} />);
    expect(screen.getByText('立即刷新')).toBeInTheDocument();
    fireEvent.click(screen.getByText('立即刷新'));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it('does not render action button when only actionLabel provided', () => {
    render(<EmptyState title="t" actionLabel="OK" />);
    expect(screen.queryByText('OK')).not.toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(
      <EmptyState
        title="t"
        icon={<svg data-testid="custom-icon" />}
      />
    );
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('has role=status and aria-live for accessibility', () => {
    render(<EmptyState title="t" />);
    const root = screen.getByRole('status');
    expect(root).toHaveAttribute('aria-live', 'polite');
  });
});
