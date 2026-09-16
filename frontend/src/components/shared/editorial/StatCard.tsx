/**
 * StatCard — 编辑部统计卡 (B3, DEV-0192)
 *
 * k/v/d 三插槽 (键 / 值 / 描述), 与 .ed-card 同语言; 供看板顶部统计条复用。
 */
import React from 'react';

interface StatCardProps {
  k: React.ReactNode;
  v: React.ReactNode;
  d?: React.ReactNode;
}

export function StatCard({ k, v, d }: StatCardProps) {
  return (
    <div className="ed-card" data-testid="stat-card">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
      {d != null && <span className="d">{d}</span>}
    </div>
  );
}

/** 统计条: 多张 StatCard 的网格容器 */
export function StatStrip({ children }: { children: React.ReactNode }) {
  return (
    <div className="ed-grid" style={{ marginBottom: 4 }} data-testid="stat-strip">
      {children}
    </div>
  );
}
