// DeepReadPage — Phase 4 S4-2: 4 节深度分析面板
//
// 路由: /deep/:type/:id
// 布局: 顶部元信息条 (provider / model / latency / tokens) + 4 节折叠卡 + 重新生成按钮
//
// 与老版 DeepReadView 的区别:
//   - 老版: 三栏 (文章 / 推荐 / 笔记), 不调 LLM
//   - 新版: 单栏 4 节报告, 调 /api/deep-read LLM 生成, 二次访问走 cache
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useDeepRead } from '../hooks/useDeepRead';
import { useGoHome } from '../hooks/useGoHome';

interface SectionDef {
  key: 'summary' | 'impact' | 'relations' | 'risks';
  title: string;
  icon: string;  // SVG path d
  color: string; // CSS var 引用
}

const SECTIONS: SectionDef[] = [
  {
    key: 'summary',
    title: '摘要',
    icon: 'M4 6h16M4 10h16M4 14h16M4 18h16', // 简化横线 (代替 bar-chart)
    color: 'var(--color-ai)',
  },
  {
    key: 'impact',
    title: '影响',
    icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
    color: 'var(--color-warning)',
  },
  {
    key: 'relations',
    title: '关联',
    icon: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71',
    color: 'var(--color-success)',
  },
  {
    key: 'risks',
    title: '风险',
    icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
    color: 'var(--color-error)',
  },
];

const metaItemStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--space-1, 4px)',
  fontSize: 11,
  color: 'var(--text-muted)',
  fontFamily: 'monospace',
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'color-mix(in srgb, var(--border-color) 40%, transparent)',
};

function SectionCard({ section, body }: { section: SectionDef; body: string }) {
  const [open, setOpen] = useState(true);

  return (
    <div
      style={{
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md, 8px)',
        background: 'var(--bg-card)',
        overflow: 'hidden',
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2, 8px)',
          width: '100%',
          padding: 'var(--space-3, 12px) var(--space-4, 16px)',
          border: 'none',
          background: 'color-mix(in srgb, var(--bg-elevated) 80%, transparent)',
          color: 'var(--text-primary)',
          cursor: 'pointer',
          fontSize: 14,
          fontWeight: 600,
          lineHeight: 1.4,
          textAlign: 'left',
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke={section.color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={section.icon} />
        </svg>
        <span style={{ flex: 1 }}>{section.title}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s ease',
          }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          style={{
            padding: 'var(--space-4, 16px)',
            borderTop: '1px solid var(--border-color)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: 1.7,
            fontSize: 14,
            color: 'var(--text-secondary)',
            minHeight: 48,
          }}
        >
          {body || <span style={{ color: 'var(--text-muted)' }}>_(本节暂无内容)_</span>}
        </div>
      )}
    </div>
  );
}

export function DeepReadPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const goHome = useGoHome();
  const { data, sections, loading, error, fetch, regenerate, clear } = useDeepRead();

  // 路由参数变化时重新拉取
  useEffect(() => {
    if (!type || !id) return;
    fetch(type, id);
    return clear;
  }, [type, id, fetch, clear]);

  const handleRegenerate = useCallback(async () => {
    if (!type || !id) return;
    await regenerate(type, id, true);
  }, [type, id, regenerate]);

  if (!type || !id) {
    return (
      <div style={{ padding: 'var(--space-6, 32px)', textAlign: 'center', color: 'var(--text-muted)' }}>
        缺少实体类型或 ID
      </div>
    );
  }

  const isEmpty = !data && !loading && !error;

  return (
    <div
      style={{
        maxWidth: '72ch',
        margin: '0 auto',
        padding: 'var(--space-4, 16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3, 12px)',
      }}
    >
      {/* 顶部元信息条 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 'var(--space-2, 8px)',
          padding: 'var(--space-3, 12px)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-md, 8px)',
          background: 'var(--bg-card)',
        }}
      >
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 'var(--space-1, 4px)' }}>
          {type}/{id}
        </span>
        {data && (
          <>
            <span style={metaItemStyle}>{data.provider || '-'}</span>
            <span style={metaItemStyle}>{data.model || '-'}</span>
            <span style={metaItemStyle}>{data.latency_ms}ms</span>
            <span style={metaItemStyle}>in {data.tokens_in} / out {data.tokens_out}</span>
            <span style={{ ...metaItemStyle, color: 'var(--text-muted)' }}>
              {new Date(data.updated_at).toLocaleString('zh-CN')}
            </span>
          </>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={handleRegenerate}
          disabled={loading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--space-1, 4px)',
            padding: '4px 12px',
            borderRadius: 'var(--radius-sm, 4px)',
            border: '1px solid var(--border-color)',
            background: loading
              ? 'color-mix(in srgb, var(--color-ai) 20%, transparent)'
              : 'color-mix(in srgb, var(--color-ai) 12%, transparent)',
            color: 'var(--color-ai)',
            fontSize: 12,
            cursor: loading ? 'not-allowed' : 'pointer',
            lineHeight: '20px',
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M1 4v6h6M23 20v-6h-6" />
            <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" />
          </svg>
          {loading ? '生成中…' : '重新生成'}
        </button>
        <button
          onClick={goHome}
          style={{
            padding: '4px 12px',
            borderRadius: 'var(--radius-sm, 4px)',
            border: '1px solid var(--border-color)',
            background: 'transparent',
            color: 'var(--text-muted)',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          返回
        </button>
      </div>

      {/* 错误 */}
      {error && (
        <div
          style={{
            padding: 'var(--space-3, 12px)',
            border: '1px solid var(--color-error)',
            borderRadius: 'var(--radius-md, 8px)',
            background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
            color: 'var(--color-error)',
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {/* 空状态 (首次访问, 无 cache) */}
      {isEmpty && !error && (
        <div
          style={{
            padding: 'var(--space-6, 32px)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 13,
          }}
        >
          暂无分析, 点击右上角"重新生成"触发 LLM 深度分析。
        </div>
      )}

      {/* 加载中 */}
      {loading && (
        <div
          style={{
            padding: 'var(--space-4, 16px)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 13,
          }}
        >
          正在生成 4 节深度分析, 请稍候…
        </div>
      )}

      {/* 4 节报告 */}
      {data && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2, 8px)' }}>
          {SECTIONS.map((sec) => (
            <SectionCard
              key={sec.key}
              section={sec}
              body={sections[sec.key] || ''}
            />
          ))}
        </div>
      )}
    </div>
  );
}
