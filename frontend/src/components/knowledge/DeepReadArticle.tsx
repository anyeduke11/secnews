/**
 * DeepReadArticle — 深度阅读 左栏文章全文区块 (B5 续拆自 DeepReadMode)
 *
 * 纯展示: JSX 逐字搬运 (标题 / 元数据 / 标签 / chunk 分段正文渲染路径不变)。
 */
import React from 'react';
import { Icon } from '../../primitives/Icon';
import type { ChunkInfo, DeepReadItem } from './deepReadModeModel';

export function DeepReadArticle({
  item,
  content,
  chunks,
  chunksLoading,
}: {
  item: DeepReadItem;
  content: string;
  chunks: ChunkInfo[];
  chunksLoading: boolean;
}) {
  return (
    <div className="flex-1 min-w-0 space-y-3">
      <section
        className="rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        {/* 标题 */}
        <h2
          className="text-lg font-bold mb-3 leading-relaxed"
          style={{ color: 'var(--text-primary)' }}
        >
          {item.title || '(无标题)'}
        </h2>

        {/* 元数据行 */}
        <div
          className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] pb-3 mb-3"
          style={{
            color: 'var(--text-muted)',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          {item.source && (
            <span className="flex items-center gap-1">
              <Icon size={11}>
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v10M7 12h10" />
              </Icon>
              {item.source}
            </span>
          )}
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--color-ai)' }}
              className="hover:underline"
            >
              原文链接 ↗
            </a>
          )}
          {item.ingested_at && (
            <span>
              录入: {new Date(item.ingested_at).toLocaleString('zh-CN')}
            </span>
          )}
          {item.type && <span>类型: {item.type}</span>}
          {item.difficulty && <span>难度: {item.difficulty}</span>}
          {item.mastery !== undefined && (
            <span>掌握度: {item.mastery}%</span>
          )}
        </div>

        {/* 标签 */}
        {item.tags && item.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {item.tags.map(tag => (
              <span
                key={tag}
                className="px-2 py-0.5 rounded text-[10px]"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-ai) 10%, transparent)',
                  color: 'var(--color-ai)',
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* 正文 (Markdown, 只读) — 按 chunk 分段显示 */}
        <div
          className="text-sm leading-relaxed"
          style={{
            color: 'var(--text-primary)',
            lineHeight: 1.8,
          }}
        >
          {!content ? (
            <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
              无正文内容
            </span>
          ) : chunks.length > 0 ? (
            <div>
              {chunks.map((chunk, i) => {
                const chunkText = content.slice(chunk.char_start, chunk.char_end) || chunk.content;
                if (!chunkText) return null;
                return (
                  <React.Fragment key={chunk.chunk_index}>
                    {i > 0 && (
                      <div
                        style={{
                          borderBottom: '1px solid color-mix(in srgb, var(--border-color) 60%, transparent)',
                          margin: 'var(--space-2, 8px) 0',
                        }}
                      />
                    )}
                    <div
                      id={`chunk-${chunk.chunk_index}`}
                      className="group relative"
                      style={{
                        borderLeft: '2px solid color-mix(in srgb, var(--color-info) 15%, transparent)',
                        paddingLeft: '12px',
                        paddingTop: '2px',
                        paddingBottom: '2px',
                      }}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <span
                          className="text-[9px] font-mono px-1 py-0.5 rounded"
                          style={{
                            backgroundColor: 'color-mix(in srgb, var(--color-info) 8%, transparent)',
                            color: 'var(--color-info)',
                          }}
                        >
                          #{chunk.chunk_index + 1}
                        </span>
                        <button
                          type="button"
                          className="text-[9px] opacity-0 group-hover:opacity-100 transition-opacity hover:underline"
                          style={{ color: 'var(--color-ai)' }}
                          onClick={() => {
                            document.getElementById(`chunk-${chunk.chunk_index}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                          }}
                        >
                          跳转
                        </button>
                      </div>
                      <div
                        style={{
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                        }}
                      >
                        {chunkText}
                      </div>
                    </div>
                  </React.Fragment>
                );
              })}
            </div>
          ) : chunksLoading ? (
            <div className="flex items-center gap-1.5 py-2" style={{ color: 'var(--text-muted)' }}>
              <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
              <span className="text-xs">加载分段…</span>
            </div>
          ) : (
            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {content}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
