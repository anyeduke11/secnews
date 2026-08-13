/**
 * report/ReportPage — 报告页主入口 / 薄壳。
 *
 * 拆自原 ReportPage.tsx (1401 行 → 7 文件, 每文件 ≤ 400 行)。
 * 本文件仅做组合: 模式切换 (日报/周报/月报) + 三个模式组件。
 * 渲染委托 DailyReport / WeeklyReportContent / MonthlyReport。
 *
 * API 保持向后兼容: export function ReportPage({ onBack })
 * (App.tsx lazy import: import('./components/report/ReportPage').then(m => ({ default: m.ReportPage })))
 */
import React, { useState, useCallback } from 'react';
import { Icon } from '../Icon';
import { DailyReport } from './DailyReport';
import { WeeklyReportContent } from './WeeklyReport';
import { MonthlyReport } from './MonthlyReport';
import type { Tab, ReportPageProps } from './types';

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'daily', label: '日报' },
  { id: 'weekly', label: '周报' },
  { id: 'monthly', label: '月报' },
];

export function ReportPage({ onBack }: ReportPageProps) {
  const [activeTab, setActiveTab] = useState<Tab>('daily');

  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab);
  }, []);

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="btn-ghost px-2 py-1.5 text-xs" aria-label="返回首页">
          <Icon><polyline points="15 18 9 12 15 6" /></Icon>
        </button>
        <div>
          <h2 className="text-base font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </Icon>
            报告
          </h2>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>本系统资讯与标讯 · 自动聚合报告</p>
        </div>
      </div>

      {/* Tab 导航 */}
      <div className="flex items-center gap-1 pb-2" style={{ borderBottom: '1px solid var(--border-color)' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className="ink-chip focus-ring transition-colors"
            style={{
              padding: '4px 14px',
              fontSize: '13px',
              fontWeight: activeTab === tab.id ? 600 : 400,
              backgroundColor: activeTab === tab.id ? 'var(--accent)' : 'transparent',
              color: activeTab === tab.id ? 'var(--text-on-light)' : 'var(--text-secondary)',
            }}
            aria-current={activeTab === tab.id ? 'page' : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 内容 */}
      {activeTab === 'daily' && <DailyReport />}
      {activeTab === 'weekly' && <WeeklyReportContent />}
      {activeTab === 'monthly' && <MonthlyReport />}
    </div>
  );
}
