import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Inspector } from './Inspector';

describe('Inspector', () => {
  it('open=false 时不渲染任何节点', () => {
    const { container } = render(
      <Inspector open={false} onClose={() => {}} title="详情">
        <span>内容</span>
      </Inspector>
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('open 时以 dialog 角色呈现, 标题即无障碍名称', () => {
    render(
      <Inspector open onClose={() => {}} title="CVE-2026-0001">
        <span>内容</span>
      </Inspector>
    );
    expect(screen.getByRole('dialog', { name: 'CVE-2026-0001' })).toBeInTheDocument();
    expect(screen.getByText('内容')).toBeInTheDocument();
  });

  it('关闭按钮与 Esc 都回调 onClose', () => {
    const onClose = vi.fn();
    render(
      <Inspector open onClose={onClose} title="详情">
        <span>内容</span>
      </Inspector>
    );
    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('关闭后解绑 Esc 监听, 不产生幽灵回调', () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Inspector open onClose={onClose} title="详情">
        <span>内容</span>
      </Inspector>
    );
    rerender(
      <Inspector open={false} onClose={onClose} title="详情">
        <span>内容</span>
      </Inspector>
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});