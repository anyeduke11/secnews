import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { loadEnUSMessages, messages_zhCN } from '../lib/i18n';

/**
 * v0.7 Batch ⑧ D6 + Batch ⑨ B9-1: 轻量 i18n 框架 (zh-CN / en-US)
 *
 * Batch ⑨ B9-1: messages dict 扩到 120+ key, 覆盖:
 * - nav (4) — 顶部导航
 * - workspace (5) — 工作台首页
 * - observability (15) — 观测面板 (D6 起 + 本批补)
 * - settings (20) — 设置 4 卡 (Pipeline/Dsh/AgentRunner/Quality)
 * - pipeline (15) — 管线观测
 * - knowledge (15) — 知识库 (Wiki/Inbox)
 * - analyze (10) — 研判 / analyze
 * - analytics (10) — 分析页 (CVE 热力图 / ATT&CK / 合规)
 * - feed (10) — Feed 视图 + 简报 + 筛选
 * - common (15) — 通用按钮/状态
 *
 * 为什么不引 react-i18next: 当前无动态内容/Plural/Gender; dict 模板能 cover
 * 所有观测/告警/设置场景, 0 依赖; 真接 i18next 的迁移点在"接入 3rd-party
 * 翻译服务"时再评估.
 *
 * 设计:
 * - 1 Context (locale / setLocale / t / toggleLocale)
 * - 2 个 messages dict (zh-CN, en-US) — 120+ key
 * - t('key.path') 用点号 lookup, 缺失返 key 自身 + console.warn
 * - localStorage 持久化, 跨刷新保持
 * - <html lang> 同步
 */
export type Locale = 'zh-CN' | 'en-US';

const STORAGE_KEY = 'hotspot-locale';

type Messages = Record<string, string>;

// B5.5 (2026-11-18): 两份词条表已抽到 lib/i18n/ 并改为**按 locale 动态加载**。
// 动机 (实测归因, perf/chunk_attrib.mjs): 两表 gzip 合计 13,770 B, 占入口
// chunk (27,697 B) 的一半; en-US 单独 6,441 B, 而中文用户首屏不需要它。
//
// 加载策略:
// - zh-CN **静态常驻**: 默认语种 + 跨语种 fallback 源 (en-US 缺 key 时回退它),
//   必须随入口加载 → 首屏成本不变。
// - en-US **动态 import**: 独立 chunk, 仅 locale=en-US 时下载 → 省 6,441 B。
//
// t() 保持**同步** (既有契约): 词条未到达时回退 zh-CN 词条 (不是 key),
// 因为 zh-CN 始终在手 → en-US 加载期间的显示与"缺 key"语义保持一致。

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, paramsOrFallback?: Record<string, string | number> | string, fallback?: string) => string;
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
  try {
    if (typeof navigator !== 'undefined' && navigator.language?.startsWith('en')) {
      return 'en-US';
    }
  } catch {}
  return 'zh-CN';
}

/**
 * v0.7 Batch ⑨ B9-1: 支持 {n} / {name} 等占位符替换.
 * 用法: t('pipeline.bookmark_total', { n: 42 })
 */
function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    Object.prototype.hasOwnProperty.call(params, k) ? String(params[k]) : `{${k}}`,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);
  const [messages, setMessages] = useState<Messages>(messages_zhCN);

  // B5.5: en-US 词条按需动态加载 (独立 chunk)。locale=zh-CN 时不发起请求。
  // 加载期间 t() 回退 zh-CN 词条 (zh-CN 始终在手) → 与"缺 key"语义一致。
  useEffect(() => {
    if (locale === 'zh-CN') {
      setMessages(messages_zhCN);
      return;
    }
    let cancelled = false;
    void loadEnUSMessages().then((m) => {
      if (!cancelled) setMessages(m);
    });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  useEffect(() => {
    document.documentElement.setAttribute('lang', locale);
    try { localStorage.setItem(STORAGE_KEY, locale); } catch {}
  }, [locale]);

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);

  const toggleLocale = useCallback(() => {
    setLocaleState((cur) => (cur === 'zh-CN' ? 'en-US' : 'zh-CN'));
  }, []);

  const t = useCallback(
    (key: string, paramsOrFallback?: Record<string, string | number> | string, fallback?: string) => {
      // B9-1: 兼容 (key, fallback) 旧调用 (D6 测试) + (key, params) 新调用
      const params: Record<string, string | number> | undefined =
        typeof paramsOrFallback === 'object' && paramsOrFallback !== null
          ? paramsOrFallback
          : undefined;
      const fb: string | undefined =
        typeof paramsOrFallback === 'string' ? paramsOrFallback : fallback;

      const msg = messages[key];
      if (msg) return interpolate(msg, params);
      // B5.5: 当前语种缺 key → 回退 zh-CN (zh-CN 始终在手, 跨语种 fallback 不变)
      if (locale !== 'zh-CN' && messages_zhCN[key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in ${locale}, falling back to zh-CN`);
        return interpolate(messages_zhCN[key], params);
      }
      if (!messages_zhCN[key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in all locales`);
      }
      return fb ?? key;
    },
    [locale, messages],
  );

  return React.createElement(
    I18nContext.Provider,
    { value: { locale, setLocale, t, toggleLocale } },
    children,
  );
}
