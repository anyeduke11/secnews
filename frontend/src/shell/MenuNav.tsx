/**
 * shell/MenuNav — 报头 masthead + 版面条 bandnav
 *
 * 2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx, DOM/类名/aria-label 逐字搬出:
 *  - masthead 报头: 衬线品牌字 + 四菜单排版式导航 (active = accent 下划线) + 主题切换/时钟
 *  - bandnav 版面条: 当前菜单的二级域 chip (sticky), 工具页经 menuOf 自动归属; gate 关闭不渲染; A7 支持收起
 */
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';
import { CommandBar } from '../components/sentinel/CommandBar';
import { chipIsCurrent, LAYER_DEFS } from './menuOf';
import type { BandItem, SentinelLayer } from './types';

function clockText(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function MenuNav({ activeLayer, bandItems, collapsed, onToggleBandnav }: {
  /** 当前菜单归属 (null = 工具页且未命中 menuOf) */
  activeLayer: SentinelLayer | null;
  /** 版面条 chip (已按 gate 过滤) */
  bandItems: BandItem[];
  /** 版面条收起态 */
  collapsed: boolean;
  /** 收起/展开翻转 (持久化由壳负责) */
  onToggleBandnav: (next: boolean) => void;
}) {
  const navigate = useNavigate();
  const { theme, cycleTheme } = useTheme();
  const { pathname } = useLocation();
  const [clock, setClock] = useState(() => clockText(new Date()));

  useEffect(() => {
    const t = setInterval(() => setClock(clockText(new Date())), 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <>
      {/* ===== 报头 masthead: 品牌 (左) + 四菜单 (中) + 控制 (右) ===== */}
      <header className="masthead">
        <a className="mh-brand" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>
          <span className="mh-title">SecNews</span>
          <span className="mh-sub">SECURITY INTEL STATION</span>
        </a>

        <nav className="mh-nav" aria-label="四菜单导航">
          {LAYER_DEFS.map(def => (
            <a
              key={def.layer}
              className={`nv${activeLayer === def.layer ? ' active' : ''}`}
              href={def.to}
              aria-current={activeLayer === def.layer ? 'page' : undefined}
              onClick={e => { e.preventDefault(); navigate(def.to); }}
            >
              <span className="nv-main">{def.label}</span>
              <span className="nv-sub">{def.sub}</span>
            </a>
          ))}
        </nav>

        {/* v0.8.6 P1-4 / M4: 命令栏常驻 masthead (PRD 用例 B; 零新路由) */}
        <CommandBar />

        <div className="mh-meta">
          <button type="button" className="iconbtn" onClick={cycleTheme} aria-label={theme === 'dark' ? '切换到晨间亮色' : theme === 'paper' ? '切换到夜航暗色' : '切换到纸面版'}>
            <svg className="tb-sun" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M9 1.2v2.1M9 14.7v2.1M1.2 9h2.1M14.7 9h2.1M3.7 3.7l1.5 1.5M12.8 12.8l1.5 1.5M14.3 3.7l-1.5 1.5M5.2 12.8l-1.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            <svg className="tb-moon" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><path d="M15.2 11.2A6.6 6.6 0 0 1 6.8 2.8a6.6 6.6 0 1 0 8.4 8.4Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
            <svg className="tb-paper" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><rect x="3.5" y="2.5" width="11" height="13" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 5.5h7M5.5 8.5h7M5.5 11.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" /></svg>
          </button>
          <span className="clock num">{clock}</span>
        </div>
      </header>

      {/* ===== 版面条 bandnav: 当前菜单二级域 chip (工具页经 menuOf 自动归属); A7 支持收起 ===== */}
      {bandItems.length > 0 && (
        <nav className={`bandnav${collapsed ? ' collapsed' : ''}`} aria-label="版面条">
          {collapsed ? (
            <button
              type="button"
              className="bn-expand"
              aria-expanded={false}
              aria-label="展开版面条"
              title="展开二级导航"
              onClick={() => onToggleBandnav(false)}
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><path d="M2 6.5 5 3.5 8 6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              版面条
            </button>
          ) : (
            <>
              {bandItems.map(it => (
                <a
                  key={it.to}
                  className={`bn-chip${chipIsCurrent(pathname, it.to) ? ' current' : ''}`}
                  href={it.to}
                  aria-current={chipIsCurrent(pathname, it.to) ? 'true' : undefined}
                  onClick={e => { e.preventDefault(); navigate(it.to); }}
                >
                  {it.label}
                </a>
              ))}
              <button
                type="button"
                className="bn-collapse"
                aria-expanded={true}
                aria-label="收起版面条"
                title="收起二级导航"
                onClick={() => onToggleBandnav(true)}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </>
          )}
        </nav>
      )}
    </>
  );
}