// frontend/src/components/ErrorBoundary.test.tsx
// Phase 6 — ErrorBoundary 错误边界测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

function Boom(): JSX.Element {
  throw new Error('test explosion');
}

function Safe({ text }: { text: string }) {
  return <p>{text}</p>;
}

describe('ErrorBoundary', () => {
  // 静默 React 的 error 警告, 测试中预期会触发
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <Safe text="正常内容" />
      </ErrorBoundary>
    );
    expect(screen.getByText('正常内容')).toBeInTheDocument();
  });

  it('shows fallback UI when child throws', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    // 标题 "出错了" 和描述 "组件渲染失败..." 都会出现, 但只有标题是单实例
    expect(screen.getByText('出错了')).toBeInTheDocument();
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  it('uses custom title and description', () => {
    render(
      <ErrorBoundary title="加载失败" description="请重试或刷新">
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText('加载失败')).toBeInTheDocument();
    expect(screen.getByText('请重试或刷新')).toBeInTheDocument();
  });

  it('calls onReset when 重试 clicked and re-renders children', () => {
    const onReset = vi.fn();
    let shouldThrow = true;
    function Maybe() {
      if (shouldThrow) throw new Error('boom');
      return <Safe text="恢复了" />;
    }
    render(
      <ErrorBoundary onReset={onReset}>
        <Maybe />
      </ErrorBoundary>
    );
    expect(screen.getByText('重试')).toBeInTheDocument();
    shouldThrow = false;
    fireEvent.click(screen.getByText('重试'));
    expect(onReset).toHaveBeenCalledOnce();
    expect(screen.getByText('恢复了')).toBeInTheDocument();
  });

  it('uses custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={(err, reset) => (
        <div>
          <p>custom: {err.message}</p>
          <button onClick={reset}>go</button>
        </div>
      )}>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText(/custom: test explosion/)).toBeInTheDocument();
    expect(screen.getByText('go')).toBeInTheDocument();
  });
});
