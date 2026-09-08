/**
 * V1SentinelShell — v1 四入口哨兵壳 (workbench / intel / cases / knowledge)
 *
 * v1.0.1 一致性重构: v1 入口接入 SentinelShell 同款顶栏 (品牌 + 三层导航 +
 * 主题切换 + 时钟), 但**移除**管道心跳条 + 右栏 rail-mod:
 *
 *   - 管道心跳条 (pipeline heartbeat) 归属 SentinelShell 专属, v1 数据采集
 *     不归此壳管 (/api/sources/health 走 secnews/* 路由常驻)
 *   - 右栏 rail-mod 复用 secnews 的 SentinelRail, v1 入口不需要
 *   - 保留: 品牌锚点 + 三层导航 active 态高亮 + 主题切换 + 时钟
 *
 * 子页通过 children 注入; SSE 订阅由各页自行管理.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import './sentinel.css';

export type V1SentinelLayer = 'workbench' | 'data' | 'judge' | 'action';

interface LayerDef {
  layer: V1SentinelLayer;
  label: string;
  sub: string;
  to: string;
  icon: JSX.Element;
}

const LAYER_DEFS: LayerDef[] = [
  {
    layer: 'data', label: '资料层', sub: '信息采集与组织', to: '/intel',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><rect x="1.5" y="7.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" /><rect x="7.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" /></svg>,
  },
  {
    layer: 'judge', label: '判断层', sub: '筛选、分析、关联', to: '/cases',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="5.5" cy="5.5" r="3.5" stroke="currentColor" strokeWidth="1.5" /><path d="M8.2 8.2L11 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  },
  {
    layer: 'action', label: '行动层', sub: '计划、学习、创作', to: '/knowledge',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 7l3 3L11 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M7.5 11h3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  },
];

function clockText(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function V1SentinelShell({ layer, children }: {
  layer: V1SentinelLayer;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [clock, setClock] = useState(() => clockText(new Date()));

  useEffect(() => {
    const t = setInterval(() => setClock(clockText(new Date())), 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="sentinel" data-mode="v1">
      {/* ===== 顶栏: 品牌 + 三层工作流导航 + 主题切换 + 时钟 ===== */}
      <header className="appbar">
        <a className="brand" href="/workbench" onClick={e => { e.preventDefault(); navigate('/workbench'); }}>
          <span className="brand-mark" aria-hidden="true">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6.5l2.5 2.5L10 3" stroke="var(--sn-mint)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </span>
          SecNews <small>SECURITY INTEL STATION</small>
        </a>

        <nav className="layers" aria-label="三层工作流导航">
          {LAYER_DEFS.map((def, i) => (
            <span key={def.layer} style={{ display: 'contents' }}>
              {i > 0 && (
                <span className="layer-flow" aria-hidden="true">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6h6M6 3.5L8.5 6 6 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </span>
              )}
              <a
                className={`layer-link${layer === def.layer ? ' active' : ''}`}
                href={def.to}
                aria-current={layer === def.layer ? 'page' : undefined}
                onClick={e => { e.preventDefault(); navigate(def.to); }}
              >
                <b>{def.icon}{def.label}</b>
                <span>{def.sub}</span>
              </a>
            </span>
          ))}
        </nav>

        <div className="appbar-right">
          <button type="button" className="iconbtn" onClick={toggleTheme} aria-label={theme === 'dark' ? '切换到晨间亮色' : '切换到夜航暗色'}>
            <svg className="tb-sun" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M9 1.2v2.1M9 14.7v2.1M1.2 9h2.1M14.7 9h2.1M3.7 3.7l1.5 1.5M12.8 12.8l1.5 1.5M14.3 3.7l-1.5 1.5M5.2 12.8l-1.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            <svg className="tb-moon" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><path d="M15.2 11.2A6.6 6.6 0 0 1 6.8 2.8a6.6 6.6 0 1 0 8.4 8.4Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
          </button>
          <span className="clock num">{clock}</span>
        </div>
      </header>

      {/* ===== 主内容区: 子页通过 children 注入 ===== */}
      <main className="sentinel-main">
        {children}
      </main>
    </div>
  );
}