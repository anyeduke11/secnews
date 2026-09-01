import { useI18n } from '../contexts/I18nContext';

/**
 * v0.7 Batch ⑧ D6: 中英文切换按钮 — 出现在 Settings/Topbar 区域.
 * a11y: aria-label 双语, 切换后立即更新.
 */
export function LocaleToggle({ className }: { className?: string }) {
  const { locale, toggleLocale } = useI18n();
  const label = locale === 'zh-CN' ? 'Switch to English' : '切换到中文';
  const text = locale === 'zh-CN' ? 'EN' : '中';

  return (
    <button
      type="button"
      onClick={toggleLocale}
      className={className ?? 'px-2 py-1 text-xs font-mono rounded border border-current opacity-70 hover:opacity-100'}
      aria-label={label}
      title={label}
      data-testid="locale-toggle"
    >
      {text}
    </button>
  );
}
