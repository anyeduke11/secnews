/**
 * KnowledgeHubPage — 资料库前厅 (/knowledge/khub, Phase 4 建, C3 接真实聚合 DEV-0191)
 *
 * 定位: 知识菜单的聚合前厅 — 六源速览 + 快捷入口。
 * 数据 (全真实 API): GET /api/knowledge/hub-stats — 后端聚合六源
 *  (wiki_items / wiki_chunks / review_total+due / funnel_total / queue_pending /
 *   quality_checked_24h, 逐源容错, 失败源为 null → 前端显示 …)。
 * 历史注: C3 之前派生口径派生自 /api/kl/pipeline/stats + /api/quality/summary
 *  (见 git blame DEV-0183); hub-stats 端点落地后整体切换。
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getJSON } from '../../lib/api';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import '../shared/editorial/pages.css';

interface HubStats {
  wiki_items: number | null;
  wiki_chunks: number | null;
  review_total: number | null;
  review_due: number | null;
  funnel_total: number | null;
  queue_pending: number | null;
  quality_checked_24h: number | null;
  generated_at: string;
}

/** 前厅快捷入口 (六域) */
const ENTRIES: { label: string; desc: string; to: string }[] = [
  { label: '知识库', desc: '导入 / 加工 / 编译 / 复利 四大领域', to: '/knowledge' },
  { label: '编目室', desc: '知识条目编目与清单管理', to: '/knowledge/library' },
  { label: '知识图谱', desc: '概念邻接与 MITRE 关联', to: '/knowledge/graph' },
  { label: '知识画布', desc: '无限画布 (pan/zoom/节点拖拽)', to: '/knowledge/canvas' },
  { label: '间隔复习', desc: 'SM-2 到期队列', to: '/knowledge/review' },
  { label: '统一检索', desc: '跨实体全文搜索', to: '/search' },
];

const fmt = (v: number | null): string => (v == null ? '…' : String(v));

export function KnowledgeHubPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<HubStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const load = useCallback(() => {
    setError(null);
    getJSON<HubStats>('/api/knowledge/hub-stats')
      .then((s) => { if (dead.current) return; setStats(s); })
      .catch(e => {
        if (dead.current) return;
        setStats(null);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [dead]);

  useEffect(() => { load(); }, [load]);

  return (
      <div className="ed-wrap">
        <header className="ed-head">
          <span className="ed-kicker">KNOWLEDGE HUB</span>
          <h1 className="ed-h1">资料库前厅</h1>
          <p className="ed-sub">先看一眼知识资产的总量与管线动静，再去对应领域动手。</p>
          <div style={{ marginTop: 10 }}>
            <Stamp color="info" variant="hollow">数据源: /api/knowledge/hub-stats (真实端点)</Stamp>
          </div>
        </header>

        <div className="ed-sechead">
          <span>速览</span>
          <span className="ed-note">
            {stats?.generated_at ? `generated ${stats.generated_at.slice(0, 16).replace('T', ' ')}` : '…'}
          </span>
        </div>
        {error ? (
          <EmptyState
            title="聚合统计加载失败"
            description={`${error} — 请确认后端服务运行在 127.0.0.1:8000。`}
            actionLabel="重试"
            onAction={load}
          />
        ) : (
          <div className="ed-grid">
            <div className="ed-card">
              <span className="k">编目条目</span>
              <span className="v">{fmt(stats?.wiki_items ?? null)}</span>
            </div>
            <div className="ed-card">
              <span className="k">wiki chunks</span>
              <span className="v">{fmt(stats?.wiki_chunks ?? null)}</span>
            </div>
            <div className="ed-card">
              <span className="k">复习在册 / 到期</span>
              <span className="v">
                {stats ? fmt(stats.review_total) : '…'}
                <small>到期 {stats ? fmt(stats.review_due) : '…'}</small>
              </span>
            </div>
            <div className="ed-card">
              <span className="k">管线漏斗合计</span>
              <span className="v">{fmt(stats?.funnel_total ?? null)}</span>
            </div>
            <div className="ed-card">
              <span className="k">队列待处理</span>
              <span className="v">{fmt(stats?.queue_pending ?? null)}</span>
            </div>
            <div className="ed-card">
              <span className="k">质量门禁 24h 检查</span>
              <span className="v">{fmt(stats?.quality_checked_24h ?? null)}</span>
            </div>
          </div>
        )}

        <div className="ed-sechead">
          <span>去哪儿</span>
          <span className="ed-note">6 域入口</span>
        </div>
        <div className="ed-grid">
          {ENTRIES.map(e => (
            <div
              key={e.to}
              className="ed-card click"
              role="link"
              tabIndex={0}
              onClick={() => navigate(e.to)}
              onKeyDown={ev => { if (ev.key === 'Enter') navigate(e.to); }}
            >
              <span className="t">{e.label}</span>
              <span className="d">{e.desc}</span>
              <span className="mono" style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>{e.to}</span>
            </div>
          ))}
        </div>
      </div>
  );
}
