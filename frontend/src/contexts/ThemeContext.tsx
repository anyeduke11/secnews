import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

// Stage1 拆分: 主题状态从 App.tsx 抽出, App 回归 "组合 + 路由" 职责。
// 基线: light-first (v1.9 日报版), CSS 侧 :root 默认亮色 token, 与这里对齐消除首屏闪色。

export type ThemeMode = 'dark' | 'light';

interface ThemeContextValue {
  theme: ThemeMode;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  toggleTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

function getInitialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem('hotspot-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {}
  // v1.9 Editorial: 日报版 (light) 为新默认, 夜读版 (dark) 可切换
  return 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('hotspot-theme', theme); } catch {}
  }, [theme]);

  // P5-6: 监听 SettingsPage 的 theme-changed 事件 (此前双轨 — 设置页
  // 切主题后首页状态不一致, 刷新才一致)
  useEffect(() => {
    const onThemeChanged = () => {
      try {
        const saved = localStorage.getItem('hotspot-theme');
        if (saved === 'dark' || saved === 'light') setTheme(saved);
      } catch {}
    };
    window.addEventListener('theme-changed', onThemeChanged);
    return () => window.removeEventListener('theme-changed', onThemeChanged);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  return React.createElement(ThemeContext.Provider, { value: { theme, toggleTheme } }, children);
}
