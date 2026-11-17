/**
 * DataTable — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 粘性表头 / 稳定列宽 / 数字右对齐 / 行 hover 仅变色 (§3: hover 不改布局尺寸)。
 * 统一替换 17 套原生 table。
 */
import React from 'react';

export interface DataTableColumn<T> {
  key: string;
  header: React.ReactNode;
  align?: 'left' | 'right' | 'center';
  /** 数字/日期列: 等宽 + tabular-nums */
  numeric?: boolean;
  width?: number | string;
  render: (row: T, index: number) => React.ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  /** 空数据插槽 */
  empty?: React.ReactNode;
  onRowClick?: (row: T, index: number) => void;
  caption?: string;
  stickyHeader?: boolean;
  maxHeight?: number | string;
}

const ALIGN_CLASS = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
} as const;

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  onRowClick,
  caption,
  stickyHeader = true,
  maxHeight,
}: DataTableProps<T>) {
  if (rows.length === 0 && empty !== undefined) {
    return <div className="py-6 text-center text-[12px]">{empty}</div>;
  }

  return (
    <div className="min-w-0 overflow-auto" style={{ maxHeight }}>
      <table className="w-full border-collapse text-[12px]" style={{ color: 'var(--text-primary)' }}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={c.width ? { width: typeof c.width === 'number' ? `${c.width}px` : c.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((c) => {
              const align = c.align ?? (c.numeric ? 'right' : 'left');
              return (
                <th
                  key={c.key}
                  scope="col"
                  className={`whitespace-nowrap border-b px-2 py-1.5 text-[11px] font-medium ${ALIGN_CLASS[align]} ${
                    stickyHeader ? 'sticky top-0' : ''
                  }`}
                  style={{
                    borderColor: 'var(--line)',
                    backgroundColor: 'var(--bg-card)',
                    color: 'var(--text-secondary)',
                    zIndex: stickyHeader ? 'var(--z-sticky)' : undefined,
                  }}
                >
                  {c.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              onClick={onRowClick ? () => onRowClick(row, i) : undefined}
              className={`border-b last:border-b-0 ${onRowClick ? 'cursor-pointer' : ''}`}
              style={{ borderColor: 'var(--line)', height: 40 }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.backgroundColor = 'var(--bg-hover)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.backgroundColor = '';
              }}
            >
              {columns.map((c) => {
                const align = c.align ?? (c.numeric ? 'right' : 'left');
                return (
                  <td
                    key={c.key}
                    className={`px-2 py-1 align-middle ${ALIGN_CLASS[align]}`}
                    style={{
                      lineHeight: 1.35,
                      fontVariantNumeric: c.numeric ? 'tabular-nums' : undefined,
                    }}
                  >
                    {c.render(row, i)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}