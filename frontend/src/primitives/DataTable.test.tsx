import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DataTable, type DataTableColumn } from './DataTable';

interface Row {
  id: string;
  name: string;
  count: number;
}

const columns: DataTableColumn<Row>[] = [
  { key: 'name', header: '名称', render: (r) => r.name },
  { key: 'count', header: '数量', numeric: true, render: (r) => r.count },
];

const rows: Row[] = [
  { id: 'a', name: '甲', count: 3 },
  { id: 'b', name: '乙', count: 12 },
];

describe('DataTable', () => {
  it('渲染表头与单元格', () => {
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
    expect(screen.getByRole('columnheader', { name: '名称' })).toBeInTheDocument();
    expect(screen.getByText('甲')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('numeric 列右对齐 (数字可纵向比较)', () => {
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
    expect(screen.getByRole('columnheader', { name: '数量' })).toHaveClass('text-right');
  });

  it('rows 为空且给 empty 时渲染空态, 不渲染表头', () => {
    render(
      <DataTable columns={columns} rows={[]} rowKey={(r) => r.id} empty={<span>无数据</span>} />
    );
    expect(screen.getByText('无数据')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader')).not.toBeInTheDocument();
  });

  it('onRowClick 回调整行数据与下标', () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} onRowClick={onRowClick} />);
    fireEvent.click(screen.getByText('乙'));
    expect(onRowClick).toHaveBeenCalledWith(rows[1], 1);
  });
});