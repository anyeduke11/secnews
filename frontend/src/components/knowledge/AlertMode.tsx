/**
 * AlertMode — 告警模式 (Phase 13)
 *
 * @deprecated v0.6.2 (P1-5): 告警展示功能在 workbench/ 中分散到
 * PipelineView (error 队列) + AnalyzeView (cap 触发); 完整 AlertCenter 仍
 * 在 /api/alerts/rules 路由内可访问。本组件保留为兼容旧路由 /knowledge/alert,
 * 计划 v0.7 退役。
 *
 * 告警中心首页，顶部红色横幅显示未读告警数，下方渲染完整 AlertCenter。
 * 用于路由 /knowledge/alert。
 */
import { useState, useEffect } from 'react';
import { Icon } from '../Icon';
import AlertCenter from '../AlertCenter';
import { OnboardingHint } from '../layout/OnboardingHint';

const API_BASE = '/api/alerts/v2';

async function fetchUnreadCount(): Promise<number> {
  const res = await fetch(`${API_BASE}/unread-count`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.count || 0;
}

export function AlertMode() {
  const [unreadCount, setUnreadCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchUnreadCount()
      .then(count => {
        if (!cancelled) {
          setUnreadCount(count);
          setLoading(false);
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(e.message || '加载未读告警数失败');
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-4">
      <OnboardingHint storageKey="kb-alert" title="告警模式">
        <p>集中查看告警规则触发的关注信息。</p>
      </OnboardingHint>

      {/* 红色横幅 — 未读告警概览 */}
      <div
        className="rounded-sm px-4 py-3 flex items-center gap-3"
        style={{
          backgroundColor: 'color-mix(in srgb, #dc2626 10%, transparent)',
          border: '1px solid color-mix(in srgb, #dc2626 25%, transparent)',
        }}
      >
        <div style={{ color: '#dc2626' }}>
          <Icon size={18}>
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </Icon>
        </div>

        <div className="flex-1 min-w-0">
          {loading && (
            <span
              className="text-xs font-bold"
              style={{ color: '#dc2626' }}
            >
              加载中…
            </span>
          )}
          {error && (
            <span
              className="text-xs"
              style={{ color: '#dc2626' }}
            >
              无法加载告警统计
              <button
                type="button"
                className="ml-2 underline"
                style={{ color: '#dc2626' }}
                onClick={() => {
                  setLoading(true);
                  setError(null);
                  fetchUnreadCount()
                    .then(count => { setUnreadCount(count); setLoading(false); })
                    .catch(e => { setError(e.message || '重试失败'); setLoading(false); });
                }}
              >
                重试
              </button>
            </span>
          )}
          {!loading && !error && (
            <span
              className="text-sm font-bold"
              style={{ color: '#dc2626' }}
            >
              {unreadCount !== null && unreadCount > 0
                ? `${unreadCount} 条未读告警`
                : '暂无未读告警'}
            </span>
          )}
        </div>

        {!loading && !error && unreadCount !== null && unreadCount > 0 && (
          <span
            className="inline-flex items-center justify-center rounded-full text-[10px] font-bold min-w-[20px] h-5 px-1.5"
            style={{
              backgroundColor: '#dc2626',
              color: '#fff',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </div>

      {/* 下方渲染完整告警中心 */}
      <AlertCenter />
    </div>
  );
}
