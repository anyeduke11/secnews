// frontend/src/components/SettingsPage.tsx
// Crawler v2 — 独立设置页面（报纸编辑风，紧凑排版，完整功能整合）
//
// v5 优化: 报纸编辑风排版全面收紧，新增保留期/缓存/采集调度/知识库/导出设置，
//          侧边导航更窄，卡片间距更紧凑，整体风格与 Header 一致.

import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRefreshInterval } from '../hooks/useRefreshInterval';
import { QualitySettings } from './settings/QualitySettings';
import { SourceSettings } from './settings/SourceSettings';
import { ProxySettings } from './settings/ProxySettings';
import { MCPSettingsCard } from './settings/MCPSettingsCard';
import { Icon } from './Icon';

// ---------------------------------------------------------------------------
// 设置区段定义
// ---------------------------------------------------------------------------
type SectionKey = 'general' | 'collection' | 'network' | 'sync' | 'integration' | 'secrets' | 'alerts' | 'knowledge' | 'export' | 'maintenance' | 'about';

interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  desc?: string;
}

const SECTIONS: SectionDef[] = [
  {
    key: 'general',
    label: '通用',
    icon: <Icon size={12}><circle cx="12" cy="12" r="3" /><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" /></Icon>,
    desc: '主题 / 刷新 / 维护',
  },
  {
    key: 'collection',
    label: '采集',
    icon: <Icon size={12}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></Icon>,
    desc: '质量 / 信源 / 调度',
  },
  {
    key: 'network',
    label: '网络',
    icon: <Icon size={12}><path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><circle cx="12" cy="20" r="1" /></Icon>,
    desc: '代理 / 连接',
  },
  {
    key: 'sync',
    label: '同步',
    icon: <Icon size={12}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Icon>,
    desc: 'WebDAV / 跨设备',
  },
  {
    key: 'integration',
    label: '集成',
    icon: <Icon size={12}><path d="M4 17l6-6-4-4" /><path d="M12 19h8" /></Icon>,
    desc: 'MCP / 外部工具',
  },
  {
    key: 'secrets',
    label: '密钥',
    icon: <Icon size={12}><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>,
    desc: 'API Key / 凭据',
  },
  {
    key: 'alerts',
    label: '告警',
    icon: <Icon size={12}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></Icon>,
    desc: '规则 / 通知',
  },
  {
    key: 'knowledge',
    label: '知识库',
    icon: <Icon size={12}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></Icon>,
    desc: '同步 / 导入',
  },
  {
    key: 'export',
    label: '导出',
    icon: <Icon size={12}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></Icon>,
    desc: '报告 / 格式',
  },
  {
    key: 'maintenance',
    label: '维护',
    icon: <Icon size={12}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></Icon>,
    desc: 'VACUUM / 清理 / 去重',
  },
  {
    key: 'about',
    label: '关于',
    icon: <Icon size={12}><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></Icon>,
    desc: '版本 / 运行状态',
  },
];

