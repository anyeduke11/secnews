/**
 * DigestCard — 官方每日简报卡 (workbench/BriefingView 并入 SecNews feed)
 *
 * 数据源: GET /api/digests/latest · POST /api/digests/generate · PUT /api/digests/read
 * 反馈契约: 生成中禁用按钮 + error 显式呈现 (不再静默)。
 * v0.7 Batch ⑨ B9-1: 接入 i18n (feed.digest.*)
 */
import { useDigest } from '../../../hooks/useDigest';
import { useI18n } from '../../../contexts/I18nContext';

export function DigestCard() {
  const { t } = useI18n();
  const { digest, loading, error, generate, markRead } = useDigest();

  const handleGenerate = async () => {
    const d = await generate();
    if (d) await markRead();
  };

  return (
    <section
      className="p-3 rounded-[var(--radius-sm)]"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: '3px solid var(--accent)',
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('feed.digest_title')}
        </h3>
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="btn-secondary text-[10px] px-2 py-0.5"
        >
          {loading ? t('feed.digest_generating') : t('feed.digest_generate')}
        </button>
      </div>
      {error && (
        <p className="text-[10px] font-mono mb-1" style={{ color: 'var(--color-error)' }} role="alert">
          {error}
        </p>
      )}
      {digest ? (
        <div className="text-[11px] font-mono space-y-1">
          <div style={{ color: 'var(--text-muted)' }}>{digest.period} · {digest.created_at}</div>
          {!digest.summary_md && (
            <p className="text-[10px]" style={{ color: 'var(--color-warning)' }}>
              {t('feed.digest_no_llm')}
            </p>
          )}
          <pre className="whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
            {digest.summary_md || digest.summary}
          </pre>
          <div style={{ color: 'var(--text-muted)' }}>
            {t('feed.digest_related', { n: digest.item_ids?.length ?? digest.count ?? 0 })}
          </div>
        </div>
      ) : (
        !error && (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {t('feed.digest_empty')}
          </p>
        )
      )}
    </section>
  );
}
