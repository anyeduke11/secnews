/**
 * ImageStudio — v0.7.4-image 工具页 (重构)
 *
 * 早期版本 (S9 落地) 含文生图 (sensenova-u1.5-lite) + 图理解两块功能。
 * 用户裁决 (2026-09-02): "只保留模型配置信息, 与 /settings 绑定即可, 不需要独立功能"。
 * 图理解原本面向"辅助爬虫/解析资讯识别"场景, 后端 /api/image/* 端点保留,
 * 未来真正要做"图辅助资讯识别"时再接入 parsers/crawlers, 不在本页。
 *
 * 现行为: 三场景模型配置面板 — 复用 ScenarioModelsPanel,
 *   与 /secnews/settings 中的三场景折叠面板同源 (同一份逻辑/状态/数据契约)。
 * 渲染差别: 本页默认展开 (不折叠), 顶部说明文案简洁化。
 */
import { ScenarioModelsPanel } from '../settings/ScenarioModelsPanel';

export function ImageStudio() {
  return (
    <div className="p-4 max-w-3xl mx-auto space-y-4">
      {/* 页面标题 + 说明 */}
      <header className="space-y-1">
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          🖼️ 图片工具 · 模型配置
        </h2>
        <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>
          深度 / 轻度 / 图片 三场景的模型选择在这里配置。改动立即写入 settings.kv,
          并与 <code>/secnews/settings</code> 中的折叠面板保持一致 (同一份状态)。
        </p>
        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          文生图与图理解功能已下线 (用户裁决 2026-09-02)。
          后续如需图片辅助资讯识别, 走 parsers/crawlers, 后端 <code>/api/image/*</code> 端点保留可用。
        </p>
      </header>

      {/* 三场景模型配置 (与 /settings 同源) */}
      <section
        className="rounded-[var(--radius-sm)]"
        style={{ border: '1px solid var(--border-color)' }}
      >
        <ScenarioModelsPanel scope="image-studio" compact />
      </section>
    </div>
  );
}

export default ImageStudio;