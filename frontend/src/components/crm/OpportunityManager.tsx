/**
 * OpportunityManager — 商机推进 (PRD US-2)
 *
 * 列表 + 新建 + 状态机推进。阶段变更只走 POST /transition
 * (后端为唯一裁决者, 前端 STAGE_FLOW 仅用于渲染可推进按钮);
 * 推进到「输单」时要求填写丢单原因。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { crmFetch, STAGE_FLOW } from '../../lib/crm';
import type { CrmCustomer, CrmListResponse, CrmMeta, CrmOpportunity } from '../../types/crm';

const BADGE_COLOR: Record<string, string> = {
  需求沟通: 'var(--text-muted)',
  方案提交: '#2563eb',
  商务谈判: '#d97706',
  合同签订: '#7c3aed',
  赢单: '#16a34a',
  输单: 'var(--color-error)',
};

interface Props {
  meta: CrmMeta | null;
}

export function OpportunityManager({ meta }: Props) {
  const [opps, setOpps] = useState<CrmOpportunity[]>([]);
  const [customers, setCustomers] = useState<CrmCustomer[]>([]);
  const [stageF, setStageF] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ customer_id: '', name: '', service_type: '安全评估', amount: '', cost: '' });

  const load = useCallback(async () => {
    try {
      const [oppData, custData] = await Promise.all([
        crmFetch<CrmListResponse<CrmOpportunity>>(
          stageF ? `/api/crm/opportunities?stage=${encodeURIComponent(stageF)}` : '/api/crm/opportunities',
        ),
        crmFetch<CrmListResponse<CrmCustomer>>('/api/crm/customers?limit=500'),
      ]);
      setOpps(oppData.items);
      setCustomers(custData.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [stageF]);

  useEffect(() => { void load(); }, [load]);

  const customerName = useMemo(() => new Map(customers.map(c => [c.id, c.name])), [customers]);

  const create = async () => {
    try {
      await crmFetch('/api/crm/opportunities', {
        method: 'POST',
        body: JSON.stringify({
          customer_id: Number(form.customer_id),
          name: form.name.trim(),
          ...(form.service_type ? { service_type: form.service_type } : {}),
          ...(form.amount !== '' ? { amount: Number(form.amount) } : {}),
          ...(form.cost !== '' ? { cost: Number(form.cost) } : {}),
        }),
      });
      setCreating(false);
      setForm({ customer_id: '', name: '', service_type: '安全评估', amount: '', cost: '' });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  /** 推进到下一阶段; 输单需要丢单原因 */
  const transition = async (o: CrmOpportunity, toStage: string) => {
    let lostReason = '';
    if (toStage === '输单') {
      lostReason = window.prompt(`商机「${o.name}」输单原因:`) ?? '';
      if (!lostReason.trim()) return; // 无原因不推进
    }
    try {
      await crmFetch(`/api/crm/opportunities/${o.id}/transition`, {
        method: 'POST',
        body: JSON.stringify({ to_stage: toStage, lost_reason: lostReason }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const stages = meta?.stages ?? Object.keys(STAGE_FLOW);
  const inputCls = 'border rounded px-2 py-1 text-xs bg-transparent';
  const borderStyle = { borderColor: 'var(--border-color)', color: 'var(--text-primary)' } as const;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={stageF} onChange={e => setStageF(e.target.value)} className={inputCls} style={borderStyle} aria-label="按阶段过滤">
          <option value="">全部阶段</option>
          {stages.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={() => setCreating(o => !o)} className="px-3 py-1 rounded text-xs font-semibold" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
          {creating ? '收起' : '+ 新建商机'}
        </button>
      </div>

      {error && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}

      {creating && (
        <div className="border rounded p-3 space-y-2" style={borderStyle}>
          <h3 className="text-xs font-semibold">新建商机</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <select value={form.customer_id} onChange={e => setForm({ ...form, customer_id: e.target.value })} className={inputCls} style={borderStyle} aria-label="所属客户">
              <option value="">选择客户 *</option>
              {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="商机名 *" className={inputCls} style={borderStyle} aria-label="商机名" />
            <input value={form.service_type} onChange={e => setForm({ ...form, service_type: e.target.value })} placeholder="服务类型" className={inputCls} style={borderStyle} aria-label="服务类型" />
            <input value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="金额 (元)" type="number" min="0" className={inputCls} style={borderStyle} aria-label="金额" />
            <input value={form.cost} onChange={e => setForm({ ...form, cost: e.target.value })} placeholder="成本 (元)" type="number" min="0" className={inputCls} style={borderStyle} aria-label="成本" />
          </div>
          <button onClick={() => void create()} disabled={!form.customer_id || !form.name.trim()} className="px-3 py-1 rounded text-xs font-semibold disabled:opacity-40" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
            创建
          </button>
        </div>
      )}

      <table className="w-full text-left" data-testid="opportunity-table">
        <thead>
          <tr className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            <th className="py-1 pr-2">商机</th><th className="pr-2">客户</th><th className="pr-2">阶段</th>
            <th className="pr-2">金额</th><th className="pr-2">成本</th><th className="pr-2">负责人</th><th>推进</th>
          </tr>
        </thead>
        <tbody>
          {opps.map(o => (
            <tr key={o.id} className="text-xs border-t align-middle" style={borderStyle}>
              <td className="py-1.5 pr-2 font-medium">{o.name}</td>
              <td className="pr-2">{customerName.get(o.customer_id) ?? `#${o.customer_id}`}</td>
              <td className="pr-2">
                <span
                  className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold"
                  style={{ color: BADGE_COLOR[o.stage], border: `1px solid ${BADGE_COLOR[o.stage]}` }}
                >
                  {o.stage}
                </span>
                {o.stage === '输单' && o.lost_reason && (
                  <span className="block text-[10px]" style={{ color: 'var(--text-muted)' }} title={o.lost_reason}>
                    {o.lost_reason.slice(0, 12)}
                  </span>
                )}
              </td>
              <td className="pr-2 font-mono tabular-nums">¥{Math.round(o.amount).toLocaleString('zh-CN')}</td>
              <td className="pr-2 font-mono tabular-nums">¥{Math.round(o.cost).toLocaleString('zh-CN')}</td>
              <td className="pr-2">{o.owner || '—'}</td>
              <td className="pr-2 whitespace-nowrap">
                {(STAGE_FLOW[o.stage] ?? []).map(next => (
                  <button
                    key={next}
                    onClick={() => void transition(o, next)}
                    className="underline mr-2"
                    style={{ color: next === '输单' ? 'var(--color-error)' : 'var(--text-secondary)' }}
                  >
                    {next === '输单' ? '标记输单' : `→ ${next}`}
                  </button>
                ))}
                {(STAGE_FLOW[o.stage] ?? []).length === 0 && <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>已终态</span>}
              </td>
            </tr>
          ))}
          {opps.length === 0 && (
            <tr><td colSpan={7} className="py-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>暂无商机</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
