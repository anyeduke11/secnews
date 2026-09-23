/** ExportActionsCard — 导出动作卡 (原 export cat, 一次性动作归运维) */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExportActionsCard } from './ExportActionsCard';

describe('ExportActionsCard — 导出动作卡', () => {
  it('提供 HTML/XLSX 两个导出入口与报告页跳转', () => {
    render(<MemoryRouter><ExportActionsCard /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /HTML 报告/ })).toHaveAttribute('href', '/api/export');
    expect(screen.getByRole('link', { name: /XLSX 导出/ })).toHaveAttribute('href', '/api/export/xlsx');
    expect(screen.getByRole('link', { name: /报告页/ })).toHaveAttribute('href', '/report');
  });
});
