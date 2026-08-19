/**
 * settings/ExportSettings — 数据导出设置。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 ExportSettings (~553-588 行)。
 * 纯结构拆分: 渲染逻辑逐字迁移。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';

export function ExportSettings() {
  const navigate = useNavigate();

  return (
    <div className="space-y-2">
      <div className="card-base">
        <div className="px-2.5 py-1.5">
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>数据导出</span>
          <p className="text-[9px] mt-1 mb-1.5" style={{ color: 'var(--text-muted)' }}>
            导出热点数据为静态 HTML 报告或 XLSX 表格
          </p>
          <div className="flex gap-1.5">
            <button
              onClick={() => window.open('/api/export', '_blank')}
              className="btn-secondary btn-sm flex-1"
            >
              HTML 报告
            </button>
            <button
              onClick={() => window.open('/api/export/xlsx', '_blank')}
              className="btn-secondary btn-sm flex-1"
            >
              XLSX 导出
            </button>
            <button
              onClick={() => navigate('/report')}
              className="btn-secondary btn-sm flex-1"
            >
              日报/周报
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
