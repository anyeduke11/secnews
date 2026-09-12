import { useState, useCallback } from 'react';
import { postJSON } from '../lib/api';
import { getHealth } from '../api/sources';

/**
 * 刷新间隔偏好 Hook — localStorage 持久化 + 后端采集频率同步。
 *
 * 端点为单一 hook 专用 → 常量化于此, 走 lib/api / api/sources 统一封装。
 */

export const REFRESH_INTERVAL_OPTIONS = [
  { value: 5, label: '5 分钟' },
  { value: 30, label: '30 分钟' },
  { value: 60, label: '60 分钟' },
  { value: 120, label: '2 小时' },
  { value: 720, label: '12 小时' },
  { value: 1480, label: '约 24 小时' },
];

const STORAGE_KEY = 'hotspot-refresh-interval';
const DEFAULT_MINUTES = 30;
const REFRESH_INTERVAL_SETTINGS_URL = '/api/settings/refresh-interval';

function getInitialMinutes(): number {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      const v = Number(parsed?.value);
      if (REFRESH_INTERVAL_OPTIONS.some(o => o.value === v)) return v;
    }
  } catch {}
  return DEFAULT_MINUTES;
}

export function useRefreshInterval() {
  const [interval, setIntervalState] = useState<number>(getInitialMinutes);

  const setInterval = useCallback(async (minutes: number) => {
    setIntervalState(minutes);
    const opt = REFRESH_INTERVAL_OPTIONS.find(o => o.value === minutes);
    if (opt) {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(opt)); } catch {}
    }
    // 同步后端采集频率
    try {
      await postJSON(REFRESH_INTERVAL_SETTINGS_URL, { minutes });
    } catch {
      // 静默失败 — 不影响本地设置
    }
  }, []);

  const refreshFromServer = useCallback(async (): Promise<number | null> => {
    // 用户偏好优先：localStorage 已有值就不覆盖
    try {
      if (localStorage.getItem(STORAGE_KEY)) return null;
    } catch {}
    try {
      const data = await getHealth();
      const seconds = data?.collect_interval_seconds;
      if (typeof seconds !== 'number' || seconds <= 0) return null;
      const minutes = Math.ceil(seconds / 60);
      setIntervalState(minutes);
      const opt = REFRESH_INTERVAL_OPTIONS.find(o => o.value === minutes);
      if (opt) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(opt)); } catch {}
      }
      return minutes;
    } catch {
      return null;
    }
  }, []);

  return { interval, setInterval, refreshFromServer, options: REFRESH_INTERVAL_OPTIONS };
}
