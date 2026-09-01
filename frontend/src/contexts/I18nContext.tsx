import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

/**
 * v0.7 Batch ⑧ D6: 轻量 i18n 框架 (zh-CN / en-US)
 *
 * 为什么不引 react-i18next: 当前无动态内容/Plural/Gender, 仅 UI 字符串
 * 双语切换; dict 模板能 cover 所有观测/告警/设置场景, 0 依赖.
 * 真接 i18next 的迁移点在 "内容源 100+ 字符串 + 右侧 RTL" 时再评估.
 *
 * 设计:
 * - 1 Context (locale / setLocale / t)
 * - 2 个 messages dict (zh-CN, en-US)
 * - t('key.path') 用点号 lookup, 缺失返 key 自身 + console.warn
 * - localStorage 持久化, 跨刷新保持
 */
export type Locale = 'zh-CN' | 'en-US';

const STORAGE_KEY = 'hotspot-locale';

type Messages = Record<string, string>;

const messages_zhCN: Messages = {
  // nav
  'nav.home': '首页',
  'nav.workspace': '工作台',
  'nav.observability': '观测',
  'nav.settings': '设置',
  // observability
  'observability.title': '观测面板 — 实时 API 健康度',
  'observability.last_1h': '最近 1 小时',
  'observability.total': '总请求',
  'observability.errors_5xx': '5xx 错误',
  'observability.error_rate': '错误率',
  'observability.p50': 'p50 延迟',
  'observability.p95': 'p95 延迟',
  'observability.top_slow_paths': 'Top 5 慢路径 (按 p95)',
  'observability.recent_events': '最近告警事件',
  'observability.loading': '正在加载观测数据…',
  'observability.error': '观测数据获取失败',
  // common
  'common.refresh': '刷新',
  'common.cancel': '取消',
  'common.save': '保存',
  'common.delete': '删除',
  'common.confirm': '确认',
  'common.disabled': '已禁用',
  'common.enabled': '已启用',
};

const messages_enUS: Messages = {
  // nav
  'nav.home': 'Home',
  'nav.workspace': 'Workspace',
  'nav.observability': 'Observability',
  'nav.settings': 'Settings',
  // observability
  'observability.title': 'Observability — Real-time API Health',
  'observability.last_1h': 'Last 1 hour',
  'observability.total': 'Total requests',
  'observability.errors_5xx': '5xx errors',
  'observability.error_rate': 'Error rate',
  'observability.p50': 'p50 latency',
  'observability.p95': 'p95 latency',
  'observability.top_slow_paths': 'Top 5 slow paths (by p95)',
  'observability.recent_events': 'Recent alert events',
  'observability.loading': 'Loading observability data…',
  'observability.error': 'Failed to load observability data',
  // common
  'common.refresh': 'Refresh',
  'common.cancel': 'Cancel',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.confirm': 'Confirm',
  'common.disabled': 'Disabled',
  'common.enabled': 'Enabled',
};

const MESSAGES: Record<Locale, Messages> = {
  'zh-CN': messages_zhCN,
  'en-US': messages_enUS,
};

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, fallback?: string) => string;
  toggleLocale: () => void;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'zh-CN',
  setLocale: () => {},
  t: (k) => k,
  toggleLocale: () => {},
});

export function useI18n() {
  return useContext(I18nContext);
}

function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh-CN' || saved === 'en-US') return saved;
  } catch {}
  // 默认 zh-CN (产品主语言); 浏览器语言命中 en-US 时自动切
  try {
    if (typeof navigator !== 'undefined' && navigator.language?.startsWith('en')) {
      return 'en-US';
    }
  } catch {}
  return 'zh-CN';
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  useEffect(() => {
    document.documentElement.setAttribute('lang', locale);
    try { localStorage.setItem(STORAGE_KEY, locale); } catch {}
  }, [locale]);

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);

  const toggleLocale = useCallback(() => {
    setLocaleState((cur) => (cur === 'zh-CN' ? 'en-US' : 'zh-CN'));
  }, []);

  const t = useCallback(
    (key: string, fallback?: string) => {
      const msg = MESSAGES[locale][key];
      if (msg) return msg;
      // 兜底: zh-CN 词典本身缺 key 时再 warn, 避免 zh→en→zh 双 warn
      if (locale !== 'zh-CN' && MESSAGES['zh-CN'][key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in ${locale}, falling back to zh-CN`);
        return MESSAGES['zh-CN'][key];
      }
      if (!MESSAGES['zh-CN'][key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in all locales`);
      }
      return fallback ?? key;
    },
    [locale],
  );

  return React.createElement(
    I18nContext.Provider,
    { value: { locale, setLocale, t, toggleLocale } },
    children,
  );
}
