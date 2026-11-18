// 拆分自 DeepReadPage.tsx: v3.1 标题区 (headline 大标题 + 解读框架选择器)。
// 选择框架即触发重新生成, 生成动作经 onRegenerate 回到页面层。
import { DeepReadResponse } from '../types';

type DeepReadPageHeaderProps = {
  data: DeepReadResponse | null;
  loading: boolean;
  pickedFramework: string;
  onPickFramework: (fw: string) => void;
  onRegenerate: (fw?: string) => void;
};

export function DeepReadPageHeader({
  data,
  loading,
  pickedFramework,
  onPickFramework,
  onRegenerate,
}: DeepReadPageHeaderProps) {
  return (
    <>
      {(data?.headline || data) && !loading && (
        <div
          style={{
            padding: 'var(--space-4, 16px)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md, 8px)',
            background: 'var(--bg-card)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2, 8px)',
          }}
        >
          {data?.headline && (
            <h1
              style={{
                margin: 0,
                fontSize: 20,
                fontWeight: 700,
                lineHeight: 1.5,
                color: 'var(--text-primary)',
              }}
            >
              {data.headline}
            </h1>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2, 8px)' }}>
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
              解读框架
            </span>
            <select
              value={pickedFramework}
              disabled={loading}
              onChange={(e) => {
                const fw = e.target.value;
                onPickFramework(fw);
                // 选择即生成: 自动档也允许主动切回 (重调 LLM 自选)
                onRegenerate(fw || undefined);
              }}
              style={{
                fontSize: 11,
                fontFamily: 'monospace',
                color: 'var(--color-ai)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm, 4px)',
                border: '1px solid var(--border-color)',
                background: 'color-mix(in srgb, var(--border-color) 40%, transparent)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
              data-testid="framework-select"
            >
              <option value="">自动（LLM 按内容自选）</option>
              <option value="what_why_how">What / Why / How（认知框架）</option>
              <option value="swot_lite">SWOT（机会 vs 威胁）</option>
              <option value="five_w">5W（主体·时点·范围）</option>
            </select>
            {data?.framework && !pickedFramework && (
              <span
                style={{
                  fontSize: 11,
                  fontFamily: 'monospace',
                  color: 'var(--text-muted)',
                }}
              >
                当前: {data.framework}
              </span>
            )}
          </div>
        </div>
      )}
    </>
  );
}