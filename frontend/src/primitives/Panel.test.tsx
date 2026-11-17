import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Panel } from './Panel';

describe('Panel', () => {
  it('渲染标题与操作区', () => {
    render(
      <Panel title="今日信号" actions={<button type="button">刷新</button>}>
        <p>body</p>
      </Panel>
    );
    expect(screen.getByRole('heading', { name: '今日信号' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '刷新' })).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('无 children 时展示 empty 插槽而非空白容器', () => {
    render(<Panel title="案件" empty={<span>暂无案件</span>} />);
    expect(screen.getByText('暂无案件')).toBeInTheDocument();
  });

  it('有 children 时 empty 插槽不出现', () => {
    render(
      <Panel title="案件" empty={<span>暂无案件</span>}>
        <span>有一条</span>
      </Panel>
    );
    expect(screen.queryByText('暂无案件')).not.toBeInTheDocument();
  });

  it('dense 模式取消内容区内边距 (表格自管留白)', () => {
    const { container } = render(
      <Panel dense>
        <span>x</span>
      </Panel>
    );
    const body = container.querySelector('section > div');
    expect(body?.className).not.toContain('p-3');
  });
});