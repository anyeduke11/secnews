// frontend/src/components/codegarden/ProjectCard.test.tsx
// Phase 2a Task H2 — ProjectCard 组件测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectCard } from './ProjectCard';
import { CgProject, LifecycleStage } from '../../types/codegarden';

const baseProject: CgProject = {
  id: 'p1',
  name: 'test-repo',
  display_name: 'Test Repo',
  description: 'A test project',
  type: 'web_application',
  source_type: 'fork',
  lifecycle_stage: 'development',
  health_score: 75,
  local_path: null,
  repo_url: 'https://github.com/owner/test-repo',
  upstream_url: 'https://github.com/upstream/test-repo',
  upstream_default_branch: 'main',
  commits_behind: 5,
  commits_ahead: 2,
  last_synced_at: null,
  source_item_id: null,
  source_type_detail: 'trending',
  tags: ['tool'],
  tech_stack: ['Python'],
  domain: 'security',
  priority: 1,
  active_skill_ids: [],
  created_at: '2026-07-19T00:00:00Z',
  last_activity_at: null,
  archived_at: null,
};

describe('ProjectCard', () => {
  it('renders project display_name', () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText('Test Repo')).toBeInTheDocument();
  });

  it('renders fork source type label', () => {
    render(<ProjectCard project={baseProject} />);
    // SOURCE_TYPE_LABELS['fork'] = 'Fork'
    expect(screen.getByText('Fork')).toBeInTheDocument();
  });

  it('renders commits_behind badge when > 0 and source_type=fork', () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText('↓5')).toBeInTheDocument();
  });

  it('hides commits_behind badge when source_type != fork', () => {
    const p = { ...baseProject, source_type: 'vibe' as const };
    render(<ProjectCard project={p} />);
    expect(screen.queryByText('↓5')).not.toBeInTheDocument();
  });

  it('calls onClick when card is clicked', () => {
    const onClick = vi.fn();
    render(<ProjectCard project={baseProject} onClick={onClick} />);
    fireEvent.click(screen.getByText('Test Repo'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('calls onTransition when advance button is clicked', () => {
    const onTransition = vi.fn();
    render(<ProjectCard project={baseProject} onTransition={onTransition} />);
    // 实际渲染: "→ 测试中" (development → testing)
    const btn = screen.getByText(/→/);
    fireEvent.click(btn);
    expect(onTransition).toHaveBeenCalledWith('p1', 'testing');
  });

  it('does not render advance button when in maintenance stage', () => {
    // maintenance 无下一阶段 (NEXT_STAGE 表中未定义)
    const p = { ...baseProject, lifecycle_stage: 'maintenance' as LifecycleStage };
    render(<ProjectCard project={p} onTransition={vi.fn()} />);
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });

  it('renders health_score when > 0', () => {
    render(<ProjectCard project={baseProject} />);
    // 实际渲染: "❤ 75"
    expect(screen.getByText(/75/)).toBeInTheDocument();
  });
});
