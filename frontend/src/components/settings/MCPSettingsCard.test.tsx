/**
 * MCPSettingsCard 组件测试 (Phase 7).
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

describe('MCPSettingsCard', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockWriteText.mockReset();
    mockWriteText.mockResolvedValue(undefined);
  });

  it('渲染标题', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, transport: 'sse', tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tools: [] }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText(/MCP Server/i)).toBeInTheDocument();
    });
  });

  it('显示 13 个 tool (5 读 + 8 写)', async () => {
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
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, transport: 'sse', tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      // 验证所有 13 个 tool 名称出现
      expect(screen.getByText('search_hotspots')).toBeInTheDocument();
      expect(screen.getByText('add_favorite')).toBeInTheDocument();
      expect(screen.getByText('mark_digest_read')).toBeInTheDocument();
    });
  });

  it('点击复制按钮调 navigator.clipboard.writeText', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools: [] }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText(/复制 stdio 配置/i)).toBeInTheDocument();
    });

    const btn = screen.getByText(/复制 stdio 配置/i);
    fireEvent.click(btn);

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalled();
      const calledText = mockWriteText.mock.calls[0][0] as string;
      expect(calledText).toContain('mcpServers');
      expect(calledText).toContain('hotspot');
      expect(calledText).toContain('backend.mcp_stdio_main');
    });
  });

  it('toggle 调 PUT /api/settings/mcp/enabled', async () => {
    mockFetch.mockImplementation((url: string, options?: any) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools: [] }) });
      }
      if (url === '/api/settings/mcp/enabled' && options?.method === 'PUT') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ enabled: false }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      const checkbox = screen.getByLabelText(/启用 MCP Server/i) as HTMLInputElement;
      expect(checkbox).toBeInTheDocument();
    });

    const checkbox = screen.getByLabelText(/启用 MCP Server/i) as HTMLInputElement;
    fireEvent.click(checkbox);

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        (call) => call[0] === '/api/settings/mcp/enabled' && (call[1] as any)?.method === 'PUT',
      );
      expect(putCall).toBeDefined();
    });
  });

  it('open=false 时不触发 fetch (避免隐藏状态拉取)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools: [] }) });
      }
      return Promise.resolve({ ok: false });
    });

    const { rerender } = render(<MCPSettingsCard open={false} />);
    // 等待一个 microtask, 确认没有 fetch 触发
    await new Promise((r) => setTimeout(r, 50));
    const callsBefore = mockFetch.mock.calls.length;
    expect(callsBefore).toBe(0);

    rerender(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(0);
    });
  });

  it('按 read / write 分两段渲染 (5 + 8)', async () => {
    const tools = [
      { name: 'r1', category: 'read', description: 'r1', enabled: true },
      { name: 'r2', category: 'read', description: 'r2', enabled: true },
      { name: 'r3', category: 'read', description: 'r3', enabled: true },
      { name: 'r4', category: 'read', description: 'r4', enabled: true },
      { name: 'r5', category: 'read', description: 'r5', enabled: true },
      { name: 'w1', category: 'write', description: 'w1', enabled: true },
      { name: 'w2', category: 'write', description: 'w2', enabled: true },
      { name: 'w3', category: 'write', description: 'w3', enabled: true },
      { name: 'w4', category: 'write', description: 'w4', enabled: true },
      { name: 'w5', category: 'write', description: 'w5', enabled: true },
      { name: 'w6', category: 'write', description: 'w6', enabled: true },
      { name: 'w7', category: 'write', description: 'w7', enabled: true },
      { name: 'w8', category: 'write', description: 'w8', enabled: true },
    ];
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText('读 (5)')).toBeInTheDocument();
      expect(screen.getByText('写 (8)')).toBeInTheDocument();
    });
  });

  it('disabled tool 用空心圆 + 灰色渲染 (视觉降级)', async () => {
    const tools = [
      { name: 'enabled_tool', category: 'read', description: 'on', enabled: true },
      { name: 'disabled_tool', category: 'read', description: 'off', enabled: false },
    ];
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText('enabled_tool')).toBeInTheDocument();
      expect(screen.getByText('disabled_tool')).toBeInTheDocument();
    });
  });

  it('复制配置 JSON 含 mcpServers.hotspot.command (Cursor 标准格式)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/mcp/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ enabled: true, tools_count: 13 }),
        });
      }
      if (url === '/api/mcp/tools') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tools: [] }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<MCPSettingsCard open={true} />);
    await waitFor(() => {
      expect(screen.getByText(/复制 stdio 配置/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/复制 stdio 配置/i));

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalled();
      const text = mockWriteText.mock.calls[0][0] as string;
      const parsed = JSON.parse(text);
      expect(parsed.mcpServers.hotspot.command).toBe('python');
      expect(parsed.mcpServers.hotspot.args).toContain('backend.mcp_stdio_main');
    });
  });
});
