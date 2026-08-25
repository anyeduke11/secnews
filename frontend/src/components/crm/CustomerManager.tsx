/**
 * CustomerManager — 客户录入与维护 (PRD US-1)
 *
 * 列表 (updated_at DESC) + 状态/等级/关键词过滤 + 新建/编辑/删除。
 * 全部走 /api/crm/customers; 错误信息来自后端 detail.message。
 */
import { useCallback, useEffect, useState } from 'react';
import { crmFetch } from '../../lib/crm';
import type { CrmCustomer, CrmListResponse, CrmMeta } from '../../types/crm';

const EMPTY_FORM = {
  name: '', industry: '', level: 'B', status: '活跃', region: '华东',
  owner: '', contact_name: '', contact_phone: '', email: '',
  contract_amount: '', nps_score: '',
};
type CustomerForm = typeof EMPTY_FORM;

function toForm(c: CrmCustomer): CustomerForm {
  return {
    name: c.name, industry: c.industry, level: c.level, status: c.status,
    region: c.region, owner: c.owner, contact_name: c.contact_name,
    contact_phone: c.contact_phone, email: c.email,
    contract_amount: c.contract_amount ? String(c.contract_amount) : '',
    nps_score: c.nps_score === null ? '' : String(c.nps_score),
  };
}

/** 表单 → 后端 payload (空串转 null, exclude_none 由后端处理) */
function toPayload(f: CustomerForm): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (f.name.trim()) out.name = f.name.trim();
  for (const k of ['industry', 'level', 'status', 'region', 'owner', 'contact_name', 'contact_phone', 'email'] as const) {
    if (f[k]) out[k] = f[k];
  }
  if (f.contract_amount !== '') out.contract_amount = Number(f.contract_amount);
  if (f.nps_score !== '') out.nps_score = Number(f.nps_score);
  return out;
}

interface Props {
  meta: CrmMeta | null;
}

