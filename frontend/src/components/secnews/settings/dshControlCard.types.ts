/** TFn — 本目录 i18n 翻译函数签名 (与 I18nContext 的 t 一致) */
export type TFn = (
  key: string,
  paramsOrFallback?: Record<string, string | number> | string,
  fallback?: string,
) => string;