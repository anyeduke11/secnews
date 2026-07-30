/**
 * KnowledgePage — 4 大领域知识管理 (薄壳)
 *
 * 实际渲染逻辑在 KnowledgeLayout (含 Outlet)。
 * 保留此文件以兼容 App.tsx 现有的 lazy import。
 *
 * 4 大领域子路由:
 *  - /knowledge          → 默认跳转 /knowledge/import
 *  - /knowledge/import   → 信息导入 (KnowledgeImport)
 *  - /knowledge/process  → 处理数据 (KnowledgeProcess)
 *  - /knowledge/compile  → 知识库编译 (KnowledgeCompile)
 *  - /knowledge/compound → 知识复利 (KnowledgeCompound)
 */
import React, { useEffect, useState } from 'react';
import { KnowledgeLayout } from './knowledge/KnowledgeLayout';
import type { KnowledgeAreaKey } from './knowledge/KnowledgeTabs';

interface KnowledgePageProps {
  onBack?: () => void; // 兼容旧 props, 实际由 KnowledgeLayout 内部 useGoHome 处理
}

export function KnowledgePage(_props: KnowledgePageProps) {
  // 抓取各领域条目数 (用于 tab 卡片右上角徽标)。失败时静默跳过, 不影响渲染。
  const [counts, setCounts] = useState<Partial<Record<KnowledgeAreaKey, number | null>>>({});

  useEffect(() => {
    let cancelled = false;
    fetch('/api/knowledge/health')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled || !data) return;
        // 健康度接口给的是 total_items, process 标签显示
        const next: Partial<Record<KnowledgeAreaKey, number | null>> = {
          process: data.total_items ?? null,
        };
        setCounts(prev => ({ ...prev, ...next }));
      })
      .catch(() => { /* 静默失败 */ });
    return () => { cancelled = true; };
  }, []);

  return <KnowledgeLayout areaCounts={counts} />;
}