export function CustomerManager({ meta }: Props) {
  const [rows, setRows] = useState<CrmCustomer[]>([]);
  const [q, setQ] = useState('');
  const [statusF, setStatusF] = useState('');
  const [levelF, setLevelF] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CrmCustomer | 'new' | null>(null);
  const [form, setForm] = useState<CustomerForm>(EMPTY_FORM);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (statusF) params.set('status', statusF);
      if (levelF) params.set('level', levelF);
      const data = await crmFetch<CrmListResponse<CrmCustomer>>(`/api/crm/customers?${params}`);
      setRows(data.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [q, statusF, levelF]);

  useEffect(() => { void load(); }, [load]);

  const openNew = () => { setEditing('new'); setForm(EMPTY_FORM); };
  const openEdit = (c: CrmCustomer) => { setEditing(c); setForm(toForm(c)); };

  const submit = async () => {
    try {
      const payload = toPayload(form);
      if (editing === 'new') {
        await crmFetch('/api/crm/customers', { method: 'POST', body: JSON.stringify(payload) });
      } else if (editing) {
        await crmFetch(`/api/crm/customers/${editing.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      }
      setEditing(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (c: CrmCustomer) => {
    if (!window.confirm(`删除客户「${c.name}」? 其名下商机与事件将级联删除。`)) return;
    try {
      await crmFetch(`/api/crm/customers/${c.id}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const industries = meta?.industries ?? [];
  const levels = meta?.levels ?? ['S', 'A', 'B', 'C'];
  const statuses = meta?.statuses ?? ['活跃', '续约中', '停滞', '流失'];
  const inputCls = 'border rounded px-2 py-1 text-xs bg-transparent';
  const borderStyle = { borderColor: 'var(--border-color)', color: 'var(--text-primary)' } as const;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q} onChange={e => setQ(e.target.value)} placeholder="搜索客户/联系人…"
          className={`${inputCls} w-48`} style={borderStyle} aria-label="搜索客户"
        />
        <select value={statusF} onChange={e => setStatusF(e.target.value)} className={inputCls} style={borderStyle} aria-label="按状态过滤">
          <option value="">全部状态</option>
          {statuses.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={levelF} onChange={e => setLevelF(e.target.value)} className={inputCls} style={borderStyle} aria-label="按等级过滤">
          <option value="">全部等级</option>
          {levels.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <button onClick={openNew} className="px-3 py-1 rounded text-xs font-semibold" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
          + 新建客户
        </button>
      </div>

      {error && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}

      {editing !== null && (
        <div className="border rounded p-3 space-y-2" style={borderStyle}>
          <h3 className="text-xs font-semibold">{editing === 'new' ? '新建客户' : `编辑: ${editing.name}`}</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="客户名 *" className={inputCls} style={borderStyle} aria-label="客户名" />
            <input value={form.industry} onChange={e => setForm({ ...form, industry: e.target.value })} placeholder="行业" list="crm-industries" className={inputCls} style={borderStyle} aria-label="行业" />
            <datalist id="crm-industries">{industries.map(i => <option key={i} value={i} />)}</datalist>
            <select value={form.level} onChange={e => setForm({ ...form, level: e.target.value })} className={inputCls} style={borderStyle} aria-label="等级">
              {levels.map(l => <option key={l} value={l}>{l} 级</option>)}
            </select>
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={inputCls} style={borderStyle} aria-label="状态">
              {statuses.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <input value={form.region} onChange={e => setForm({ ...form, region: e.target.value })} placeholder="区域" className={inputCls} style={borderStyle} aria-label="区域" />
            <input value={form.owner} onChange={e => setForm({ ...form, owner: e.target.value })} placeholder="负责人" className={inputCls} style={borderStyle} aria-label="负责人" />
            <input value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} placeholder="联系人" className={inputCls} style={borderStyle} aria-label="联系人" />
            <input value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} placeholder="电话" className={inputCls} style={borderStyle} aria-label="电话" />
            <input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="邮箱" type="email" className={inputCls} style={borderStyle} aria-label="邮箱" />
            <input value={form.contract_amount} onChange={e => setForm({ ...form, contract_amount: e.target.value })} placeholder="合同额 (元)" type="number" min="0" className={inputCls} style={borderStyle} aria-label="合同额" />
            <input value={form.nps_score} onChange={e => setForm({ ...form, nps_score: e.target.value })} placeholder="NPS (0-10)" type="number" min="0" max="10" className={inputCls} style={borderStyle} aria-label="NPS 分" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => void submit()} className="px-3 py-1 rounded text-xs font-semibold" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
              保存
            </button>
            <button onClick={() => setEditing(null)} className="px-3 py-1 rounded text-xs border" style={borderStyle}>取消</button>
          </div>
        </div>
      )}

      <table className="w-full text-left" data-testid="customer-table">
        <thead>
          <tr className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            <th className="py-1 pr-2">客户</th><th className="pr-2">行业</th><th className="pr-2">等级</th>
            <th className="pr-2">状态</th><th className="pr-2">区域</th><th className="pr-2">合同额</th>
            <th className="pr-2">NPS</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(c => (
            <tr key={c.id} className="text-xs border-t" style={borderStyle}>
              <td className="py-1.5 pr-2 font-medium">{c.name}</td>
              <td className="pr-2">{c.industry}</td>
              <td className="pr-2 font-mono">{c.level}</td>
              <td className="pr-2">{c.status}</td>
              <td className="pr-2">{c.region}</td>
              <td className="pr-2 font-mono tabular-nums">¥{Math.round(c.contract_amount).toLocaleString('zh-CN')}</td>
              <td className="pr-2 font-mono tabular-nums">{c.nps_score ?? '—'}</td>
              <td className="pr-2 whitespace-nowrap">
                <button onClick={() => openEdit(c)} className="underline mr-2" style={{ color: 'var(--text-secondary)' }}>编辑</button>
                <button onClick={() => void remove(c)} className="underline" style={{ color: 'var(--color-error)' }}>删除</button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={8} className="py-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>暂无客户, 点击「新建客户」开始录入</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
