// frontend/src/components/shared/TagSelector.test.tsx
// v1.7 Phase 1 — TagSelector 组件测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TagSelector } from './TagSelector';

// Mock /api/tags list + suggest
const tagList = [
  { id: 'cve', label: 'CVE', type: 'cve', parent_id: null, weight: 1.0, created_at: '' },
  { id: 'ai-security', label: 'AI Security', type: 'domain', parent_id: null, weight: 1.0, created_at: '' },
  { id: 'llm', label: 'LLM', type: 'domain', parent_id: null, weight: 1.0, created_at: '' },
];

describe('TagSelector', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      const body = u.includes('/suggest')
        ? { items: tagList.filter((t) => t.id.startsWith('cve')) }
        : { items: tagList };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as any;
  });

  it('renders tags from API', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={[]} mode="or" onChange={onChange} />);
    await waitFor(() => {
      expect(screen.getByText('CVE')).toBeInTheDocument();
      expect(screen.getByText('LLM')).toBeInTheDocument();
    });
  });

  it('toggles a tag on click and calls onChange', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={[]} mode="or" onChange={onChange} />);
    await waitFor(() => expect(screen.getByText('CVE')).toBeInTheDocument());
    fireEvent.click(screen.getByText('CVE'));
    expect(onChange).toHaveBeenCalledWith(['cve'], 'or');
  });

  it('deselects an already-selected tag', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={['cve']} mode="or" onChange={onChange} />);
    await waitFor(() => expect(screen.getByText('CVE')).toBeInTheDocument());
    fireEvent.click(screen.getByText('CVE'));
    expect(onChange).toHaveBeenCalledWith([], 'or');
  });

  it('switches mode from OR to AND (验收 2)', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={['cve']} mode="or" onChange={onChange} />);
    await waitFor(() => expect(screen.getByText('AND')).toBeInTheDocument());
    fireEvent.click(screen.getByText('AND'));
    expect(onChange).toHaveBeenCalledWith(['cve'], 'and');
  });

  it('shows clear button when tags selected and clears all', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={['cve', 'llm']} mode="and" onChange={onChange} />);
    await waitFor(() => expect(screen.getByText(/已选 2 个/)).toBeInTheDocument());
    fireEvent.click(screen.getByText('清除'));
    expect(onChange).toHaveBeenCalledWith([], 'and');
  });

  it('does not call onChange when clicking active mode button (no-op)', async () => {
    const onChange = vi.fn();
    render(<TagSelector selected={[]} mode="or" onChange={onChange} />);
    await waitFor(() => expect(screen.getByText('OR')).toBeInTheDocument());
    fireEvent.click(screen.getByText('OR'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
