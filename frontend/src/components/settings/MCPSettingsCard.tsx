/**
 * MCPSettingsCard — MCP Server 设置卡片 (Sentinel V2)。
 *
 * 嵌入 SettingsPanel 抽屉中, 提供:
 * 1. 启用 toggle: PUT /api/settings/mcp/enabled
 * 2. 13 个 tool 列表 (分 5 读 + 8 写)
 * 3. 复制配置 JSON 按钮 (供 Claude Desktop / Trae / Cursor / Workbuddy 4 个 AI Agent)
 *
 * 不调 LLM, 同步直返, 全部本地 SQLite 读 mcp_tool_registry 表。
 *
 * V2 设计:
 * - st-head 头部 + st-chip 状态徽章
 * - st-rule: 启用 toggle / transport hints / 复制按钮
 * - st-section 列表展示工具, 读 / 写分类
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useEffect, useState, useCallback } from 'react';
import { Icon } from '../Icon';
import '../settings/settings-shell.css';

interface MCPTool {
  name: string;
  category: 'read' | 'write';
  description: string;
  enabled: boolean;
}

interface MCPSettingsCardProps {
  open: boolean;
}

export function MCPSettingsCard({ open }: MCPSettingsCardProps) {
  const [enabled, setEnabled] = useState(true);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [toast, setToast] = useState<string>('');

  // Load MCP status + tools on mount
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [statusRes, toolsRes] = await Promise.all([
          fetch('/api/mcp/status'),
          fetch('/api/mcp/tools'),
        ]);
        if (cancelled) return;
        if (statusRes.ok) {
          const s = await statusRes.json();
          setEnabled(Boolean(s.enabled));
        }
        if (toolsRes.ok) {
          const t = await toolsRes.json();
          setTools(t.tools || []);
        }
      } catch (err) {
        console.warn('MCPSettingsCard load failed', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Toggle handler
  const onToggle = useCallback(
    async (next: boolean) => {
      setLoading(true);
      try {
        const res = await fetch('/api/settings/mcp/enabled', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: next }),
        });
        if (res.ok) {
          setEnabled(next);
          setSaved(true);
          setTimeout(() => setSaved(false), 2000);
        }
      } catch (err) {
        console.warn('toggle failed', err);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Copy stdio config to clipboard
  const copyConfig = useCallback(async () => {
    const config = {
      mcpServers: {
        hotspot: {
          command: 'python',
          args: ['-m', 'backend.mcp_stdio_main'],
          cwd: '/Users/duke/Documents/hotspot',
        },
      },
    };
    const text = JSON.stringify(config, null, 2);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setToast('已复制 stdio 配置到剪贴板');
      } else {
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setToast('已复制 (fallback)');
      }
      setTimeout(() => setToast(''), 2500);
    } catch (err) {
      setToast('复制失败');
      setTimeout(() => setToast(''), 2500);
    }
  }, []);

  const readTools = tools.filter((t) => t.category === 'read');
  const writeTools = tools.filter((t) => t.category === 'write');

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon size={16}>
            <path d="M4 17l6-6-4-4" />
            <path d="M12 19h8" />
          </Icon>
          MCP Server
        </h2>
        <p className="st-sub2">
          暴露 5 读 + 8 写 共 13 个工具给 AI Agent (Claude Desktop / Cursor / Trae / Workbuddy).
          关闭后 AI 仍可对话, 但读不到数据库, 写不了 Wiki; 排查 AI 工具有无响应时第一检查这里.
          stdio 用于本地 IDE, sse 用于远端调用。
        </p>
        <div className="st-headops">
          <span className={`st-chip ${enabled ? 'ok' : 'mute'}`}>
            <i /> {enabled ? '已启用' : '已禁用'}
          </span>
        </div>
      </div>

      {/* 启用 toggle + 保存提示 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">启用 MCP</span>
            <div className="st-ctrl">
              <button
                role="switch"
                aria-checked={enabled}
                disabled={loading}
                className="st-switch"
                onClick={() => onToggle(!enabled)}
                style={{ width: 32, height: 16 }}
              />
              {saved && (
                <span className="st-ab-msg ok">✓ 已保存 (重启后生效)</span>
              )}
              {toast && (
                <span className="st-ab-msg mute">{toast}</span>
              )}
            </div>
          </div>

          {/* Transport hints */}
          <div className="st-rule">
            <span className="st-label">传输方式</span>
            <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
              <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                stdio: <code style={{ color: 'var(--sn-mint)' }}>python -m backend.mcp_stdio_main</code>
              </span>
              <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                sse: <code style={{ color: 'var(--sn-mint)' }}>http://127.0.0.1:8000/mcp/sse</code>
              </span>
            </div>
          </div>

          {/* Copy config */}
          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">接入配置</span>
            <div className="st-ctrl">
              <button
                className="st-btn"
                onClick={copyConfig}
                aria-label="复制 stdio 配置"
              >
                <Icon size={12}>
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </Icon>
                复制 stdio 配置 (Claude Desktop / Trae / Cursor / Workbuddy)
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tools list */}
      <div className="st-section">
        <h3 style={{ margin: '0 0 var(--sn-row) 0', fontSize: 'var(--sn-fs-h3)', color: 'var(--sn-ink)' }}>
          工具清单 · {tools.length}
        </h3>
        <div className="st-section-body" style={{ padding: 0 }}>
          <table className="st-table">
            <thead>
              <tr>
                <th style={{ width: 60 }}>类型</th>
                <th>名称</th>
                <th style={{ width: 80 }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {readTools.map(t => (
                <tr key={t.name}>
                  <td>
                    <span className="st-chip ok">
                      <i /> READ
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11 }} title={t.description}>
                    {t.name}
                  </td>
                  <td>
                    <span className={`st-chip ${t.enabled ? 'ok' : 'mute'}`}>
                      <i /> {t.enabled ? 'ON' : 'OFF'}
                    </span>
                  </td>
                </tr>
              ))}
              {writeTools.map(t => (
                <tr key={t.name}>
                  <td>
                    <span className="st-chip warn">
                      <i /> WRITE
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11 }} title={t.description}>
                    {t.name}
                  </td>
                  <td>
                    <span className={`st-chip ${t.enabled ? 'ok' : 'mute'}`}>
                      <i /> {t.enabled ? 'ON' : 'OFF'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}