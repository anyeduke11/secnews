/**
 * SkillMatrix — skill 状态矩阵 (B5.6 拆分自 Dashboard)。
 *
 * 纯展示: skill 清单表格 (空态 + 每行 id / name / type / category / enabled)。
 */
import { useI18n } from '../../contexts/I18nContext';
import type { SkillSummary } from '../../types/skill';

export function SkillMatrix({ skills }: { skills: SkillSummary[] }) {
  const { t } = useI18n();
  return (
    <section
      className="rounded-md border border-[var(--sn-line,#3a3f45)] bg-[var(--sn-bg-1,#101316)] p-4"
      data-testid="skill-matrix"
      aria-label="skill matrix"
    >
      <h2 className="text-[13px] font-medium mb-3" data-testid="skill-matrix-title">
        {t('dashboard.matrix.title', '技能状态矩阵')} · {skills.length}
      </h2>
      {skills.length === 0 ? (
        <p className="text-[12px] text-[var(--sn-ink-3,#8a929c)]" data-testid="skill-matrix-empty">
          {t('dashboard.matrix.empty', '暂无技能 (请确认 skill_registry gate 已开启)')}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]" data-testid="skill-matrix-table">
            <thead className="text-[var(--sn-ink-3,#8a929c)]">
              <tr className="border-b border-[var(--sn-line,#3a3f45)]">
                <th className="text-left py-2 pr-3 font-medium">id</th>
                <th className="text-left py-2 pr-3 font-medium">name</th>
                <th className="text-left py-2 pr-3 font-medium">type</th>
                <th className="text-left py-2 pr-3 font-medium">category</th>
                <th className="text-left py-2 font-medium">enabled</th>
              </tr>
            </thead>
            <tbody>
              {skills.map(s => (
                <tr
                  key={s.id}
                  className="border-b border-[var(--sn-line,#3a3f45)]/40"
                  data-testid={`skill-matrix-row-${s.id}`}
                >
                  <td className="py-2 pr-3 font-mono">{s.id}</td>
                  <td className="py-2 pr-3">{s.name}</td>
                  <td className="py-2 pr-3">
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-mono"
                      style={{
                        background: 'var(--sn-bg-2,#15181d)',
                        color: 'var(--sn-mint,#5fb88a)',
                      }}
                    >
                      {s.skill_type}
                    </span>
                  </td>
                  <td className="py-2 pr-3">{s.category}</td>
                  <td className="py-2" data-testid={`skill-matrix-enabled-${s.id}`}>
                    {s.enabled ? (
                      <span style={{ color: 'var(--sn-mint,#5fb88a)' }}>
                        ● {t('common.enabled', '已启用')}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--sn-ink-3,#8a929c)' }}>
                        ○ {t('common.disabled', '未启用')}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
