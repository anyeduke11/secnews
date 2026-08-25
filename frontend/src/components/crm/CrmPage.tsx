/**
 * CrmPage — CRM 业绩座舱页面容器 (v0.6 方案 C)
 *
 * 三个标签: 座舱复盘 / 客户 / 商机; 顶部可折叠「访问令牌」输入
 * (HOTSPOT_CRM_TOKEN 启用时必填, 本地模式留空即可)。
 */
import { useEffect, useState } from 'react';
import { CockpitDashboard } from './CockpitDashboard';
import { CustomerManager } from './CustomerManager';
import { OpportunityManager } from './OpportunityManager';
import { crmFetch, getCrmToken, setCrmToken } from '../../lib/crm';
import type { CrmMeta } from '../../types/crm';

type Tab = 'cockpit' | 'customers' | 'opportunities';

const TABS: { key: Tab; label: string }[] = [
  { key: 'cockpit', label: '座舱复盘' },
  { key: 'customers', label: '客户' },
  { key: 'opportunities', label: '商机' },
];

export function CrmPage({ onBack }: { onBack?: () => void }) {
  const [tab, setTab] = useState<Tab>('cockpit');
  const [meta, setMeta] = useState<CrmMeta | null>(null);
  const [token, setToken] = useState<string>(getCrmToken());
  const [tokenOpen, setTokenOpen] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  // 令牌保存后递增, 以 key 重挂载子面板触发重新拉取 (避免整页 reload)
  const [authVersion, setAuthVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    crmFetch<CrmMeta>('/api/crm/meta')
      .then(m => { if (!cancelled) setMeta(m); })
      .catch(e => { if (!cancelled) setMetaError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  const saveToken = () => {
    setCrmToken(token.trim());
    setTokenOpen(false);
    setAuthVersion(v => v + 1);
  };

  const borderStyle = { borderColor: 'var(--border-color)', color: 'var(--text-primary)' } as const;

  return (
    <div className="max-w-6xl mx-auto px-4 py-5" data-testid="crm-page">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
        <div className="flex items-center gap-3">
          {onBack && (
            <button onClick={onBack} className="nav-btn" aria-label="返回首页">←</button>
          )}
          <h1 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>CRM 业绩座舱</h1>
        </div>
        <button
          onClick={() => setTokenOpen(o => !o)}
          className="text-[11px] underline"
          style={{ color: 'var(--text-muted)' }}
          aria-expanded={tokenOpen}
        >
          访问令牌{token ? ' (已设置)' : ''}
        </button>
      </div>

      {tokenOpen && (
        <div className="flex items-center gap-2 mb-4 text-xs">
          <input
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="X-CRM-Token (服务端设置 HOTSPOT_CRM_TOKEN 时必填)"
            type="password"
            className="border rounded px-2 py-1 text-xs bg-transparent w-72"
            style={borderStyle}
            aria-label="CRM 访问令牌"
          />
          <button onClick={saveToken} className="px-2.5 py-1 rounded font-semibold" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
            保存
          </button>
        </div>
      )}

      <div className="flex gap-2 mb-4" role="tablist" aria-label="CRM 视图切换">
        {TABS.map(t => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className="ink-chip focus-ring transition-colors text-[11px]"
            style={{
              padding: '4px 10px',
              color: tab === t.key ? 'var(--text-on-light)' : 'var(--text-secondary)',
              backgroundColor: tab === t.key ? 'var(--accent)' : 'var(--bg-hover)',
              fontWeight: tab === t.key ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {metaError && (
        <p className="mb-3 text-xs" style={{ color: 'var(--color-error)' }}>
          枚举加载失败 (检查后端 crm 扩展是否开启): {metaError}
        </p>
      )}

      <div role="tabpanel">
        {tab === 'cockpit' && <CockpitDashboard key={authVersion} />}
        {tab === 'customers' && <CustomerManager key={authVersion} meta={meta} />}
        {tab === 'opportunities' && <OpportunityManager key={authVersion} meta={meta} />}
      </div>
    </div>
  );
}