// ---------------------------------------------------------------------------
// 通用设置
// ---------------------------------------------------------------------------
function GeneralSettings({ onThemeToggle, theme }: { onThemeToggle: () => void; theme: 'dark' | 'light' }) {
  const { options: refreshOptions, interval: currentInterval, setInterval: setRefreshInterval } = useRefreshInterval();

  return (
    <div className="space-y-2">
      {/* 主题切换 */}
      <div className="card-compact">
        <div className="flex items-center justify-between px-2.5 py-1.5">
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>主题</span>
          <div className="flex gap-1">
            <button
              onClick={() => theme === 'dark' && onThemeToggle()}
              className="px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: theme === 'light' ? 'var(--accent)' : 'var(--bg-hover)',
                color: theme === 'light' ? 'var(--text-on-color)' : 'var(--text-secondary)',
                border: `1px solid ${theme === 'light' ? 'var(--accent)' : 'var(--border-color)'}`,
              }}
            >
              日报版
            </button>
            <button
              onClick={() => theme === 'light' && onThemeToggle()}
              className="px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: theme === 'dark' ? 'var(--accent)' : 'var(--bg-hover)',
                color: theme === 'dark' ? 'var(--text-on-color)' : 'var(--text-secondary)',
                border: `1px solid ${theme === 'dark' ? 'var(--accent)' : 'var(--border-color)'}`,
              }}
            >
              夜读版
            </button>
          </div>
        </div>
      </div>

      {/* 自动刷新 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>自动刷新</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
              当前: {refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {refreshOptions.map(opt => {
              const active = currentInterval === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setRefreshInterval(opt.value)}
                  className="px-2 py-0.5 text-[9px] font-medium rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                    color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-color)'}`,
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* 自动刷新 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>自动刷新</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
              当前: {refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {refreshOptions.map(opt => {
              const active = currentInterval === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setRefreshInterval(opt.value)}
                  className="px-2 py-0.5 text-[9px] font-medium rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                    color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-color)'}`,
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 同步设置
// ---------------------------------------------------------------------------
function SyncSettings() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<{
    configured?: boolean;
    last_sync_at?: string | null;
    last_sync_status?: string | null;
    auto_sync_enabled?: boolean;
    webdav_url?: string;
  } | null>(null);

  useEffect(() => {
    fetch('/api/sync/status')
      .then(r => r.json())
      .then(d => setStatus(d.status || d))
      .catch(() => {});
  }, []);

  const handleToggleAuto = async () => {
    try {
      await fetch('/api/sync/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !status?.auto_sync_enabled }),
      });
      setStatus(s => s ? { ...s, auto_sync_enabled: !s.auto_sync_enabled } : s);
    } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>跨端同步</span>
            {status?.configured && (
              <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
                backgroundColor: status?.auto_sync_enabled
                  ? 'color-mix(in srgb, var(--color-success) 9%, transparent)'
                  : 'color-mix(in srgb, var(--text-muted) 9%, transparent)',
                color: status?.auto_sync_enabled ? 'var(--color-success)' : 'var(--text-muted)',
              }}>
                {status?.auto_sync_enabled ? '自动同步' : '手动同步'}
              </span>
            )}
          </div>

          {!status?.configured ? (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              通过 WebDAV (坚果云) 在设备间同步配置和密钥
            </p>
          ) : (
            <div className="space-y-1 mb-1.5">
              <div className="flex items-center gap-1.5 text-[9px]">
                <span className="font-mono truncate flex-1" style={{ color: 'var(--text-muted)' }} title={status.webdav_url}>
                  {status.webdav_url}
                </span>
                <span className="font-mono shrink-0" style={{ color: status.last_sync_status === 'success' ? 'var(--color-success)' : 'var(--text-muted)' }}>
                  {status.last_sync_at ? `上次: ${status.last_sync_at.slice(0, 10)}` : '未同步'}
                </span>
              </div>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={status?.auto_sync_enabled ?? false} onChange={handleToggleAuto} className="w-3 h-3" />
                <span className="text-[9px]" style={{ color: 'var(--text-secondary)' }}>采集后自动同步</span>
              </label>
            </div>
          )}

          <button
            onClick={() => navigate('/sync')}
            className="btn-secondary btn-sm w-full text-center"
          >
            {status?.configured ? '详细配置' : '配置同步'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 密钥状态卡片
// ---------------------------------------------------------------------------
function SecretsStatusCard() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<{ setup?: boolean; unlocked?: boolean; remaining_seconds?: number; total?: number } | null>(null);
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/secrets/status')
      .then(r => r.json())
      .then(d => setStatus(d))
      .catch(() => {});
    fetch('/api/secrets?limit=5')
      .then(r => r.json())
      .then(d => setItems(d.items || []))
      .catch(() => {});
  }, []);

  const ttlColor = status?.remaining_seconds != null && status.remaining_seconds < 300
    ? 'var(--color-error)'
    : status?.remaining_seconds != null && status.remaining_seconds < 600
      ? 'var(--color-warning)'
      : 'var(--color-general)';

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>密钥管理器</span>
            <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
              backgroundColor: status?.unlocked
                ? 'color-mix(in srgb, var(--color-success) 9%, transparent)'
                : status?.setup
                  ? 'color-mix(in srgb, var(--color-warning) 9%, transparent)'
                  : 'color-mix(in srgb, var(--text-muted) 9%, transparent)',
              color: status?.unlocked ? 'var(--color-success)' : status?.setup ? 'var(--color-warning)' : 'var(--text-muted)',
            }}>
              {status?.unlocked ? '已解锁' : status?.setup ? '已锁定' : '未设置'}
            </span>
          </div>
          {status?.unlocked && status.remaining_seconds != null && (
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>剩余锁定时间</span>
              <span className="text-[9px] font-mono font-bold" style={{ color: ttlColor }}>
                {Math.floor(status.remaining_seconds / 60)}:{String(status.remaining_seconds % 60).padStart(2, '0')}
              </span>
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                · {status.total ?? items.length} 条密钥
              </span>
            </div>
          )}
          {items.length > 0 && status?.unlocked && (
            <div className="space-y-0.5 mb-1.5">
              {items.slice(0, 3).map((item: any) => (
                <div key={item.id} className="flex items-center gap-1.5 text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  <span className="w-2.5 h-2.5 rounded flex items-center justify-center" style={{ backgroundColor: 'color-mix(in srgb, var(--color-ai) 15%, transparent)', fontSize: 6 }}>
                    {item.name?.charAt(0)?.toUpperCase() || 'K'}
                  </span>
                  <span className="truncate flex-1">{item.name}</span>
                  <span>{'●'.repeat(6)}</span>
                </div>
              ))}
              {(status.total ?? items.length) > 3 && (
                <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>+{(status.total ?? items.length) - 3} 条更多...</p>
              )}
            </div>
          )}
          {!status?.setup && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              设置主密钥以安全存储 LLM API Key 等敏感凭据
            </p>
          )}
          <div className="flex gap-1.5">
            <button
              onClick={() => navigate('/secrets')}
              className="btn-secondary btn-sm flex-1"
            >
              管理密钥
            </button>
            {status?.unlocked && (
              <button
                onClick={async () => {
                  try { await fetch('/api/secrets/lock', { method: 'POST' }); } catch {}
                  window.location.reload();
                }}
                className="btn-secondary btn-sm"
                style={{ color: 'var(--color-error)' }}
              >
                立即锁定
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 告警规则
// ---------------------------------------------------------------------------
function AlertSettings() {
  const [rules, setRules] = useState<any[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/alerts/rules')
      .then(r => r.json())
      .then(d => {
        setRules(d.items || []);
        setCount(d.count || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (rule: any) => {
    try {
      await fetch(`/api/alerts/rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      setRules(prev => prev.map(r => r.id === rule.id ? { ...r, enabled: !r.enabled } : r));
    } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>告警规则 ({count})</span>
          </div>
          {loading ? (
            <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
          ) : rules.length === 0 ? (
            <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>暂无告警规则</p>
          ) : (
            <div className="space-y-0.5">
              {rules.map((rule: any) => (
                <div key={rule.id} className="flex items-center gap-1.5 px-1.5 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
                  <span className="text-[9px] font-mono flex-1 truncate" style={{ color: 'var(--text-primary)' }} title={rule.name}>
                    {rule.name}
                  </span>
                  <span className="text-[8px] font-mono" style={{ color: 'var(--text-muted)' }}>
                    {rule.cooldown_sec ? `${Math.round(rule.cooldown_sec / 3600)}h` : '-'}
                  </span>
                  <button
                    onClick={() => handleToggle(rule)}
                    className="text-[9px] px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: rule.enabled ? 'color-mix(in srgb, var(--color-success) 9%, transparent)' : 'transparent',
                      color: rule.enabled ? 'var(--color-success)' : 'var(--text-muted)',
                      border: `1px solid ${rule.enabled ? 'var(--color-success)' : 'var(--border-color)'}`,
                    }}
                  >
                    {rule.enabled ? '开' : '关'}
                  </button>
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
            告警规则在采集时自动评估，触发后发送通知
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 采集调度信息
// ---------------------------------------------------------------------------
function CollectionScheduleInfo() {
  const [health, setHealth] = useState<{ collect_interval_seconds?: number; components?: { collectors?: any; scheduler?: any } } | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealth(d))
      .catch(() => {});
  }, []);

  const interval = health?.collect_interval_seconds ? Math.round(health.collect_interval_seconds / 60) : null;
  const lastRun = health?.components?.collectors?.last_run;
  const jobs = health?.components?.scheduler?.details?.length ?? 0;

  return (
    <div className="card-compact">
      <div className="px-2.5 py-1.5">
        <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>采集调度</span>
        <div className="grid grid-cols-3 gap-1.5 mt-1.5 text-[9px]">
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">间隔</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{interval ? `${interval} 分钟` : '-'}</span>
          </div>
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">最近运行</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{lastRun ? lastRun.slice(0, 16).replace('T', ' ') : '未运行'}</span>
          </div>
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">调度任务</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{jobs} 个</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 知识库设置
// ---------------------------------------------------------------------------
function KnowledgeSettings() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<{ items?: number; concepts?: number; last_sync?: string } | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/health')
      .then(r => r.json())
      .then(d => setStats({
        items: d.total_items || 0,
        concepts: d.total_concepts || 0,
        last_sync: undefined,
      }))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>知识库状态</span>
            {stats && (
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {stats.items} 条目 · {stats.concepts} 概念
              </span>
            )}
          </div>
          {stats?.last_sync && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              最近同步: {stats.last_sync.slice(0, 16).replace('T', ' ')}
            </p>
          )}
          {!stats?.last_sync && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              知识库通过知识页面的同步功能更新
            </p>
          )}
          <button
            onClick={() => navigate('/knowledge')}
            className="btn-secondary btn-sm w-full text-center"
          >
            进入知识库
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 导出设置
// ---------------------------------------------------------------------------
function ExportSettings() {
  const navigate = useNavigate();

  return (
    <div className="space-y-2">
      <div className="card-compact">
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
              onClick={() => window.open('/api/export/download', '_blank')}
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

// ---------------------------------------------------------------------------
// 关于/系统信息
// ---------------------------------------------------------------------------
function AboutSettings() {
  const [health, setHealth] = useState<{
    version?: string;
    uptime_s?: number;
    status?: string;
    components?: { db?: any; scheduler?: any; collectors?: any; proxy?: any };
  } | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealth(d))
      .catch(() => {});
  }, []);

  const fmtUptime = (s?: number) => {
    if (!s) return '-';
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  const statusColor = (st?: string) => {
    switch (st) {
      case 'ok': return 'var(--color-success)';
      case 'degraded': return 'var(--color-warning)';
      default: return 'var(--color-error)';
    }
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>系统信息</span>
            {health?.status && (
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{
                backgroundColor: `color-mix(in srgb, ${statusColor(health.status)} 9%, transparent)`,
                color: statusColor(health.status),
              }}>
                {health.status === 'ok' ? '正常运行' : health.status === 'degraded' ? '部分降级' : '异常'}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-1 text-[9px]">
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">版本</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{health?.version || '-'}</span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">运行</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{fmtUptime(health?.uptime_s)}</span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">数据库</span>
              <span className="font-mono font-medium" style={{ color: health?.components?.db?.ok ? 'var(--color-success)' : 'var(--color-error)' }}>
                {health?.components?.db?.ok ? '正常' : '异常'}
                {health?.components?.db?.size_mb ? ` (${health.components.db.size_mb.toFixed(1)} MB)` : ''}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">调度器</span>
              <span className="font-mono font-medium" style={{ color: health?.components?.scheduler?.ok ? 'var(--color-general)' : 'var(--text-muted)' }}>
                {health?.components?.scheduler?.ok ? `${health.components.scheduler.details?.length || 0} 个任务` : '未启动'}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">采集器</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                {health?.components?.collectors?.last_run ? `最近 ${health.components.collectors.last_run.slice(0, 10)}` : '未运行'}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">代理</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                {health?.components?.proxy?.mode || '-'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 数据库维护
// ---------------------------------------------------------------------------
function DatabaseMaintenance() {
  const [dbHealth, setDbHealth] = useState<{ size_mb?: number; fragmentation_pct?: number; journal_mode?: string } | null>(null);
  const [tableStats, setTableStats] = useState<any[] | null>(null);
  const [dirtyReport, setDirtyReport] = useState<any | null>(null);
  const [duplicates, setDuplicates] = useState<{ hotspots?: any[]; knowledge_items?: any[] } | null>(null);

  // 操作状态
  const [vacuuming, setVacuuming] = useState(false);
  const [vacuumMsg, setVacuumMsg] = useState<string | null>(null);
  const [cleaningLogs, setCleaningLogs] = useState(false);
  const [cleanLogsMsg, setCleanLogsMsg] = useState<string | null>(null);
  const [deduping, setDeduping] = useState(false);
  const [dedupMsg, setDedupMsg] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanMsg, setCleanMsg] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState(90);
  const [qualityLogDays, setQualityLogDays] = useState(7);
  const [cacheClearing, setCacheClearing] = useState(false);
  const [cacheMsg, setCacheMsg] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [h, t, d, dup] = await Promise.all([
        fetch('/api/maintenance/health').then(r => r.json()),
        fetch('/api/maintenance/table-stats').then(r => r.json()),
        fetch('/api/maintenance/dirty-report').then(r => r.json()),
        fetch('/api/maintenance/duplicates').then(r => r.json()),
      ]);
      setDbHealth(h);
      setTableStats(t.tables || []);
      setDirtyReport(d);
      setDuplicates(dup);
    } catch {}
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleVacuum = async () => {
    setVacuuming(true);
    setVacuumMsg(null);
    try {
      const r = await fetch('/api/maintenance/vacuum', { method: 'POST' });
      const d = await r.json();
      setVacuumMsg(d.status === 'ok' ? `VACUUM 完成 (${d.total_seconds}s)` : 'VACUUM 失败');
      await loadData();
    } catch { setVacuumMsg('VACUUM 请求失败'); }
    finally { setVacuuming(false); }
  };

  const handleCleanupQualityLogs = async () => {
    setCleaningLogs(true);
    setCleanLogsMsg(null);
    try {
      const r = await fetch(`/api/maintenance/cleanup-quality-logs?days=${qualityLogDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
      setCleanLogsMsg(`已清理 ${d.rows_to_delete} 条 quality 日志，剩余 ${d.rows_remaining_after} 条`);
      await loadData();
    } catch { setCleanLogsMsg('清理请求失败'); }
    finally { setCleaningLogs(false); }
  };

  const handleDedup = async () => {
    setDeduping(true);
    setDedupMsg(null);
    try {
      const r = await fetch('/api/maintenance/cleanup-duplicates?dry_run=false', { method: 'POST' });
      const d = await r.json();
      setDedupMsg(`已删除 ${d.total_deleted} 条重复记录 (hotspots ${d.hotspots?.total_deleted || 0} + 知识库 ${d.knowledge_items?.total_deleted || 0})`);
      await loadData();
    } catch { setDedupMsg('去重请求失败'); }
    finally { setDeduping(false); }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanMsg(null);
    try {
      const r = await fetch(`/api/maintenance/cleanup?days=${retentionDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
      setCleanMsg(`历史清理完成: ${d.total_rows || 0} 条`);
      await loadData();
    } catch { setCleanMsg('清理请求失败'); }
    finally { setCleaning(false); }
  };

  const handleClearCache = async () => {
    setCacheClearing(true);
    setCacheMsg(null);
    try {
      const r = await fetch('/api/cache/clear', { method: 'POST' });
      const d = await r.json();
      setCacheMsg(d.status === 'ok' ? '缓存已清除' : '清除失败');
    } catch { setCacheMsg('清除请求失败'); }
    finally { setCacheClearing(false); }
  };

  const topTables = tableStats?.filter(t => t.rows > 0).sort((a, b) => b.rows - a.rows).slice(0, 10) || [];
  const dupCount = duplicates?.hotspots?.length ?? 0;
  const kiDupCount = duplicates?.knowledge_items?.length ?? 0;

  return (
    <div className="space-y-2">
      {/* DB 概览 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>数据库概览</span>
            {dbHealth && (
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {dbHealth.size_mb?.toFixed(1)} MB · 碎片 {dbHealth.fragmentation_pct?.toFixed(1)}%
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-1 text-[9px] font-mono mb-1.5">
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>总行数</span>
              <span style={{ color: 'var(--text-primary)' }}>{dirtyReport?.quality_check_logs?.total?.toLocaleString() || '-'}</span>
            </div>
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>质量日志</span>
              <span style={{ color: 'var(--color-warning)' }}>{dirtyReport?.quality_check_logs?.older_than_7_days?.toLocaleString() || '-'} 条可清理</span>
            </div>
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>脏数据</span>
              <span style={{ color: dupCount > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
                {dirtyReport?.duplicate_hotspots || 0} 重复URL · {dirtyReport?.duplicate_knowledge_items || 0} 重复标题
                {dirtyReport?.invalid_urls ? ` · ${dirtyReport.invalid_urls} 无效URL` : ''}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 大表 Top 10 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <span className="text-[11px] font-medium mb-1 block" style={{ color: 'var(--text-primary)' }}>大表 Top 10</span>
          <div className="space-y-0.5 text-[9px] font-mono">
            {topTables.map(t => (
              <div key={t.table} className="flex items-center justify-between px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <span className="truncate" style={{ color: 'var(--text-primary)' }}>{t.table}</span>
                <span style={{ color: 'var(--text-muted)' }}>{t.rows.toLocaleString()} 行</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 操作按钮组 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <span className="text-[11px] font-medium mb-1.5 block" style={{ color: 'var(--text-primary)' }}>维护操作</span>
          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
            <button onClick={handleVacuum} disabled={vacuuming} className="btn-secondary btn-sm">
              {vacuuming ? '压缩中...' : 'VACUUM 压缩'}
            </button>
            <button onClick={handleClearCache} disabled={cacheClearing} className="btn-secondary btn-sm">
              {cacheClearing ? '清除中...' : '清除缓存'}
            </button>
            <button onClick={handleDedup} disabled={deduping} className="btn-secondary btn-sm">
              {deduping ? '去重中...' : '重复数据去重'}
            </button>
            <button onClick={() => { handleCleanupQualityLogs(); }} disabled={cleaningLogs} className="btn-secondary btn-sm" style={{ color: 'var(--color-warning)' }}>
              {cleaningLogs ? '清理中...' : '清理质量日志'}
            </button>
          </div>
          {vacuumMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{vacuumMsg}</p>}
          {cacheMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{cacheMsg}</p>}
          {dedupMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{dedupMsg}</p>}
          {cleanLogsMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{cleanLogsMsg}</p>}
        </div>
      </div>

      {/* 质量日志保留期 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>质量日志保留期</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{qualityLogDays} 天</span>
          </div>
          <input
            type="range" min={1} max={90} step={1} value={qualityLogDays}
            onChange={e => setQualityLogDays(Number(e.target.value))}
            className="w-full h-1 accent-[var(--accent)] mb-1.5"
            style={{ accentColor: 'var(--accent)' }}
          />
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>1 天</span>
            <span className="flex-1 text-[9px] text-center" style={{ color: 'var(--text-muted)' }}>
              保留最近 {qualityLogDays} 天的质量日志
            </span>
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>90 天</span>
          </div>
          <button
            onClick={handleCleanupQualityLogs}
            disabled={cleaningLogs}
            className="btn-secondary btn-sm w-full mt-1.5"
          >
            {cleaningLogs ? '清理中...' : `立即清理质量日志 (保留 ${qualityLogDays} 天)`}
          </button>
        </div>
      </div>

      {/* 历史数据保留期 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>历史数据保留期</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{retentionDays} 天</span>
          </div>
          <input
            type="range" min={7} max={365} step={1} value={retentionDays}
            onChange={e => setRetentionDays(Number(e.target.value))}
            className="w-full h-1 accent-[var(--accent)] mb-1.5"
            style={{ accentColor: 'var(--accent)' }}
          />
          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className="btn-secondary btn-sm w-full mt-1.5"
          >
            {cleaning ? '清理中...' : `清理历史数据 (保留 ${retentionDays} 天)`}
          </button>
          {cleanMsg && <p className="text-[9px] mt-1" style={{ color: 'var(--color-general)' }}>{cleanMsg}</p>}
        </div>
      </div>

      {/* 重复数据详情 */}
      {(dupCount > 0 || kiDupCount > 0) && (
        <div className="card-compact">
          <div className="px-2.5 py-1.5">
            <span className="text-[11px] font-medium mb-1 block" style={{ color: 'var(--text-primary)' }}>重复数据详情</span>
            {duplicates?.hotspots && duplicates.hotspots.length > 0 && (
              <div className="mb-1">
                <span className="text-[9px] font-medium" style={{ color: 'var(--color-warning)' }}>Hotspots 重复 URL ({duplicates.hotspots.length} 组)</span>
                <div className="space-y-0.5 mt-0.5">
                  {duplicates.hotspots.slice(0, 5).map((d: any, i: number) => (
                    <div key={i} className="flex items-center gap-1 text-[9px] font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                      <span className="text-[8px] px-1 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>{d.count}×</span>
                      <span className="truncate flex-1" style={{ color: 'var(--text-muted)' }}>{d.url?.substring(0, 60)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {duplicates?.knowledge_items && duplicates.knowledge_items.length > 0 && (
              <div>
                <span className="text-[9px] font-medium" style={{ color: 'var(--color-warning)' }}>知识库重复标题 ({duplicates.knowledge_items.length} 组)</span>
                <div className="space-y-0.5 mt-0.5">
                  {duplicates.knowledge_items.slice(0, 5).map((d: any, i: number) => (
                    <div key={i} className="flex items-center gap-1 text-[9px] font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                      <span className="text-[8px] px-1 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>{d.count}×</span>
                      <span className="truncate flex-1" style={{ color: 'var(--text-muted)' }}>{d.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 设置页面主组件
// ---------------------------------------------------------------------------
export function SettingsPage() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState<SectionKey>('general');
  const [open] = useState(true);

  const { theme, toggleTheme } = (() => {
    try {
      const saved = localStorage.getItem('hotspot-theme');
      return {
        theme: (saved === 'dark' ? 'dark' : 'light') as 'dark' | 'light',
        toggleTheme: () => {
          const next = saved === 'dark' ? 'light' : 'dark';
          localStorage.setItem('hotspot-theme', next);
          document.documentElement.setAttribute('data-theme', next);
          window.dispatchEvent(new Event('theme-changed'));
        },
      };
    } catch {
      return { theme: 'light' as const, toggleTheme: () => {} };
    }
  })();

  const renderContent = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSettings onThemeToggle={toggleTheme} theme={theme} />;
      case 'collection':
        return (
          <div className="space-y-2">
            <CollectionScheduleInfo />
            <QualitySettings open={open} />
            <SourceSettings open={open} />
          </div>
        );
      case 'network':
        return <ProxySettings open={open} />;
      case 'sync':
        return <SyncSettings />;
      case 'integration':
        return <MCPSettingsCard open={open} />;
      case 'secrets':
        return <SecretsStatusCard />;
      case 'alerts':
        return <AlertSettings />;
      case 'knowledge':
        return <KnowledgeSettings />;
      case 'export':
        return <ExportSettings />;
      case 'maintenance':
        return <DatabaseMaintenance />;
      case 'about':
        return <AboutSettings />;
    }
  };

  return (
    <div className="w-full flex flex-col" style={{ minHeight: 'calc(100dvh - 1.5rem)' }}>
      {/* 页面标题 — 报纸报眉风格 */}
      <div className="shrink-0 flex items-center justify-between pb-2 mb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-serif mr-2">{'\u2699'}</span>
          设置
        </h1>
        <button
          onClick={() => navigate('/')}
          className="btn-ghost gap-1.5 px-2 py-1 text-[10px]"
          aria-label="返回首页"
        >
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回首页</span>
        </button>
      </div>

      {/* 主区域：sidebar + 可滚动内容 — 填满剩余高度 */}
      <div className="flex flex-1 gap-3 min-h-0">
        {/* 侧边导航 — 桌面 sticky 竖排, 移动端横向横滚 */}
        <nav
          className="shrink-0 flex flex-row sm:flex-col gap-px overflow-x-auto sm:overflow-y-auto pb-1 sm:pb-0 sm:sticky sm:top-0 sm:self-start sm:w-[78px] sm:max-h-full"
          style={{ scrollbarWidth: 'none' }}
          aria-label="设置分类"
        >
          {SECTIONS.map(s => {
            const active = activeSection === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setActiveSection(s.key)}
                className="settings-nav-btn"
                title={s.desc}
                style={{
                  backgroundColor: active ? 'var(--accent)' : 'transparent',
                  color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                  fontWeight: active ? 700 : 400,
                }}
                aria-current={active ? 'page' : undefined}
              >
                {s.icon}
                <span className="leading-tight">{s.label}</span>
              </button>
            );
          })}
        </nav>

        {/* 内容区 — 独立滚动 */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-0.5" style={{ scrollbarWidth: 'thin' }}>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;