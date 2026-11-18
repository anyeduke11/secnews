/**
 * CuboxImportCard — 数据源卡片: Cubox 同步 + 同步异常时的人工兜底 (B5 从 KnowledgeImport 原样抽出)
 *
 * 纯展示: 取数与 toast 编排留在容器 KnowledgeImport, 本组件只透传回调。
 */
import type { ChangeEvent, MutableRefObject } from 'react';
import { Icon } from '../../Icon';

export function CuboxImportCard({ syncing, cliBusy, dirBusy, dirPath, fileRef, onSync, onDirPathChange, onCliFileChange, onDirImport }: {
  syncing: boolean;
  cliBusy: boolean;
  dirBusy: boolean;
  dirPath: string;
  fileRef: MutableRefObject<HTMLInputElement | null>;
  onSync: () => void;
  onDirPathChange: (value: string) => void;
  onCliFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onDirImport: () => void;
}) {
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
            <path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
          </Icon>
        </span>
        <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
          Cubox 同步
        </h4>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          收藏夹全文 + 标注
        </span>
      </div>
      <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
        拉取 Cubox 中收藏的卡片正文与高亮，触发后台同步任务。
      </p>
      <button
        onClick={onSync}
        disabled={syncing}
        className="btn-ghost px-3 py-1.5 text-xs"
        style={{
          color: 'var(--area-accent)',
          opacity: syncing ? 0.6 : 1,
          cursor: syncing ? 'wait' : 'pointer',
        }}
      >
        {syncing ? (
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
            同步中…
          </span>
        ) : (
          '同步 Cubox'
        )}
      </button>

      {/* C2 (DEV-0195): 同步异常的人工兜底 — CLI 导出导入 + 本地目录导入 */}
      <div className="mt-3 pt-3 border-t" style={{ borderColor: 'var(--border-color)' }}>
        <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
          同步异常时的人工兜底：上传 cubox-cli 导出的 JSON，或导入本地 Cubox 知识库目录（.json / .md）。
        </p>
        <div className="flex flex-col gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            data-testid="cubox-cli-file"
            onChange={onCliFileChange}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={cliBusy}
            className="btn-ghost px-3 py-1.5 text-xs w-full"
            data-testid="cubox-cli-import"
          >
            {cliBusy ? '导入中…' : '导入 CLI 导出 JSON'}
          </button>
          <div className="flex gap-2">
            <input
              className="editorial-input flex-1 text-xs"
              style={{ minWidth: 0 }}
              placeholder="本地 Cubox 目录绝对路径 (支持 .json/.md), 如 /Users/me/Cubox"
              aria-label="cubox 导出目录路径"
              value={dirPath}
              onChange={e => onDirPathChange(e.target.value)}
            />
            <button
              onClick={onDirImport}
              disabled={dirBusy || !dirPath.trim()}
              className="btn-ghost px-3 py-1.5 text-xs whitespace-nowrap"
              data-testid="cubox-dir-import"
            >
              {dirBusy ? '导入中…' : '导入目录'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
