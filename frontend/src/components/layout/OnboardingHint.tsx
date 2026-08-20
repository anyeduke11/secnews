/**
 * OnboardingHint — 轻量级首次使用引导 (v1)
 *
 * 设计原则:
 * - 零依赖 (不引入 react-joyride 等)
 * - localStorage 记忆已读状态
 * - 只在首次访问对应认知模式时显示一次
 * - 可手动重新触发 (清 localStorage)
 *
 * 用法:
 *   <OnboardingHint storageKey="kb-briefing" title="简报模式">
 *     <p>这是简报模式的说明...</p>
 *   </OnboardingHint>
 */
import React, { useState, useEffect } from 'react';

interface OnboardingHintProps {
  storageKey: string;
  title: string;
  children: React.ReactNode;
  /** 显示位置 (默认顶部) */
  position?: 'top' | 'bottom';
}

export function OnboardingHint({
  storageKey,
  title,
  children,
  position = 'top',
}: OnboardingHintProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const seen = localStorage.getItem(`onboarding:${storageKey}`);
    if (!seen) setVisible(true);
  }, [storageKey]);

  const dismiss = () => {
    localStorage.setItem(`onboarding:${storageKey}`, '1');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="region"
      aria-label={`引导: ${title}`}
      className="onboarding-hint"
      style={{
        position: 'relative',
        margin: position === 'top' ? '0 0 12px 0' : '12px 0 0 0',
        padding: '12px 16px',
        backgroundColor: 'color-mix(in srgb, var(--accent) 8%, var(--bg-elevated))',
        border: '1px solid var(--accent-dim, var(--accent))',
        borderRadius: 'var(--radius-md)',
        boxShadow: '0 0 0 3px color-mix(in srgb, var(--accent) 6%, transparent)',
      }}
    >
      <div className="flex items-start gap-3">
        <span
          className="shrink-0 text-xs font-mono font-bold"
          style={{ color: 'var(--accent)' }}
        >
          ✦
        </span>
        <div className="flex-1">
          <h4
            className="text-xs font-bold uppercase tracking-[0.08em] mb-1"
            style={{ color: 'var(--accent)' }}
          >
            {title}
          </h4>
          <div
            className="text-[12px] leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}
          >
            {children}
          </div>
        </div>
        <button
          onClick={dismiss}
          className="shrink-0 btn-ghost"
          style={{ minHeight: 'auto', padding: '2px 8px' }}
          aria-label="关闭引导"
        >
          知道了
        </button>
      </div>
    </div>
  );
}

/** 重置所有 onboarding 记忆 (开发用) */
export function resetOnboarding() {
  Object.keys(localStorage)
    .filter((k) => k.startsWith('onboarding:'))
    .forEach((k) => localStorage.removeItem(k));
}
