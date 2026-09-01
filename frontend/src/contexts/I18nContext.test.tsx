import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { I18nProvider, useI18n } from './I18nContext';

function Probe() {
  const { locale, t, toggleLocale } = useI18n();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="t-nav">{t('nav.home')}</span>
      <span data-testid="t-obs-title">{t('observability.title')}</span>
      <span data-testid="t-missing">{t('not.exist', 'FALLBACK')}</span>
      <button data-testid="toggle" onClick={toggleLocale}>toggle</button>
    </div>
  );
}

describe('I18nContext (D6 Batch ⑧)', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('lang');
    // jsdom 默认 navigator.language 是 'en-US', 会让 initialLocale 走 en-US;
    // 测试期望 zh-CN 优先, 显式置 zh-CN
    Object.defineProperty(navigator, 'language', { value: 'zh-CN', configurable: true });
  });

  it('默认 locale 是 zh-CN, t() 返回中文', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId('locale').textContent).toBe('zh-CN');
    expect(screen.getByTestId('t-nav').textContent).toBe('首页');
    expect(screen.getByTestId('t-obs-title').textContent).toBe('观测面板 — 实时 API 健康度');
  });

  it('toggleLocale 切到 en-US, 字符串变英文, <html lang> 同步', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByTestId('toggle'));
    expect(screen.getByTestId('locale').textContent).toBe('en-US');
    expect(screen.getByTestId('t-nav').textContent).toBe('Home');
    expect(screen.getByTestId('t-obs-title').textContent).toBe('Observability — Real-time API Health');
    expect(document.documentElement.getAttribute('lang')).toBe('en-US');
  });

  it('缺失 key 走 fallback, 控制台 warn', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId('t-missing').textContent).toBe('FALLBACK');
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('localStorage 持久化: 初始 zh-CN 时重 mount 仍是 zh-CN', () => {
    const { unmount } = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByTestId('toggle')); // → en-US
    expect(localStorage.getItem('hotspot-locale')).toBe('en-US');
    unmount();
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId('locale').textContent).toBe('en-US');
  });

  it('zh-CN 存在 key 不触发 warn', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    function OnlyZh() {
      const { t } = useI18n();
      return <span data-testid="only-zh">{t('nav.home')}</span>;
    }
    render(
      <I18nProvider>
        <OnlyZh />
      </I18nProvider>,
    );
    expect(screen.getByTestId('only-zh').textContent).toBe('首页');
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
