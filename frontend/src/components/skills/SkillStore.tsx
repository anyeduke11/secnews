/**
 * SkillStore — 技能商店主页面 (v0.8 Phase A, Task A4)
 *
 * 数据面: /api/skill-registry (A3)。category 下拉走服务端过滤 (hook 参数重拉);
 * skill_type / 状态 / 搜索为本地过滤。卡片网格 4 列桌面响应式。
 *
 * 行为:
 *  - 跑一次 → POST /{id}/run, 成功内联提示「已加入执行队列 · ticket tg-xxx」
 *    (Phase A 预注册态: 只入队不执行, 文案不暴露内部阶段字样);
 *    错误信封 {detail:{message}} 已被 apiFetch 提为 Error.message, 再按
 *    后端语义 (未启用 → 提示先启用; 触发过于频繁 → 提示稍后再试) 转译。
 *  - 启停: 二次确认在 SkillToggle (window.confirm, 仓库既有模式), 成功后 refresh。
 *  - 详情/历史: B6 接线 → 跳 /skill-store/:skillId (历史带 ?focus=history);
 *    回调由路由包装层注入, 页面组件保持 router-free (单测免 Router 包装)。
 *
 * 文案暂硬编码中文 (i18n 接入为 D3 任务; I18nContext 只读使用无既有 key 可复用)。
 * TODO(v0.8 D3): 接入 useI18n 后迁移本页文案。
 */
import { useMemo, useState } from 'react';
import { CATEGORY_LABELS, SKILL_TYPE_LABELS, SkillCategory, SkillTypeCode, SkillSummary } from '../../types/skill';
import { postJSON } from '../../lib/api';
import { useSkillRegistry, useSkillToggle } from '../../hooks/useSkillRegistry';
import { SkillCard } from './SkillCard';

type StatusFilter = 'all' | 'enabled' | 'disabled';

interface Notice {
  kind: 'ok' | 'err';
  text: string;
}

/** run 错误转译 — 后端 409 SKILL_DISABLED / 429 THROTTLED 的 message 语义 */
function runErrorMessage(raw: string): string {
  if (raw.includes('未启用')) return '该技能未启用，请先开启后再运行';
  if (raw.includes('触发过于频繁')) return '触发过于频繁，请稍后再试';
  return raw || '运行请求失败';
}

export function SkillStore({
  onBack,
  onDetail,
  onHistory,
}: {
  onBack?: () => void;
  /** B6: 跳详情页 (路由包装层注入) */
  onDetail?: (skillId: string) => void;
  /** B6: 跳详情页并锚定历史区 */
  onHistory?: (skillId: string) => void;
}) {
  const [category, setCategory] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  const { skills, loading, error, refresh } = useSkillRegistry(
    category === 'all' ? undefined : category
  );
  const { toggle, busy } = useSkillToggle();

  const visible = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return skills.filter(s => {
      if (typeFilter !== 'all' && s.skill_type !== typeFilter) return false;
      if (statusFilter === 'enabled' && !s.enabled) return false;
      if (statusFilter === 'disabled' && s.enabled) return false;
      if (kw && !(`${s.name} ${s.desc}`.toLowerCase().includes(kw))) return false;
      return true;
    });
  }, [skills, typeFilter, statusFilter, search]);

  const handleToggle = async (skill: SkillSummary, next: boolean) => {
    try {
      await toggle(skill.id, next);
      setNotice({ kind: 'ok', text: `「${skill.name}」已${next ? '启用' : '停用'}` });
      refresh();
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : '启停操作失败';
      setNotice({ kind: 'err', text: msg });
    }
  };

  const handleRun = async (skill: SkillSummary) => {
    if (runningId) return;
    setRunningId(skill.id);
    try {
      const resp = await postJSON<{ ticket_id?: string }>(
        `/api/skill-registry/${encodeURIComponent(skill.id)}/run`,
        { inputs: null }
      );
      setNotice({
        kind: 'ok',
        text: resp?.ticket_id
          ? `「${skill.name}」已加入执行队列 · ticket ${resp.ticket_id}`
          : `「${skill.name}」已加入执行队列`,
      });
    } catch (err) {
      const raw = err instanceof Error ? err.message : '';
      setNotice({ kind: 'err', text: runErrorMessage(raw) });
    } finally {
      setRunningId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-4 md:p-6 max-w-[1400px] mx-auto w-full">
      {/* 页头 */}
      <header className="flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            aria-label="返回"
            className="h-8 px-2.5 rounded-md text-sm border"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
          >
            ←
          </button>
        )}
        <h1 className="text-lg font-bold" style={{ color: 'var(--ink)' }}>
          技能商店
        </h1>
        <span className="text-[12px] font-mono" style={{ color: 'var(--ink-3)' }}>
          {loading ? '…' : `${visible.length} / ${skills.length} 项`}
        </span>
      </header>

      {/* 筛选栏: 类别(服务端) + 类型/状态/搜索(本地) */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="类别筛选"
          value={category}
          onChange={e => setCategory(e.target.value)}
          className="h-8 px-2 rounded-md text-[13px] border bg-transparent"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
        >
          <option value="all">全部分类</option>
          {(Object.keys(CATEGORY_LABELS) as SkillCategory[]).map(c => (
            <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
          ))}
        </select>
        <select
          aria-label="类型筛选"
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="h-8 px-2 rounded-md text-[13px] border bg-transparent"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
        >
          <option value="all">全部类型</option>
          {(Object.keys(SKILL_TYPE_LABELS) as SkillTypeCode[]).map(t => (
            <option key={t} value={t}>{`${t} ${SKILL_TYPE_LABELS[t]}`}</option>
          ))}
        </select>
        <select
          aria-label="状态筛选"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as StatusFilter)}
          className="h-8 px-2 rounded-md text-[13px] border bg-transparent"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
        >
          <option value="all">全部状态</option>
          <option value="enabled">已启用</option>
          <option value="disabled">未启用</option>
        </select>
        <input
          aria-label="搜索技能"
          type="search"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="搜索名称或描述…"
          className="h-8 px-2.5 rounded-md text-[13px] border bg-transparent w-52"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
        />
      </div>

      {/* 操作反馈: 成功 status / 失败 alert */}
      {notice && (
        <div
          role={notice.kind === 'ok' ? 'status' : 'alert'}
          className="rounded-md px-3 py-2 text-[13px] border"
          style={{
            color: notice.kind === 'ok' ? 'var(--mint)' : 'var(--red)',
            borderColor: notice.kind === 'ok' ? 'var(--mint)' : 'var(--red)',
            backgroundColor: 'var(--bg-lift)',
          }}
        >
          {notice.text}
        </div>
      )}

      {/* 主体三态 */}
      {loading && (
        <div role="status" className="py-16 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
          技能清单加载中…
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
      {!loading && !error && visible.length === 0 && (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
          {skills.length === 0 ? '暂无已注册技能' : '没有匹配的技能，请调整筛选条件'}
        </div>
      )}
      {!loading && !error && visible.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {visible.map(skill => (
            <SkillCard
              key={skill.id}
              skill={skill}
              onToggle={handleToggle}
              onRun={handleRun}
              onDetail={onDetail}
              onHistory={onHistory}
              busy={busy}
              running={runningId === skill.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
