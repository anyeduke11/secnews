/**
 * SourceCards — 数据源 action cards 中的书签 / Obsidian / 冲突快照三块 + 冲突列表展开,
 * B5 从 KnowledgeImport 原样抽出, DOM、class 与 data-testid 未改。
 */
import { Icon } from '../../../primitives/Icon';
import { BookmarkImport } from '../../BookmarkImport';
import type { ConflictFile } from './importModel';

/** 书签导入 */
export function BookmarkImportCard() {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
            color: 'var(--area-accent)',
          }}
        >
          <Icon size={12}>
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
          </Icon>
        </span>
        <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
          浏览器书签
        </h4>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          Chrome JSON / HTML
        </span>
      </div>
      <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
        上传 Chrome / Edge 导出的书签文件，自动去重，可选验证 URL 可达性。
      </p>
      <BookmarkImport />
    </div>
  );
}

/** Obsidian 入口 */
export function ObsidianCard({ onOpen }: { onOpen: () => void }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
            color: 'var(--area-accent)',
          }}
        >
          <Icon size={12}>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v10M7 12h10" />
          </Icon>
        </span>
        <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
          Obsidian vault
        </h4>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          本地 vault 协议
        </span>
      </div>
      <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
        通过 <code style={{ color: 'var(--area-accent)' }}>obsidian://</code> 协议唤起本地 Obsidian。
      </p>
      <button
        onClick={onOpen}
        className="btn-ghost px-3 py-1.5 text-xs"
        style={{ color: 'var(--area-accent)' }}
      >
        打开 Obsidian
      </button>
    </div>
  );
}

/** 冲突快照入口卡片 */
export function ConflictCard({ revealed, onToggle }: { revealed: boolean; onToggle: () => void }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
            color: 'var(--area-accent)',
          }}
        >
          <Icon size={12}>
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </Icon>
        </span>
        <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
          冲突快照
        </h4>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          watchdog 记录
        </span>
      </div>
      <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
        查看文件监视器记录的同步冲突（外部修改 vs 内部写入）。
      </p>
      <button
        onClick={onToggle}
        className="btn-ghost px-3 py-1.5 text-xs"
        style={{ color: revealed ? 'var(--color-error)' : 'var(--area-accent)' }}
      >
        {revealed ? '隐藏冲突' : '查看冲突'}
      </button>
    </div>
  );
}

/** 冲突列表展开 */
export function ConflictSection({ conflicts }: { conflicts: ConflictFile[] }) {
  return (
    <section
      className="rounded-[var(--radius-md)] p-2.5 text-xs"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
      }}
    >
      <div className="font-semibold mb-1.5" style={{ color: 'var(--text-primary)' }}>
        冲突快照 ({conflicts.length})
      </div>
      {conflicts.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>无冲突记录</p>
      ) : (
        <ul className="space-y-1">
          {conflicts.map(c => (
            <li key={c.filename} className="flex items-center gap-2">
              <span style={{ color: 'var(--color-error)' }}>⚠</span>
              <span className="flex-1 truncate" title={c.filename} style={{ color: 'var(--text-primary)' }}>
                {c.filename}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{(c.size / 1024).toFixed(1)} KB</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
