/**
 * FeatureGatesCard — 能力开关卡测试
 * 意图: 16 gate 从 /api/settings/features 只读呈现 (P1); P2 的 PUT 端点就绪后接通 toggle。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { FeatureGatesCard } from './FeatureGatesCard';

const FEATURES = {
  codegarden: true, codegarden_phase2b: true, sync: true, tech_stack: true,
  security_graph: true, secnews: true, dsh: true, info_filter: true,
  skill_registry: true, trigger_gate: true, user_skills: true,
  interest_engine: true, semantic_filter: true, ai_classify: true,
  pipeline_ner: true, mcp: false,
};

describe('FeatureGatesCard — 能力开关 (只读期)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/settings/features')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(FEATURES) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染 16 个 gate 与启停状态, mcp=false 显示 OFF', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => expect(screen.getByText('能力开关')).toBeInTheDocument());
    expect(screen.getByText('secnews')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('mcp')).toBeInTheDocument());
    await waitFor(() => {
      const rows = screen.getAllByRole('switch');
      expect(rows).toHaveLength(16);
    });
  });

  it('P1 阶段开关为只读 (disabled), 提示来源', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => {
      const sw = screen.getAllByRole('switch')[0] as HTMLButtonElement;
      expect(sw.disabled).toBe(true);
    });
    expect(screen.getByText(/feature_gates\.toml/)).toBeInTheDocument();
  });
});
