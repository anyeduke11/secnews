/**
 * LayerTable — 三层架构统一表格组件 (v1)
 *
 * Phase 5 设计治理: 消除 QualityRejectionPage / ProjectList / BatchImportDialog
 * 各自实现的 <table> 样式差异, 集中到 design tokens。
 *
 * - thead: var(--bg-secondary) + var(--text-muted) + uppercase 11px
 * - tbody: 行 hover var(--bg-hover) + border-bottom var(--border-color)
 * - 斑马纹可选 (zebra)
 * - 圆角与 LayerCard 对齐: var(--radius-md)
 */
import React from 'react';

export interface LayerTableColumn<T> {
  key: keyof T | string;
  header: string;
  render?: (row: T) => React.ReactNode;
  width?: string;
  align?: 'left' | 'right' | 'center';
  className?: string;
}

interface LayerTableProps<T> {
  columns: LayerTableColumn<T>[];
  data: T[];
  rowKey: (row: T, index: number) => string | number;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  emptyMessage?: string;
  zebra?: boolean;
  /** 紧凑模式 (行 padding 减小) */
  compact?: boolean;
  className?: string;
}

export function LayerTable<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  loading = false,
  emptyMessage = '暂无数据',
  zebra = false,
  compact = false,
  className = '',
}: LayerTableProps<T>) {
  const cellPad = compact ? 'px-2.5 py-1.5' : 'px-3 py-2';

  return (
    <div
      className={`layer-table-wrapper overflow-x-auto rounded-[var(--radius-md)] ${className}`}
      style={{
        border: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ backgroundColor: 'var(--bg-secondary)' }}>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                className={`${cellPad} text-left font-mono font-semibold uppercase tracking-[0.06em]`}
                style={{
                  color: 'var(--text-muted)',
                  fontSize: '10px',
                  textAlign: col.align || 'left',
                  width: col.width,
                  borderBottom: '1px solid var(--border-color)',
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td
                colSpan={columns.length}
                className={`${cellPad} text-center`}
                style={{ color: 'var(--text-muted)' }}
              >
                加载中…
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className={`${cellPad} text-center`}
                style={{ color: 'var(--text-muted)' }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, index) => {
              const key = rowKey(row, index);
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={onRowClick ? 'cursor-pointer' : ''}
                  style={{
                    backgroundColor: zebra && index % 2 === 1 ? 'var(--bg-secondary)' : 'transparent',
                    borderBottom: '1px solid var(--border-color)',
                    transition: 'background-color var(--duration-fast) ease',
                  }}
                  onMouseEnter={(e) => {
                    if (onRowClick) e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor =
                      zebra && index % 2 === 1 ? 'var(--bg-secondary)' : 'transparent';
                  }}
                >
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className={`${cellPad} ${col.className || ''}`}
                      style={{
                        color: 'var(--text-primary)',
                        textAlign: col.align || 'left',
                      }}
                    >
                      {col.render
                        ? col.render(row)
                        : String((row as Record<string, unknown>)[col.key as string] ?? '')}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
