import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AsyncState } from './AsyncState';

describe('AsyncState', () => {
  it('loading 态声明 busy 且不渲染业务内容', () => {
    render(
      <AsyncState status="loading" skeletonRows={2}>
        <span>业务内容</span>
      </AsyncState>
    );
    const root = screen.getByRole('status');
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('业务内容')).not.toBeInTheDocument();
  });

  it('empty 态渲染业务方给的空态文案', () => {
    render(<AsyncState status="empty" emptyTitle="暂无案件" emptyDescription="等待采集" />);
    expect(screen.getByText('暂无案件')).toBeInTheDocument();
    expect(screen.getByText('等待采集')).toBeInTheDocument();
  });

  it('error 态是 alert 且重试按钮可用', () => {
    const onRetry = vi.fn();
    render(<AsyncState status="error" errorMessage="网络中断" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('网络中断');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('ready 态透传 children, stale 时给出过期提示', () => {
    render(
      <AsyncState status="ready" stale>
        <span>列表</span>
      </AsyncState>
    );
    expect(screen.getByText('列表')).toBeInTheDocument();
    expect(screen.getByText('数据已过期, 正在刷新')).toBeInTheDocument();
  });

  it('ready 且非 stale 时不出现提示条', () => {
    render(
      <AsyncState status="ready">
        <span>列表</span>
      </AsyncState>
    );
    expect(screen.queryByText('数据已过期, 正在刷新')).not.toBeInTheDocument();
  });
});