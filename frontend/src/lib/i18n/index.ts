/**
 * i18n 词条表入口 (B5.5, 2026-11-18)
 *
 * 拆分动机 (实测归因, perf/chunk_attrib.mjs):
 *   两份词条表 (zh-CN + en-US 各 390 keys) gzip 合计 **13,770 B**,
 *   而入口 chunk 只有 27,697 B —— 词条表占了入口 chunk 的**一半**。
 *   其中 en-US 单独占 6,441 B, 而中文用户首屏根本不需要它。
 *
 * 策略:
 *   - zh-CN **静态导出**: 它既是默认语种, 也是跨语种 fallback 的来源
 *     (en-US 缺 key 时回退 zh-CN), 必须常驻 → 无首屏成本。
 *   - en-US **动态 import**: 独立 chunk, 仅 locale=en-US 时按需下载。
 *
 * ⚠️ 词条表由 scripts/split_i18n.mjs 一次性抽取生成, key 集合已逐条校验
 *    (390 = 390, 双向无缺)。后续增删词条请**同步改两个文件**
 *    (key 必须成对, 否则切换语言会缺词)。
 */
export type Messages = Record<string, string>;

export { messages_zhCN } from './messages.zh-CN';

/** 动态加载 en-US 词条表 (→ 独立 chunk)。 */
export async function loadEnUSMessages(): Promise<Messages> {
  const mod = await import('./messages.en-US');
  return mod.messages_enUS;
}
