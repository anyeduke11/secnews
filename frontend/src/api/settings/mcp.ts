/**
 * api/settings/mcp.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: MCP
 */
import { apiFetch, getJSON } from '../../lib/api';

// ---------------------------------------------------------------------------
// MCP
// ---------------------------------------------------------------------------

export interface MCPTool {
  name: string;
  category: 'read' | 'write';
  description: string;
  enabled: boolean;
}

export interface MCPConfigResponse {
  stdio?: { mcpServers?: Record<string, unknown> };
  sse?: { mcpServers?: Record<string, { url?: string }> };
}

/** GET /api/mcp/status */
export function getMCPStatus(): Promise<{ enabled?: boolean }> {
  return getJSON<{ enabled?: boolean }>('/api/mcp/status');
}

/** GET /api/mcp/tools */
export function getMCPTools(): Promise<{ tools?: MCPTool[] }> {
  return getJSON<{ tools?: MCPTool[] }>('/api/mcp/tools');
}

/** GET /api/settings/mcp/config */
export function getMCPConfig(): Promise<MCPConfigResponse> {
  return getJSON<MCPConfigResponse>('/api/settings/mcp/config');
}

/** PUT /api/settings/mcp/enabled */
export function putMCPEnabled(enabled: boolean): Promise<unknown> {
  return apiFetch('/api/settings/mcp/enabled', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });
}
