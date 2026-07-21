/**
 * ErrorBoundary — Phase 1A 设计系统原子
 *
 * React 错误边界。捕获子组件渲染错误，显示降级 UI + 重试按钮。
 *
 * Usage:
 *   <ErrorBoundary onReset={() => refresh()}>
 *     <HotspotGrid items={items} />
 *   </ErrorBoundary>
 */
import React from 'react';
import { Icon } from './Icon';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** 重置回调（用户点击"重试"时调用） */
  onReset?: () => void;
  /** 自定义错误标题 */
  title?: string;
  /** 自定义错误描述 */
  description?: string;
  /** 降级 UI（完全自定义时） */
  fallback?: (err: Error, reset: () => void) => React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Phase 1A: 简单 console.error, 后续可接入 observability
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    if (this.props.fallback) {
      return this.props.fallback(this.state.error!, this.reset);
    }

    return (
      <div
        className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center animate-fade-in"
        style={{ color: 'var(--text-muted)' }}
        role="alert"
      >
        <div
          className="rounded-full p-3 mb-1"
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          <Icon size={20}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </Icon>
        </div>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {this.props.title ?? '出错了'}
        </p>
        <p className="text-xs max-w-md" style={{ color: 'var(--text-secondary)' }}>
          {this.props.description ?? '组件渲染失败，请刷新页面或重试'}
        </p>
        {this.state.error && (
          <details className="text-left max-w-lg w-full">
            <summary
              className="text-xs cursor-pointer focus-ring"
              style={{ color: 'var(--text-muted)' }}
            >
              错误详情
            </summary>
            <pre
              className="text-[10px] mt-2 p-2 rounded overflow-auto"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-secondary)',
                maxHeight: '160px',
              }}
            >
              {this.state.error.stack ?? this.state.error.message}
            </pre>
          </details>
        )}
        <button
          onClick={this.reset}
          className="btn-ghost focus-ring text-xs px-3 py-1.5 mt-1"
        >
          重试
        </button>
      </div>
    );
  }
}
