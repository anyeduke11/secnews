/**
 * MCPSettingsCard — MCP Server 设置卡片 (Phase 7).
 *
 * 嵌入 SettingsPanel 抽屉中, 提供:
 * 1. 启用 toggle: PUT /api/settings/mcp/enabled
 * 2. 13 个 tool 列表 (分 5 读 + 8 写)
 * 3. 复制配置 JSON 按钮 (供 Claude Desktop / Trae / Cursor / Workbuddy 4 个 AI Agent)
 *
 * 不调 LLM, 同步直返, 全部本地 SQLite 读 mcp_tool_registry 表。
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Icon } from '../Icon';

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
    <div
      className="rounded-md p-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3
          className="text-xs font-bold flex items-center gap-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <Icon size={14}>
            <path d="M4 17l6-6-4-4" />
            <path d="M12 19h8" />
          </Icon>
          MCP Server
          <span
            className="text-[10px] font-normal px-1.5 py-0.5 rounded"
            style={{
              background: enabled
                ? 'color-mix(in srgb, var(--color-success) 9%, transparent)'
                : 'color-mix(in srgb, var(--text-muted) 9%, transparent)',
              color: enabled ? 'var(--color-success)' : 'var(--text-muted)',
            }}
          >
            {enabled ? '已启用' : '已禁用'}
          </span>
        </h3>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            disabled={loading}
            onChange={(e) => onToggle(e.target.checked)}
            className="w-3.5 h-3.5"
            aria-label="启用 MCP Server"
          />
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            启用
          </span>
        </label>
      </div>

      {saved && (
        <div
          className="text-[10px] mb-2 px-2 py-1 rounded"
          style={{ background: 'color-mix(in srgb, var(--color-success) 8%, transparent)', color: 'var(--color-success)' }}
        >
          ✓ 已保存 (重启后生效)
        </div>
      )}

      {toast && (
        <div
          className="text-[10px] mb-2 px-2 py-1 rounded"
          style={{ background: 'color-mix(in srgb, var(--color-info) 8%, transparent)', color: 'var(--color-info)' }}
        >
          {toast}
        </div>
      )}

      {/* Transport hint */}
      <div
        className="text-[10px] mb-2 px-2 py-1.5 rounded font-mono"
        style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}
      >
        <div>stdio: <code>python -m backend.mcp_stdio_main</code></div>
        <div>sse: <code>http://127.0.0.1:8000/mcp/sse</code></div>
      </div>

      {/* Copy config button */}
      <button
        onClick={copyConfig}
        className="btn-ghost w-full text-[11px] py-1.5 mb-2 flex items-center justify-center gap-1.5"
        aria-label="复制 stdio 配置"
      >
        <Icon size={12}>
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </Icon>
        复制 stdio 配置 (Claude Desktop / Trae / Cursor / Workbuddy)
      </button>

      {/* Tools list */}
      <div className="text-[10px] space-y-1">
        <div
          className="font-semibold mt-2 mb-1"
          style={{ color: 'var(--text-muted)' }}
        >
          读 ({readTools.length})
        </div>
        {readTools.map((t) => (
          <ToolRow key={t.name} tool={t} />
        ))}
        <div
          className="font-semibold mt-2 mb-1"
          style={{ color: 'var(--text-muted)' }}
        >
          写 ({writeTools.length})
        </div>
        {writeTools.map((t) => (
          <ToolRow key={t.name} tool={t} />
        ))}
      </div>
    </div>
  );
}

function ToolRow({ tool }: { tool: MCPTool }) {
  return (
    <div
      className="flex items-start gap-1.5 px-1.5 py-1 rounded font-mono"
      style={{ background: 'var(--bg-muted)' }}
      title={tool.description}
    >
      <span
        className="text-[10px] flex-shrink-0"
        style={{
          color: tool.enabled ? 'var(--color-ai)' : 'var(--text-muted)',
        }}
      >
        {tool.enabled ? '●' : '○'}
      </span>
      <span
        className="text-[10px] break-all"
        style={{ color: 'var(--text-primary)' }}
      >
        {tool.name}
      </span>
    </div>
  );
}
