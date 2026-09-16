/**
 * settings/GeneralSettings — 通用设置 (主题 / 自动刷新) (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: 走 settings-shell.css 的 st-rule / st-btn / st-chip;
 *                        主题按钮改双 chip + 自动刷新按钮改 st-cellgrid
 * v0.8.5 P2 (2026-09-13): 主题升级 3 chip — 日报 (light) / 夜读 (dark) / 纸面 (paper),
 *                         onThemeChange 直接 setTheme(m), 不再走 toggle 二态循环
 */
import { useRefreshInterval } from '../../hooks/useRefreshInterval';
import type { ThemeMode } from '../../contexts/ThemeContext';

const THEME_OPTIONS: { mode: ThemeMode; label: string; aria: string }[] = [
  { mode: 'light', label: '日报版', aria: '日报版 (light)' },
  { mode: 'dark', label: '夜读版', aria: '夜读版 (dark)' },
  { mode: 'paper', label: '纸面版', aria: '纸面版 (paper)' },
];

export function GeneralSettings({
  theme,
  onThemeChange,
}: {
  theme: ThemeMode;
  onThemeChange: (mode: ThemeMode) => void;
}) {
  const { options: refreshOptions, interval: currentInterval, setInterval: setRefreshInterval } = useRefreshInterval();
  const currentLabel = refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`;

  return (
    <div className="space-y-3" data-testid="general-settings">
      <section className="st-section" aria-label="主题">
        <h3>主题</h3>
        <p className="st-section-desc">切换后立即生效, 偏好写入 localStorage `hotspot-theme`。P2 新增纸面版 (暖米黄纸底 + 衬线字体)。</p>
        <div className="st-section-body">
          <div className="st-rule">
            <div>
              <p className="st-label">当前主题</p>
              <p className="st-key">{theme === 'dark' ? 'dark mode' : theme === 'paper' ? 'paper mode' : 'light mode'}</p>
            </div>
            <div className="st-ctrl">
              <div className="st-ctrlrow" data-testid="theme-chip-group">
                {THEME_OPTIONS.map(opt => (
                  <button
                    key={opt.mode}
                    type="button"
                    className={theme === opt.mode ? 'st-btn primary' : 'st-btn'}
                    onClick={() => theme !== opt.mode && onThemeChange(opt.mode)}
                    aria-label={opt.aria}
                    aria-pressed={theme === opt.mode}
                    data-testid={`theme-${opt.mode}`}
                  >{opt.label}</button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="st-section" aria-label="自动刷新">
        <h3>自动刷新</h3>
        <p className="st-section-desc">
          控制采集面板的轮询频率; 当前 <span className="st-chip ok"><i aria-hidden />{currentLabel}</span>
        </p>
        <div className="st-cellgrid">
          {refreshOptions.map(opt => {
            const active = currentInterval === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                className={active ? 'st-btn primary' : 'st-btn'}
                onClick={() => setRefreshInterval(opt.value)}
                aria-label={opt.label}
                aria-pressed={active}
                data-testid={`refresh-${opt.value}`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}

export default GeneralSettings;