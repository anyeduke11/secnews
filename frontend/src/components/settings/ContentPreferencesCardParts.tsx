/**
 * settings/ContentPreferencesCardParts — ContentPreferencesCard 的私有子组件与常量。
 *
 * 从 ContentPreferencesCard.tsx 纯搬运 (拆分批次 B6-b, 单文件 ≤300 行):
 * 三级分段控件 LevelPicker、自动学习只读 chips 组 AutoChips,
 * 以及 LEVELS / VISIBLE_SOURCES / labelOfCategory。语义与 DOM 与拆分前一致。
 */
import { useI18n } from '../../contexts/I18nContext';
import type {
  ContentPrefLevel as Level,
  ContentPrefTable as PrefTable,
} from '../../api/settings';
import { CATEGORIES } from '../../types';

export const LEVELS: Level[] = ['more', 'normal', 'less'];
export const VISIBLE_SOURCES = 40;

export const labelOfCategory = (id: string) => CATEGORIES.find((c) => c.id === id)?.label ?? id;

/** 三级分段控件: 加强 / 默认 / 减弱 (默认态 = 不存, 交还自动)。 */
export function LevelPicker({
  name, value, onChange, disabled,
}: {
  name: string; value: Level; onChange: (lv: Level) => void; disabled: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      role="group"
      aria-label={t('settings.content_prefs.level_of', { name })}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}
    >
      {LEVELS.map((lv) => {
        const active = value === lv;
        const lessActive = active && lv === 'less';
        return (
          <button
            key={lv}
            type="button"
            className={`st-btn${active ? ' primary' : ''}`}
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(lv)}
            style={lessActive
              ? { background: 'var(--sn-cat-sec, #d4574e)', borderColor: 'var(--sn-cat-sec, #d4574e)' }
              : undefined}
          >
            {t(`settings.content_prefs.levels.${lv}`)}
          </button>
        );
      })}
    </div>
  );
}

/** 自动学习 chips 组 (只读): more=绿 / less=红。 */
export function AutoChips({ table }: { table: PrefTable }) {
  const { t } = useI18n();
  return (
    <span className="flex items-center gap-2" style={{ flexWrap: 'wrap', gap: 6 }}>
      {Object.entries(table).map(([key, lv]) => (
        <span
          key={key}
          className="st-chip"
          style={lv === 'less'
            ? { color: 'var(--sn-cat-sec, #d4574e)', borderColor: 'currentColor' }
            : { color: 'var(--sn-mint, #00e5a0)', borderColor: 'currentColor' }}
          title={t('settings.content_prefs.auto_chip_title')}
        >
          <i aria-hidden />{labelOfCategory(key) || key}
          {' · '}{t(`settings.content_prefs.levels.${lv}`)}
        </span>
      ))}
    </span>
  );
}