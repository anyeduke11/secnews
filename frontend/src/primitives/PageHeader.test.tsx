import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('渲染 h1 标题与主操作', () => {
    render(<PageHeader title="资讯" actions={<button type="button">导出</button>} />);
    expect(screen.getByRole('heading', { level: 1, name: '资讯' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出' })).toBeInTheDocument();
  });

  it('面包屑中间项可点击, 末项为纯文本', () => {
    render(
      <PageHeader
        title="案件详情"
        breadcrumb={[{ label: '知识', href: '/knowledge' }, { label: '案件' }]}
      />
    );
    expect(screen.getByRole('link', { name: '知识' })).toHaveAttribute('href', '/knowledge');
    expect(screen.getByText('案件')).toBeInTheDocument();
  });

  it('meta 与 description 按需出现', () => {
    render(<PageHeader title="t" meta={<span>12 条</span>} description="过去 24 小时" />);
    expect(screen.getByText('12 条')).toBeInTheDocument();
    expect(screen.getByText('过去 24 小时')).toBeInTheDocument();
  });

  it('无 meta/description 时不渲染空节点', () => {
    const { container } = render(<PageHeader title="t" />);
    expect(container.querySelectorAll('p')).toHaveLength(0);
  });
});