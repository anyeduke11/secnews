/**
 * ImportHero — 信息导入区域介绍 hero (B5 从 KnowledgeImport 原样抽出)
 */
import { Icon } from '../../../primitives/Icon';

export function ImportHero() {
  return (
    <section
      className="rounded-[var(--radius-md)] p-3.5"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: '3px solid var(--area-accent)',
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
            color: 'var(--area-accent)',
          }}
        >
          <Icon size={18}>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </Icon>
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className="text-sm font-bold mb-0.5"
            style={{ color: 'var(--text-primary)' }}
          >
            信息导入 · 多源采集入口
          </h3>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            从 Cubox 收藏夹、浏览器书签、外部 URL 等多源采集原始素材，
            经 <span style={{ color: 'var(--area-accent)' }}>去重 + 验证</span> 后写入知识条目池。
          </p>
        </div>
      </div>
    </section>
  );
}
