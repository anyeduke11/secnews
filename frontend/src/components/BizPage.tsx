/**
 * NAV4 P3 (2026-09-13, DEV-0178): 业务座舱 /biz
 *
 * 三列卡 (业绩/客户/机会) + mock 兜底.
 * 背景: CRM 域已随 migration 116 整体删除 (/crm + /api/crm 不存在),
 * 本页作为"行动菜单扩展域"占位, 等真实业务系统接入再替换数据源.
 *
 * 设计契约:
 * - 纯前端 mock, 与后端 0 依赖
 * - 顶部 chip 标注「演示数据」 (i18n: biz.demoNote)
 * - 风格与 nav4 资讯页一致: PageLayout 内层渲染
 */

import { useMemo } from 'react';
import { useI18n } from '../contexts/I18nContext';

interface BizMock {
  performance: {
    alerts: number;
    handled: number;
    mttd: string;
  };
  customers: { name: string; activity: number; tag: string }[];
  opportunities: { title: string; priority: 'high' | 'mid' | 'low'; owner: string }[];
}

const BIZ_MOCK: BizMock = {
  performance: { alerts: 234, handled: 0.87, mttd: '4.2h' },
  customers: [
    { name: '某股份制银行', activity: 0.92, tag: '战略' },
    { name: '某城商行', activity: 0.78, tag: '重点' },
    { name: '某支付机构', activity: 0.65, tag: '重点' },
  ],
  opportunities: [
    { title: 'CVE-2026-31337 PoC 跟进', priority: 'high', owner: '本人' },
    { title: '金融行业钓鱼专题', priority: 'mid', owner: '协作' },
    { title: 'ATT&CK T1059 季度复盘', priority: 'low', owner: '本人' },
  ],
};

const PRIORITY_COLOR: Record<string, string> = {
  high: 'var(--color-error)',
  mid: 'var(--color-warning)',
  low: 'var(--text-muted)',
};

export function BizPage() {
  const { t } = useI18n();
  const data = useMemo(() => BIZ_MOCK, []);

  return (
    <div className="px-6 py-8 max-w-7xl mx-auto">
      {/* 顶部演示 chip + 标题 */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <span
            data-testid="biz-demo-chip"
            className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono"
            style={{
              background: 'var(--bg-warning)',
              color: 'var(--text-on-warning)',
              border: '1px solid var(--border-color)',
            }}
          >
            {t('biz.demoNote')}
          </span>
        </div>
        <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--ink)' }}>
          {t('biz.title')}
        </h1>
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          {t('biz.subtitle')}
        </p>
      </header>

      {/* 三列卡 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 业绩 */}
        <section
          data-testid="biz-card-performance"
          className="rounded-lg p-5"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
          }}
        >
          <h2 className="text-sm font-mono mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('biz.performance.title')}
          </h2>
          <dl className="space-y-4">
            <div>
              <dt className="text-xs mb-1" style={{ color: 'var(--ink-3)' }}>
                {t('biz.performance.alerts')}
              </dt>
              <dd className="text-3xl font-semibold font-mono" style={{ color: 'var(--ink)' }}>
                {data.performance.alerts}
              </dd>
            </div>
            <div>
              <dt className="text-xs mb-1" style={{ color: 'var(--ink-3)' }}>
                {t('biz.performance.handled')}
              </dt>
              <dd className="text-xl font-mono" style={{ color: 'var(--mint)' }}>
                {(data.performance.handled * 100).toFixed(0)}%
              </dd>
            </div>
            <div>
              <dt className="text-xs mb-1" style={{ color: 'var(--ink-3)' }}>
                {t('biz.performance.mttd')}
              </dt>
              <dd className="text-xl font-mono" style={{ color: 'var(--ink)' }}>
                {data.performance.mttd}
              </dd>
            </div>
          </dl>
        </section>

        {/* 客户 */}
        <section
          data-testid="biz-card-customers"
          className="rounded-lg p-5"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
          }}
        >
          <h2 className="text-sm font-mono mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('biz.customers.title')}
          </h2>
          <ul className="space-y-3">
            {data.customers.map((c, i) => (
              <li key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm" style={{ color: 'var(--ink)' }}>
                    {c.name}
                  </span>
                  <span
                    className="text-xs px-1.5 py-0.5 rounded font-mono"
                    style={{
                      background: 'var(--bg-elevated)',
                      color: 'var(--ink-2)',
                    }}
                  >
                    {c.tag}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="w-16 h-1.5 rounded"
                    style={{ background: 'var(--bg-elevated)' }}
                  >
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${c.activity * 100}%`,
                        background: 'var(--mint)',
                      }}
                    />
                  </div>
                  <span className="text-xs font-mono w-8 text-right" style={{ color: 'var(--ink-3)' }}>
                    {(c.activity * 100).toFixed(0)}%
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* 机会 */}
        <section
          data-testid="biz-card-opportunities"
          className="rounded-lg p-5"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
          }}
        >
          <h2 className="text-sm font-mono mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('biz.opportunities.title')}
          </h2>
          <ul className="space-y-3">
            {data.opportunities.map((o, i) => (
              <li
                key={i}
                className="flex items-start gap-3 py-2"
                style={{ borderBottom: '1px solid var(--border-color)' }}
              >
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full mt-2 shrink-0"
                  style={{ background: PRIORITY_COLOR[o.priority] }}
                  aria-label={o.priority}
                />
                <div className="flex-1">
                  <div className="text-sm" style={{ color: 'var(--ink)' }}>
                    {o.title}
                  </div>
                  <div className="text-xs font-mono mt-0.5" style={{ color: 'var(--ink-3)' }}>
                    {o.owner} · {t(`biz.opportunities.priority.${o.priority}`)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}