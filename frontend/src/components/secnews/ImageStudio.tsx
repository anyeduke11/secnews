/**
 * ImageStudio — DEPRECATED (v0.7.x SettingsHub 落地后)
 *
 * 早期版本 (v0.7.4-image, S9) 含文生图 (sensenova-u1.5-lite) + 图理解两块功能。
 * 用户裁决 (2026-09-02): "只保留模型配置信息, 与 /settings 绑定即可, 不需要独立功能"。
 * 用户进一步裁决 (2026-09-02): "整个进 settings, 不应该有多个孤页管理设置入口"。
 *
 * 此文件保留不删 (引用了 ScenarioModelsPanel 的紧凑版),
 * 路由 /secnews/image 已在 index.tsx 永久 redirect 到 /settings?cat=image_models,
 * lazy-imports.ts 不再 export, 路由层不可达。
 * 真正的入口见 /settings?cat=image_models。
 *
 * 图理解原本面向"辅助爬虫/解析资讯识别"场景, 后端 /api/image/* 端点保留,
 * 未来真正要做"图辅助资讯识别"时再接入 parsers/crawlers, 不在本页。
 */
import { ScenarioModelsPanel } from '../settings/ScenarioModelsPanel';

/** @deprecated 路由层已不可达, 真正的入口见 /settings?cat=image_models */
export function ImageStudio() {
  return (
    <div className="p-4 max-w-3xl mx-auto space-y-4">
      <p className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
        ⚠️ DEPRECATED: 此页已并入 <a href="/settings?cat=image_models" style={{ color: 'var(--accent)' }}>设置 → 图片模型</a>。
        本路由将在 v0.8 移除 (lazy-imports 已 unexport)。
      </p>
      <ScenarioModelsPanel scope="image-studio" compact />
    </div>
  );
}

export default ImageStudio;