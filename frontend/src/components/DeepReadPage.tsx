// DeepReadPage — Phase 4 S4-2: 深度分析面板 (分类型动态分节)
//
// 路由: /deep/:type/:id
// 布局: 顶部元信息条 (provider / model / latency / tokens / cost) + 动态分节折叠卡 + 重新生成按钮
//
// 分节集合由后端按**文章类型**下发 (视角 profile 决定有哪几节、叫什么、什么色调),
// 前端不再假设固定 4 节 —— 只负责按 tone 上色、按 key 查图标 (未知 key 用默认图标)。
// 首次生成会真调 LLM, sensenova 实测十几到几十秒, 二次访问命中后端缓存则瞬时返回。
//
// 与老版 DeepReadView 的区别:
//   - 老版: 三栏 (文章 / 推荐 / 笔记), 不调 LLM
//   - 新版: 分节报告, 调 /api/deep-read LLM 生成, 二次访问走 cache
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useDeepRead } from '../hooks/useDeepRead';
import { useGoHome } from '../hooks/useGoHome';
import { DeepReadSection, DeepReadTone } from '../types';

/** 语义三色锁 → 图标描边色 */
const TONE_COLOR: Record<DeepReadTone, string> = {
  mint: 'var(--color-success)',
  amber: 'var(--color-warning)',
  red: 'var(--color-error)',
};

/** 已知分节的图标; 未命中用 DEFAULT_ICON, 保证后端加节不需要改前端 */
const ICON_BY_KEY: Record<string, string> = {
  key_takeaways: 'M4 6h16M4 10h16M4 14h10M4 18h7',
  next_actions: 'M5 13l4 4L19 7',
  evidence_gaps: 'M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
  impact_ioc: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  exploit_conditions: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  remediation: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  attack_surface: 'M12 9v2m0 4h.01m-6.94 4h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.7-1.33-3.46 0L3.34 16c-.77 1.33.2 3 1.72 3z',
  mitigation: 'M4 4h16v16H4zM9 9h6v6H9z',
  detection: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  capability_boundary: 'M3 12h18M12 3v18M5.6 5.6l12.8 12.8',
  cost_alternatives: 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
  regulation_points: 'M4 4h16v16H4zM8 9h8M8 13h8M8 17h5',
  applicability: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm14 14v-2a4 4 0 0 0-3-3.87',
  obligations_timeline: 'M12 6v6l4 2m6-2a10 10 0 1 1-20 0 10 10 0 0 1 20 0z',
  penalty: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4m0 4h.01',
  tender_card: 'M3 5h18v14H3zM3 10h18M7 15h4',
  qualification: 'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
  scoring: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
  key_dates: 'M3 5h18v16H3zM3 9h18M8 2v4m8-4v4',
  positioning: 'M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z',
  adoption_cost: 'M20 12V8H4v12h16v-4M4 12h16M9 16h.01',
  license_risk: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4',
  biz_signal: 'M3 17l6-6 4 4 8-8m0 0h-6m6 0v6',
  playbook: 'M4 4h16v16H4zM10 9l5 3-5 3z',
  pitfalls: 'M12 9v4m0 4h.01M4.93 4.93l14.14 14.14M19.07 4.93L4.93 19.07',
  facts: 'M4 6h16M4 12h16M4 18h16',
  system_impact: 'M12 2v6m0 0l3-3m-3 3L9 5M4 14h16v6H4z',
  watch: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zm11 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  context: 'M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zM12 16v-4m0-4h.01',
  significance: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  // 历史遗留键 (旧行 sections_json 是扁平 4 键)
  summary: 'M4 6h16M4 10h16M4 14h16M4 18h16',
  impact: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  relations: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71',
  risks: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
};

const DEFAULT_ICON = 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 6v6m0-9h.01';

/**
 * LLM 正文里的 markdown 强调标记在本 UI 是纯文本渲染 (全仓无 markdown 依赖,
 * 也不该为剥几个符号引入带 XSS 面的渲染库), 这里做最小化清理。
 */
function stripInlineMarkdown(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*#{1,6}\s+/gm, '');
}

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

function SectionCard({ section }: { section: DeepReadSection }) {
  const [open, setOpen] = useState(true);
  const icon = ICON_BY_KEY[section.key] || DEFAULT_ICON;
  const stroke = TONE_COLOR[section.tone] || TONE_COLOR.mint;

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
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={icon} />
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
          {section.body.trim()
            ? stripInlineMarkdown(section.body)
            : <span style={{ color: 'var(--text-muted)' }}>本节暂无内容</span>}
        </div>
      )}
    </div>
  );
}

export function DeepReadPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const goHome = useGoHome();
  const { data, sections, loading, error, regenerate, clear } = useDeepRead();

  // 进入即分析: force=false 命中后端缓存则瞬时返回, 无缓存则直接调 LLM 生成
  useEffect(() => {
    if (!type || !id) return;
    regenerate(type, id, false);
    return clear;
  }, [type, id, regenerate, clear]);

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
            {data.category && (
              <span style={{ ...metaItemStyle, color: 'var(--color-ai)' }}>
                视角 {data.category}
              </span>
            )}
            <span style={metaItemStyle}>{data.provider || '-'}</span>
            <span style={metaItemStyle}>{data.model || '-'}</span>
            <span style={metaItemStyle}>{data.latency_ms}ms</span>
            <span style={metaItemStyle}>in {data.tokens_in} / out {data.tokens_out}</span>
            {/* 服务当前把 cost_usd 记为 0; 只在真记了账时展示, 不把 0 当既成事实呈现 */}
            {data.cost_usd > 0 && (
              <span style={metaItemStyle}>${data.cost_usd.toFixed(4)}</span>
            )}
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
          深度分析未完成, 点击右上角"重新生成"重试。
        </div>
      )}

      {/* 加载中 (首次要真调 LLM, 实测十几~几十秒) */}
      {loading && (
        <div
          style={{
            padding: 'var(--space-4, 16px)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 13,
            lineHeight: 1.7,
          }}
        >
          正在按文章类型生成深度解读，请稍候…
          <br />
          <span style={{ fontSize: 11 }}>首次生成需调用 AI，通常十几到几十秒；再次访问将直接读取已存结果。</span>
        </div>
      )}

      {/* 分节报告 (节集合与顺序由后端按文章类型下发) */}
      {data && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2, 8px)' }}>
          {sections.map((sec) => (
            <SectionCard key={sec.key} section={sec} />
          ))}
        </div>
      )}
    </div>
  );
}
