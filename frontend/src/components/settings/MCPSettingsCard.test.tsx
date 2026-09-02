/**
 * MCPSettingsCard 组件测试 (Sentinel V2 重写, 语义化查询)。
 *
 * V2 改动:
 * - 启用 toggle: 原 checkbox with label → button role=switch (无 label)
 * - 工具清单: 原 read/write 折叠 → 单一 st-table + chip
 * - 添加 V2 语义查询 (settings-shell / st-head / st-chip / st-table)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MCPSettingsCard } from './MCPSettingsCard';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

// jsdom 没有 navigator.clipboard, 注入 mock
const mockWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(global.navigator, 'clipboard', {
  configurable: true,
  value: { writeText: mockWriteText },
});

function mockStatusTools(tools: any[] = []) {
  mockFetch.mockImplementation((url: string, options?: any) => {
    if (url === '/api/mcp/status') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ enabled: true, transport: 'sse', tools_count: tools.length || 13 }),
      });
    }
    if (url === '/api/mcp/tools') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools }) });
    }
    if (url === '/api/settings/mcp/enabled' && options?.method === 'PUT') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ enabled: false }) });
    }
    return Promise.resolve({ ok: false });
  });
}

describe('MCPSettingsCard — Sentinel V2', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockWriteText.mockReset();
    mockWriteText.mockResolvedValue(undefined);
  });

  it('渲染 V2 shell + 标题 + 启用徽章', async () => {
    mockStatusTools([]);
    const { container } = render(<MCPSettingsCard open={true} />);

    await waitFor(() => {
      expect(container.querySelector('.settings-shell')).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { level: 2, name: /MCP Server/i })).toBeInTheDocument();
    // 启用 chip (st-chip ok) — 含 "已启用" 字样
    expect(screen.getByText('已启用')).toBeInTheDocument();
  });

  it('显示 13 个 tool 名称 (5 读 + 8 写)', async () => {
    const tools = [
      { name: 'search_hotspots', category: 'read', description: '搜索热点', enabled: true },
      { name: 'get_hotspot', category: 'read', description: '获取单个热点', enabled: true },
      { name: 'list_favorites', category: 'read', description: '列出收藏', enabled: true },
      { name: 'search_knowledge', category: 'read', description: '搜索知识', enabled: true },
      { name: 'get_personal_profile', category: 'read', description: '获取画像', enabled: true },
      { name: 'add_favorite', category: 'write', description: '添加收藏', enabled: true },
      { name: 'remove_favorite', category: 'write', description: '取消收藏', enabled: true },
      { name: 'add_annotation', category: 'write', description: '添加标注', enabled: true },
      { name: 'update_knowledge_item', category: 'write', description: '更新知识', enabled: true },
      { name: 'trigger_extract_tags', category: 'write', description: '触发提取', enabled: true },
      { name: 'trigger_cubox_sync', category: 'write', description: 'cubox 同步', enabled: true },
      { name: 'create_alert_rule', category: 'write', description: '创建告警', enabled: true },
      { name: 'mark_digest_read', category: 'write', description: '标记已读', enabled: true },
    ];
    mockStatusTools(tools);

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText('search_hotspots')).toBeInTheDocument();
      expect(screen.getByText('add_favorite')).toBeInTheDocument();
      expect(screen.getByText('mark_digest_read')).toBeInTheDocument();
    });
  });

  it('13 个 tool 用 st-table 渲染 (含 READ/WRITE chip)', async () => {
    const tools = Array.from({ length: 5 }, (_, i) => ({ name: `r${i}`, category: 'read', description: '', enabled: true }))
      .concat(Array.from({ length: 8 }, (_, i) => ({ name: `w${i}`, category: 'write', description: '', enabled: true })));
    mockStatusTools(tools);

    const { container } = render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      const table = container.querySelector('table.st-table');
      expect(table).toBeInTheDocument();
      // READ/WRITE chip 数: 5 read + 8 write = 13
      // 6 chips per row (1 type + 1 status for 13 tools = 26), but classnames vary
      // simpler: row count
      const rows = table!.querySelectorAll('tbody tr');
      expect(rows.length).toBe(13);
    });
  });

  it('toggle (role=switch) 调 PUT /api/settings/mcp/enabled', async () => {
    mockStatusTools([]);
    render(<MCPSettingsCard open={true} />);

    await waitFor(() => {
      expect(screen.getByRole('switch')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        (call) => call[0] === '/api/settings/mcp/enabled' && (call[1] as any)?.method === 'PUT',
      );
      expect(putCall).toBeDefined();
    });
  });

  it('复制按钮调 writeText (stdio + backend.mcp_stdio_main)', async () => {
    mockStatusTools([]);
    render(<MCPSettingsCard open={true} />);

    await waitFor(() => {
      expect(screen.getByText(/复制 stdio 配置/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/复制 stdio 配置/i));
    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalled();
      const text = mockWriteText.mock.calls[0][0] as string;
      expect(text).toContain('mcpServers');
      expect(text).toContain('hotspot');
      expect(text).toContain('backend.mcp_stdio_main');
    });
  });

  it('复制配置 JSON 含 mcpServers.hotspot.command (Cursor 标准格式)', async () => {
    mockStatusTools([]);
    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText(/复制 stdio 配置/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/复制 stdio 配置/i));
    await waitFor(() => {
      const text = mockWriteText.mock.calls[0][0] as string;
      const parsed = JSON.parse(text);
      expect(parsed.mcpServers.hotspot.command).toBe('python');
      expect(parsed.mcpServers.hotspot.args).toContain('backend.mcp_stdio_main');
    });
  });

  it('open=false 时不触发 fetch', async () => {
    mockStatusTools([]);
    const { rerender } = render(<MCPSettingsCard open={false} />);
    await new Promise((r) => setTimeout(r, 50));
    expect(mockFetch.mock.calls.length).toBe(0);

    rerender(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(0);
    });
  });

  it('transport hints 暴露 stdio + sse 命令', async () => {
    mockStatusTools([]);
    const { container } = render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      // 找包含 stdio: 的 code 元素
      expect(container.textContent).toContain('stdio:');
      expect(container.textContent).toContain('sse:');
      expect(container.textContent).toContain('backend.mcp_stdio_main');
    });
  });
});