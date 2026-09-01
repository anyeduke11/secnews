/**
 * SecNewsHeader — 看板页头组件
 *
 * 显示标题 + 当前日期 + 刷新按钮。
 * v0.7 Batch ⑨ B9-1: 接入 i18n (nav.refresh / nav.refreshing), 日期 locale 跟随
 */
import { useI18n } from '../../../contexts/I18nContext';

interface SecNewsHeaderProps {
  title?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function SecNewsHeader({ title = '安全看板', onRefresh, refreshing }: SecNewsHeaderProps) {
  const { locale, t } = useI18n();
  // locale=en-US 时浏览器输出 "Monday, September 1, 2026" 风格
  const dateLocale = locale === 'en-US' ? 'en-US' : 'zh-CN';
  const today = new Date().toLocaleDateString(dateLocale, {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  return (
    <header className="flex items-center justify-between mb-4">
      <div>
        <h1 className="text-lg font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{today}</p>
      </div>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          aria-label={t('nav.refresh')}
          className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
        >
          {refreshing ? t('nav.refreshing') : t('nav.refresh')}
        </button>
      )}
    </header>
  );
}
