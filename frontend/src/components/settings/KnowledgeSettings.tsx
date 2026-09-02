/**
 * settings/KnowledgeSettings — 知识库设置 (Sentinel V2)。
 *
 * 设计原则:
 * - 顶部 st-head 用途说明 (知识库是 w2 的核心, 没了它决策回顾断链)
 * - st-cellgrid 3 卡 (条目 / 概念 / 最后同步) 取代零碎分布
 * - st-rule 入口 + "进入知识库 →" st-btn primary 行动按钮
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import '../settings/settings-shell.css';

export function KnowledgeSettings() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<{ items?: number; concepts?: number; last_sync?: string } | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/health')
      .then(r => r.json())
      .then(d => setStats({
        items: d.total_items || 0,
        concepts: d.total_concepts || 0,
        last_sync: d.last_sync,
      }))
      .catch(() => {});
  }, []);

  const lastSyncText = stats?.last_sync
    ? stats.last_sync.slice(0, 16).replace('T', ' ')
    : '尚未同步';

  const itemsTone: 'mint' | 'amber' | 'red' =
    (stats?.items ?? 0) === 0 ? 'red'
    : (stats?.items ?? 0) < 100 ? 'amber'
    : 'mint';

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">知识库</h2>
        <p className="st-sub2">
          从热点和情报中提炼出的可检索条目 + 概念节点, 支撑日报回顾 / 决策追溯 / 二次查询.
          不配置此项时, /knowledge 页面为空, 日报会退化为纯热点罗列.
          数据由"知识页面的同步"触发, 不是自动常驻任务.
        </p>
      </div>

      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">条目</span>
          <span className={`st-cellv ${itemsTone === 'mint' ? '' : itemsTone}`}>
            {stats?.items?.toLocaleString() ?? '—'}
          </span>
          <span className="st-cellnote">
            {itemsTone === 'red' ? '未初始化' : itemsTone === 'amber' ? '初始阶段' : '已积累'}
          </span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">概念</span>
          <span className="st-cellv sm">
            {stats?.concepts?.toLocaleString() ?? '—'}
          </span>
          <span className="st-cellnote">实体 / 主题抽取</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">最后同步</span>
          <span className="st-cellv sm">
            {lastSyncText}
          </span>
          <span className="st-cellnote">需在 /knowledge 触发</span>
        </div>
      </div>

      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">下一步</span>
            <div className="st-ctrl">
              <button
                className="st-btn primary"
                onClick={() => navigate('/knowledge')}
              >
                进入知识库 →
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}