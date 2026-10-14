/**
 * NewsAlertList — 资讯告警列表 (2026-09-27 四模式 P1, spec §4)
 *
 * 数据: GET /api/alerts/v2?rule_type= (4 规则域, 不含 CodeGarden 项目告警)。
 * 操作: tab 过滤 / 单条已读 / 全部已读 / 解决。severity 色条 + rule_type 标签
 * + description 首段 (LLM reason | 摘要)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getNewsAlerts, markAlertRead, markAllAlertsRead, resolveAlert,
  ALERT_RULE_LABELS,
  type NewsAlertEvent,
} from '../../api/secnews';
import { useReactions } from '../../hooks/useReactions';
import { ReactionButtons, useReactionAction } from './ReactionButtons';

const TABS: Array<{ key: string; label: string }> = [
  { key: '', label: '全部' },
  { key: 'critical_vuln', label: '漏洞' },
  { key: 'major_security_event', label: '安全事件' },
  { key: 'major_ai_security_event', label: 'AI 安全事件' },
  { key: 'must_know_regulatory', label: '合规时限' },
];

const SEV_CLASS: Record<string, string> = {
  critical: 'sev-critical', high: 'sev-high', medium: 'sev-medium',
};

export function NewsAlertList() {
  const [items, setItems] = useState<NewsAlertEvent[] | null>(null);
  const [tab, setTab] = useState('');
  const nav = useNavigate();
  // DEV-0326: 赞/踩覆盖告警面 — 仅当告警可归因到真实 hotspot 行 (item_id 非空) 才渲染
  const { reactionOf, available: reactionsAvailable } = useReactions();
  const doReact = useReactionAction();

  const reload = useCallback(async (ruleType: string) => {
    try {
      const d = await getNewsAlerts(ruleType || undefined);
      setItems(d.items ?? []);
    } catch { setItems([]); }
  }, []);

  useEffect(() => { void reload(tab); }, [tab, reload]);

  const openHref = (a: NewsAlertEvent) =>
    a.source_url && /^https?:\/\//.test(a.source_url) ? a.source_url : null;

  if (items === null) {
    return <div className="news-alert-list"><p className="na-empty">载入中…</p></div>;
  }
  return (
    <div className="news-alert-list">
      <div className="na-head">
        <div className="na-tabs" role="tablist">
          {TABS.map(t => (
            <button key={t.key} role="tab" aria-selected={tab === t.key}
              className={`na-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
        </div>
        <div className="na-ops">
          <button className="abtn" onClick={() => { void markAllAlertsRead().then(() => reload(tab)); }}>全部已读</button>
        </div>
      </div>
      {items.length === 0 ? (
        <p className="na-empty">当前无可执行告警 — 系统每轮采集后自动扫描</p>
      ) : (
        <ul className="na-items">
          {items.map(a => (
            <li key={a.id} className={`na-item ${SEV_CLASS[a.severity] ?? ''}${a.status === 'unread' ? ' unread' : ''}`}>
              <div className="na-bar">
                <span className="na-sev">{a.severity}</span>
                <span className="na-rule">{ALERT_RULE_LABELS[a.rule_type] ?? a.rule_type}</span>
                <span className="na-time num">{a.created_at.slice(5, 16).replace('T', ' ')}</span>
              </div>
              <div className="na-title">{a.title}</div>
              <div className="na-desc">{a.description}</div>
              <div className="na-src">{a.source ?? ''}</div>
              <div className="na-actions">
                {a.item_id && (
                  <button className="abtn" onClick={() => nav(`/deep/hotspot/${a.item_id}`)}>进入深读</button>
                )}
                {openHref(a) && (
                  <button className="abtn" onClick={() => window.open(openHref(a)!, '_blank', 'noopener')}>查看原文</button>
                )}
                {a.status === 'unread' && (
                  <button className="abtn" onClick={() => { void markAlertRead(a.id).then(() => reload(tab)); }}>已读</button>
                )}
                <button className="abtn" onClick={() => { void resolveAlert(a.id).then(() => reload(tab)); }}>解决</button>
                {a.item_id && reactionsAvailable && (
                  <ReactionButtons item={{ id: a.item_id, title: a.title }} current={reactionOf(a.item_id)} onReact={doReact} />
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
