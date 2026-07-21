// frontend/src/components/codegarden/ProjectList.test.tsx
// Phase 2a Task H2 — ProjectList 组件测试 (列表模式)
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectList } from './ProjectList';
import { CgProject, LifecycleStage } from '../../types/codegarden';

const makeProject = (over: Partial<CgProject> = {}): CgProject => ({
  id: over.id ?? 'p1',
  name: over.name ?? 'repo-a',
  display_name: over.display_name ?? over.name ?? 'Repo A',
  description: over.description ?? null,
  type: over.type ?? 'web_application',
  source_type: over.source_type ?? 'vibe',
  lifecycle_stage: over.lifecycle_stage ?? 'ideation',
  health_score: 0,
  local_path: null,
  repo_url: null,
  upstream_url: null,
  upstream_default_branch: null,
  commits_behind: over.commits_behind ?? 0,
  commits_ahead: 0,
  last_synced_at: null,
  source_item_id: null,
  source_type_detail: null,
  tags: [],
  tech_stack: over.tech_stack ?? [],
  domain: null,
  priority: 0,
  active_skill_ids: [],
  created_at: '2026-07-19T00:00:00Z',
  last_activity_at: over.last_activity_at ?? '2026-07-19T12:00:00Z',
  archived_at: null,
});

describe('ProjectList', () => {
  it('renders all items as table rows', () => {
    const items = [
      makeProject({ id: 'a', name: 'alpha' }),
      makeProject({ id: 'b', name: 'beta' }),
    ];
    render(<ProjectList items={items} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
  });

  it('renders empty placeholder when no items', () => {
    render(<ProjectList items={[]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    expect(screen.getByText('空')).toBeInTheDocument();
  });

  it('shows commits_behind only for fork projects with > 0', () => {
    const fork = makeProject({ id: 'f', source_type: 'fork', commits_behind: 7 });
    const vibe = makeProject({ id: 'v', source_type: 'vibe', commits_behind: 99 });
    render(<ProjectList items={[fork, vibe]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    expect(screen.getByText('↓7')).toBeInTheDocument();
    expect(screen.queryByText('↓99')).not.toBeInTheDocument();
  });

  it('checkbox reflects selectedIds', () => {
    const a = makeProject({ id: 'a', name: 'alpha' });
    const b = makeProject({ id: 'b', name: 'beta' });
    const selected = new Set(['a']);
    render(<ProjectList items={[a, b]} selectedIds={selected} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    const checkboxes = screen.getAllByRole('checkbox');
    // a 的 checkbox 选中
    expect((checkboxes[1] as HTMLInputElement).checked).toBe(true);
    // b 的 checkbox 未选
    expect((checkboxes[2] as HTMLInputElement).checked).toBe(false);
  });

  it('clicking checkbox calls onToggleSelect', () => {
    const a = makeProject({ id: 'a', name: 'alpha' });
    const onToggle = vi.fn();
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={onToggle} onToggleAll={vi.fn()} />);
    const cb = screen.getAllByRole('checkbox').find(c => c.getAttribute('aria-label')?.includes('alpha'))!;
    fireEvent.click(cb);
    expect(onToggle).toHaveBeenCalledWith('a');
  });

  it('clicking header checkbox calls onToggleAll', () => {
    const a = makeProject({ id: 'a', name: 'alpha' });
    const onToggleAll = vi.fn();
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={onToggleAll} />);
    const headerCb = screen.getByLabelText('全选');
    fireEvent.click(headerCb);
    expect(onToggleAll).toHaveBeenCalledOnce();
  });

  it('header checkbox is indeterminate when some items selected', () => {
    const a = makeProject({ id: 'a' });
    const b = makeProject({ id: 'b' });
    render(<ProjectList items={[a, b]} selectedIds={new Set(['a'])} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    const headerCb = screen.getByLabelText('全选') as HTMLInputElement;
    expect(headerCb.indeterminate).toBe(true);
    expect(headerCb.checked).toBe(false);
  });

  it('header checkbox is fully checked when all items selected', () => {
    const a = makeProject({ id: 'a' });
    const b = makeProject({ id: 'b' });
    render(<ProjectList items={[a, b]} selectedIds={new Set(['a', 'b'])} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    const headerCb = screen.getByLabelText('全选') as HTMLInputElement;
    expect(headerCb.checked).toBe(true);
  });

  it('clicking row calls onSelect with the project', () => {
    const a = makeProject({ id: 'a', name: 'alpha' });
    const onSelect = vi.fn();
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('alpha'));
    expect(onSelect).toHaveBeenCalledWith(a);
  });

  it('advance button calls onTransition', () => {
    const a = makeProject({ id: 'a', lifecycle_stage: 'ideation' as LifecycleStage });
    const onTransition = vi.fn();
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} onTransition={onTransition} />);
    fireEvent.click(screen.getByText(/→/));
    expect(onTransition).toHaveBeenCalledWith('a', 'prototype');
  });

  it('does not show advance button in maintenance stage', () => {
    const a = makeProject({ id: 'a', lifecycle_stage: 'maintenance' as LifecycleStage });
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} onTransition={vi.fn()} />);
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });

  it('truncates long tech_stack with ellipsis', () => {
    const a = makeProject({ id: 'a', tech_stack: ['react', 'vue', 'svelte', 'angular'] });
    render(<ProjectList items={[a]} selectedIds={new Set()} onToggleSelect={vi.fn()} onToggleAll={vi.fn()} />);
    expect(screen.getByText(/react, vue, svelte…/)).toBeInTheDocument();
  });
});
