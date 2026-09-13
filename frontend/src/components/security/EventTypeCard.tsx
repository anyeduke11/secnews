/**
 * EventTypeCard — MP-2 单类事件类型的技战法卡 (L2 实例化渲染).
 *
 * 数据源: GET /api/event-technique/event-types/{id}/techniques (已审定 event_technique_map).
 * 按 kill_chain_stages 时间线分组展示 technique (name + stage + note + 溯源 source_url).
 * 空态: 该类尚无审定链 → 显示提示 (pending 候选数如传入).
 */
import { useMemo } from 'react';

export interface EventTypeInfo {
  id: string;
  name_zh: string;
  name_en: string;
  description?: string;
  kill_chain_stages: string[];
}

export interface MappedTechnique {
  map_id: string;
  technique_id: string;
  technique_name: string;
  stage: string;
  note?: string | null;
  approved_at: string;
  approved_by: string;
  source_url?: string | null;
}

interface EventTypeCardProps {
  eventType: EventTypeInfo;
  techniques: MappedTechnique[];
  pendingCount?: number;
  onSelectStage?: (stage: string) => void;
}

const CONFIDENCE_LABEL = '已审定';

export function EventTypeCard({ eventType, techniques, pendingCount, onSelectStage }: EventTypeCardProps) {
  const byStage = useMemo(() => {
    const map = new Map<string, MappedTechnique[]>();
    for (const t of techniques) {
      const list = map.get(t.stage) ?? [];
      list.push(t);
      map.set(t.stage, list);
    }
    return map;
  }, [techniques]);

  const stageOrder = useMemo(() => {
    const declared = eventType.kill_chain_stages ?? [];
    const extra = [...byStage.keys()].filter((s) => !declared.includes(s));
    return [...declared.filter((s) => byStage.has(s)), ...extra];
  }, [eventType.kill_chain_stages, byStage]);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" data-testid={`event-type-card-${eventType.id}`}>
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            {eventType.name_zh}
            <span className="ml-2 text-xs font-normal text-slate-500">{eventType.name_en}</span>
          </h3>
          {eventType.description && (
            <p className="mt-1 text-xs leading-relaxed text-slate-500">{eventType.description}</p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <span className="inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
            {CONFIDENCE_LABEL} {techniques.length}
          </span>
          {typeof pendingCount === 'number' && pendingCount > 0 && (
            <p className="mt-1 text-[11px] text-amber-600">待审 {pendingCount}</p>
          )}
        </div>
      </header>

      {techniques.length === 0 ? (
        <p className="rounded border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-center text-xs text-slate-400">
          该事件类型尚无已审定技战法链 (owner 人审后在此展示)
        </p>
      ) : (
        <ol className="space-y-3">
          {stageOrder.map((stage) => (
            <li key={stage}>
              <button
                type="button"
                onClick={() => onSelectStage?.(stage)}
                className="mb-1 inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-700"
              >
                <span className="inline-block h-2 w-2 rounded-full bg-sky-500" aria-hidden="true" />
                {stage}
              </button>
              <ul className="ml-2 space-y-1 border-l border-slate-200 pl-3">
                {(byStage.get(stage) ?? []).map((t) => (
                  <li key={t.map_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-700">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                      {t.technique_id}
                    </span>
                    <span className="font-medium">{t.technique_name}</span>
                    {t.note && <span className="text-[11px] text-slate-400">{t.note}</span>}
                    {t.source_url && (
                      <a
                        href={t.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-sky-600 underline-offset-2 hover:underline"
                      >
                        溯源
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default EventTypeCard;
