/**
 * RotationBanner — Secrets 主密钥轮换提醒条 (v0.7 Batch ⑨ B9-2)
 *
 * 显示在 SecretsPage 顶部: 当 /api/secrets/rotation-status 返 should_rotate=true
 * 时, 警告用户主密钥已超期 (默认 90 天), 提示通过 /api/secrets/rotate 轮换。
 * 数据轮询 24h 一次 (因 scheduler 每日 09:00 检查, 不用 polling 监控实时变化)。
 */
import { useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';

interface RotationStatus {
  setup: boolean;
  last_rotated_at: string | null;
  age_days: number | null;
  should_rotate: boolean;
  remind_days: number;
}

export function RotationBanner() {
  const { t } = useI18n();
  const [status, setStatus] = useState<RotationStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const r = await fetch('/api/secrets/rotation-status');
        if (!r.ok) return;
        const d: RotationStatus = await r.json();
        if (!cancelled) setStatus(d);
      } catch { /* silent */ }
    };
    fetchStatus();
    // 24h 轮询 (scheduler 每日 09:00 检查, 不需高频)
    const timer = window.setInterval(fetchStatus, 24 * 60 * 60 * 1000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  if (!status?.setup || !status.should_rotate) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="px-3 py-2 rounded text-xs font-mono flex items-center justify-between gap-2"
      style={{
        backgroundColor: 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
        border: '1px solid var(--color-warning)',
        color: 'var(--text-primary)',
      }}
    >
      <span>
        ⚠ {t('rotation_banner.title', { age: status.age_days ?? '?', remind: status.remind_days })}
      </span>
      <a
        href="https://github.com/anyeduke11/secnews#secrets-rotation"
        target="_blank"
        rel="noopener noreferrer"
        className="underline shrink-0"
        style={{ color: 'var(--color-warning)' }}
      >
        {t('rotation_banner.howto')}
      </a>
    </div>
  );
}
