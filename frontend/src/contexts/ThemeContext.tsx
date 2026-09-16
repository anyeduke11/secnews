import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

// Stage1 拆分: 主题状态从 App.tsx 抽出, App 回归 "组合 + 路由" 职责。
// 基线: light-first (v1.9 日报版), CSS 侧 :root 默认亮色 token, 与这里对齐消除首屏闪色。
// P2 (2026-09-13): ThemeMode 扩展第 3 值 'paper' — 暖米黄纸底 + 深褐墨 + 衬线字体,
//   仅覆写 bg/ink/font 6 个核心 token, 其它链 token (mint/amber/red/分类色) 沿用亮色值;
//   接入详见 frontend/src/index.css `:root[data-theme="paper"]` 块.

export type ThemeMode = 'dark' | 'light' | 'paper';

const THEME_CYCLE: ThemeMode[] = ['light', 'dark', 'paper'];

interface ThemeContextValue {
  theme: ThemeMode;
  /** 三态轮换: light → dark → paper → light */
  cycleTheme: () => void;
  /** 直接切到指定主题 (设置页快捷按钮用) */
  setTheme: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  cycleTheme: () => {},
  setTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

function getInitialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem('hotspot-theme');
    if (saved === 'light' || saved === 'dark' || saved === 'paper') return saved;
  } catch {}
  // v1.9 Editorial: 日报版 (light) 为新默认, 夜读版 (dark) 可切换; 纸面版 (paper) 须用户主动启用
  return 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('hotspot-theme', theme); } catch {}
  }, [theme]);

  // P5-6: 监听 SettingsPage 的 theme-changed 事件 (此前双轨 — 设置页
  // 切主题后首页状态不一致, 刷新才一致)
  useEffect(() => {
    const onThemeChanged = (e: Event) => {
      const next = (e as CustomEvent<{ theme?: ThemeMode }>).detail?.theme;
      if (next === 'dark' || next === 'light' || next === 'paper') setThemeState(next);
      // 老路径兼容: 直接读 storage
      try {
        const saved = localStorage.getItem('hotspot-theme');
        if (saved === 'dark' || saved === 'light' || saved === 'paper') setThemeState(saved);
      } catch {}
    };
    window.addEventListener('theme-changed', onThemeChanged as EventListener);
    return () => window.removeEventListener('theme-changed', onThemeChanged as EventListener);
  }, []);

  const cycleTheme = useCallback(() => {
    setThemeState(t => {
      const idx = THEME_CYCLE.indexOf(t);
      const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
      return next ?? 'light';
    });
  }, []);

  const setTheme = useCallback((mode: ThemeMode) => setThemeState(mode), []);

  return React.createElement(
    ThemeContext.Provider,
    { value: { theme, cycleTheme, setTheme } },
    children
  );
}