/**
 * settings/GeneralSettings — 通用设置 (主题 / 自动刷新) (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: 走 settings-shell.css 的 st-rule / st-btn / st-chip;
 *                        主题按钮改双 chip + 自动刷新按钮改 st-cellgrid
 */
import { useRefreshInterval } from '../../hooks/useRefreshInterval';

export function GeneralSettings({ onThemeToggle, theme }: { onThemeToggle: () => void; theme: 'dark' | 'light' }) {
  const { options: refreshOptions, interval: currentInterval, setInterval: setRefreshInterval } = useRefreshInterval();
  const currentLabel = refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`;

  return (
    <div className="space-y-3" data-testid="general-settings">
      <section className="st-section" aria-label="主题">
        <h3>主题</h3>
        <p className="st-section-desc">切换后立即生效, 偏好写入 localStorage `hotspot-theme`。</p>
        <div className="st-section-body">
          <div className="st-rule">
            <div>
              <p className="st-label">当前主题</p>
              <p className="st-key">{theme === 'dark' ? 'dark mode' : 'light mode'}</p>
            </div>
            <div className="st-ctrl">
              <div className="st-ctrlrow">
                <button
                  type="button"
                  className={theme === 'light' ? 'st-btn primary' : 'st-btn'}
                  onClick={() => theme === 'dark' && onThemeToggle()}
                  aria-label="日报版 (light)"
                >日报版</button>
                <button
                  type="button"
                  className={theme === 'dark' ? 'st-btn primary' : 'st-btn'}
                  onClick={() => theme === 'light' && onThemeToggle()}
                  aria-label="夜读版 (dark)"
                >夜读版</button>
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