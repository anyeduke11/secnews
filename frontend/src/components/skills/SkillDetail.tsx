/**
 * SkillDetail — 技能详情页 (v0.8 Phase B, Task B6)
 *
 * 数据面: GET /api/skill-registry/{id} (A3 detail) + GET /{id}/runs (B6)。
 * 版面: 基本信息 (类别/类型/runner/超时/门控) → input/output schema 表 →
 * C/D 类 prompt 全文 → RunHistory 历史回放。
 * 组件保持 router-free: skillId/onBack 由路由包装层注入; ?focus=history
 * 用于商店「历史」按钮直达历史区 (仅锚定滚动)。
 */
import { useEffect, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useSkillDetail } from '../../hooks/useSkillRegistry';
import { CATEGORY_LABELS, SKILL_TYPE_LABELS, SkillDetail as SkillDetailData } from '../../types/skill';
import { RunHistory } from './RunHistory';

function SchemaTable({ title, schema }: { title: string; schema: Record<string, string> }) {
  const entries = Object.entries(schema ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-mono uppercase mb-1" style={{ color: 'var(--ink-3)' }}>
        {title}
      </div>
      <div
        className="rounded-md overflow-hidden text-[12.5px]"
        style={{ border: '1px solid var(--line)' }}
      >
        {entries.map(([field, type], i) => (
          <div
            key={field}
            className="flex items-center gap-3 px-2.5 py-1.5"
            style={{
              backgroundColor: i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-lift)',
              borderTop: i === 0 ? 'none' : '1px solid var(--line)',
            }}
          >
            <span className="font-mono" style={{ color: 'var(--ink)' }}>
              {field}
            </span>
            <span className="font-mono text-[11.5px] ml-auto" style={{ color: 'var(--ink-3)' }}>
              {type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2 text-[12.5px]">
      <span className="shrink-0" style={{ color: 'var(--ink-3)' }}>
        {label}
      </span>
      <span className="font-mono truncate" style={{ color: 'var(--ink)' }}>
        {value}
      </span>
    </div>
  );
}

export function SkillDetail({ skillId: skillIdProp, onBack }: { skillId?: string; onBack?: () => void }) {
  // skillId 优先取 prop; 单测裸渲染场景下空 prop 可从路由参数 fallback (router-free 设计)
  const params = useParams<{ skillId: string }>();
  const skillId = skillIdProp || params.skillId || '';
  const { detail, loading, error, refresh } = useSkillDetail(skillId);
  const [searchParams] = useSearchParams();
  const historyRef = useRef<HTMLElement | null>(null);

  // 商店「历史」按钮带 ?focus=history → 锚定历史区; detail 异步加载完成后再次触发
  // (初次渲染时 ref.current 尚未绑定, 必须等 detail 渲染后再调一次)
  useEffect(() => {
    if (searchParams.get('focus') === 'history' && historyRef.current) {
      historyRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [searchParams, detail]);

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-[900px] mx-auto w-full">
      {/* 页头 */}
      <header className="flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            aria-label="返回商店"
            className="h-8 px-2.5 rounded-md text-sm border"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
          >
            ←
          </button>
        )}
        <h1 className="text-lg font-bold truncate" style={{ color: 'var(--ink)' }}>
          {loading ? '技能详情' : detail?.name ?? '技能详情'}
        </h1>
        {detail && (
          <span
            className="px-1.5 py-0.5 rounded text-[11px] font-mono shrink-0"
            style={{
              color: detail.enabled ? 'var(--mint)' : 'var(--ink-3)',
              backgroundColor: 'var(--bg-hover)',
            }}
          >
            {detail.enabled ? '[ON]' : '[OFF]'}
          </span>
        )}
      </header>

      {/* 三态 */}
      {loading && (
        <div role="status" className="py-16 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
          技能详情加载中…
        </div>
      )}
      {!loading && error && (
        <div role="alert" className="py-10 flex flex-col items-center gap-3" style={{ color: 'var(--red)' }}>
          <p className="text-sm">{error}</p>
          <button
            type="button"
            onClick={refresh}
            className="h-8 px-3 rounded-md text-[13px] border"
            style={{ borderColor: 'var(--red)', color: 'var(--red)' }}
          >
            重试
          </button>
        </div>
      )}
      {!loading && !error && detail && <DetailBody detail={detail} historyRef={historyRef} />}
    </div>
  );
}

function DetailBody({
  detail,
  historyRef,
}: {
  detail: SkillDetailData;
  historyRef: React.RefObject<HTMLElement | null>;
}) {
  return (
    <>
      {/* 基本信息 */}
      <section
        aria-label="基本信息"
        className="rounded-md p-3 flex flex-col gap-1.5"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
      >
        <p className="text-[13px] m-0 leading-relaxed" style={{ color: 'var(--ink-2)' }}>
          {detail.desc}
        </p>
        <MetaRow label="类别" value={CATEGORY_LABELS[detail.category] ?? detail.category} />
        <MetaRow
          label="类型"
          value={`${detail.skill_type} ${SKILL_TYPE_LABELS[detail.skill_type] ?? detail.skill_type}`}
        />
        <MetaRow label="runner" value={detail.runner} />
        <MetaRow label="超时" value={`${detail.timeout_seconds}s`} />
        {detail.feature_gate && <MetaRow label="门控" value={detail.feature_gate} />}
        <MetaRow label="技能 ID" value={detail.id} />
      </section>

      {/* schema */}
      <SchemaTable title="输入字段 (input_schema)" schema={detail.input_schema} />
      <SchemaTable title="输出字段 (output_schema)" schema={detail.output_schema} />

      {/* C/D 类 prompt 全文 */}
      {detail.prompt_template && (
        <div className="min-w-0">
          <div className="text-[11px] font-mono uppercase mb-1" style={{ color: 'var(--ink-3)' }}>
            Prompt 模板
          </div>
          <pre
            className="text-[12px] font-mono whitespace-pre-wrap break-all rounded p-2.5 m-0"
            style={{ backgroundColor: 'var(--bg-lift)', color: 'var(--ink-2)' }}
          >
            {detail.prompt_template}
          </pre>
        </div>
      )}

      {/* 历史回放 */}
      <section ref={historyRef as React.RefObject<HTMLElement>}>
        <RunHistory skillId={detail.id} />
      </section>
    </>
  );
}
