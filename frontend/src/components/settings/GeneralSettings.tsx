/**
 * settings/GeneralSettings — 通用设置 (主题 / 自动刷新)。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 GeneralSettings (~100-199 行)。
 * 纯结构拆分: 状态 (useRefreshInterval) 与渲染逻辑逐字迁移。
 */
import { useRefreshInterval } from '../../hooks/useRefreshInterval';

export function GeneralSettings({ onThemeToggle, theme }: { onThemeToggle: () => void; theme: 'dark' | 'light' }) {
  const { options: refreshOptions, interval: currentInterval, setInterval: setRefreshInterval } = useRefreshInterval();

  return (
    <div className="space-y-2">
      {/* 主题切换 */}
      <div className="card-base">
        <div className="flex items-center justify-between px-2.5 py-1.5">
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>主题</span>
          <div className="flex gap-1">
            <button
              onClick={() => theme === 'dark' && onThemeToggle()}
              className="px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: theme === 'light' ? 'var(--accent)' : 'var(--bg-hover)',
                color: theme === 'light' ? 'var(--text-on-color)' : 'var(--text-secondary)',
                border: `1px solid ${theme === 'light' ? 'var(--accent)' : 'var(--border-color)'}`,
              }}
            >
              日报版
            </button>
            <button
              onClick={() => theme === 'light' && onThemeToggle()}
              className="px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: theme === 'dark' ? 'var(--accent)' : 'var(--bg-hover)',
                color: theme === 'dark' ? 'var(--text-on-color)' : 'var(--text-secondary)',
                border: `1px solid ${theme === 'dark' ? 'var(--accent)' : 'var(--border-color)'}`,
              }}
            >
              夜读版
            </button>
          </div>
        </div>
      </div>

      {/* 自动刷新 */}
      <div className="card-base">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>自动刷新</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
              当前: {refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {refreshOptions.map(opt => {
              const active = currentInterval === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setRefreshInterval(opt.value)}
                  className="px-2 py-0.5 text-[9px] font-medium rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                    color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-color)'}`,
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* 自动刷新 */}
      <div className="card-base">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>自动刷新</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
              当前: {refreshOptions.find(o => o.value === currentInterval)?.label || `${currentInterval} 分钟`}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {refreshOptions.map(opt => {
              const active = currentInterval === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setRefreshInterval(opt.value)}
                  className="px-2 py-0.5 text-[9px] font-medium rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                    color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-color)'}`,
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
