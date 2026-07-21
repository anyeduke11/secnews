/**
 * useThemeColors — 读取当前主题的 CSS 变量解析值。
 *
 * Phase 2: 用于 Recharts/ECharts 等 SVG 绘图库, 它们需要字面颜色
 *          (不能直接用 var(--color-*))。本 hook 在挂载时 + 主题切换时
 *          通过 getComputedStyle 读取最新值。
 *
 * 限制: 只读取指定 token 列表, 不读所有 CSS 变量（性能 + 精确性）。
 */
import { useEffect, useState } from 'react';

export type ThemeColorKey =
  | 'color-ai'
  | 'color-security'
  | 'color-finance'
  | 'color-startup'
  | 'color-bid'
  | 'color-general'
  | 'color-success'
  | 'color-warning'
  | 'color-error'
  | 'color-info'
  | 'bg-primary'
  | 'bg-card'
  | 'bg-elevated'
  | 'bg-hover'
  | 'border-color'
  | 'text-primary'
  | 'text-secondary'
  | 'text-muted';

export type ThemeColors = Partial<Record<ThemeColorKey, string>>;

function readVars(keys: ThemeColorKey[]): ThemeColors {
  const cs = getComputedStyle(document.documentElement);
  const out: ThemeColors = {};
  for (const k of keys) {
    out[k] = cs.getPropertyValue(`--${k}`).trim();
  }
  return out;
}

export function useThemeColors(keys: ThemeColorKey[]): ThemeColors {
  const [colors, setColors] = useState<ThemeColors>(() => readVars(keys));

  useEffect(() => {
    setColors(readVars(keys));
    const obs = new MutationObserver(() => setColors(readVars(keys)));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => obs.disconnect();
    // keys 引用稳定即可
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys.join(',')]);

  return colors;
}
