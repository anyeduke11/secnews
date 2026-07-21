// frontend/src/components/SkillCard.test.tsx
// Phase 6 — SkillCard 技能卡片测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SkillCard } from './SkillCard';
import type { SkillItem } from '../types';

const baseSkill: SkillItem = {
  id: 1,
  name: 'test-skill',
  source: 'npx',
  install_command: 'npx test-skill',
  description: 'a test skill',
  url: 'https://example.com/test-skill',
  tags: ['test'],
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
};

describe('SkillCard', () => {
  beforeEach(() => {
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  it('renders the skill name', () => {
    render(<SkillCard item={baseSkill} />);
    expect(screen.getByText('test-skill')).toBeInTheDocument();
  });

  it('renders the install command', () => {
    render(<SkillCard item={baseSkill} />);
    expect(screen.getByText('npx test-skill')).toBeInTheDocument();
  });

  it('renders the source label (npx)', () => {
    render(<SkillCard item={baseSkill} />);
    expect(screen.getByText('npx')).toBeInTheDocument();
  });

  it('shows install command block', () => {
    render(<SkillCard item={baseSkill} />);
    // 安装指令在 <code> 块中
    expect(screen.getByText('npx test-skill')).toBeInTheDocument();
  });

  it('clicking copy button calls clipboard.writeText', async () => {
    render(<SkillCard item={baseSkill} />);
    const copyBtn = screen.getByLabelText(/复制/);
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('npx test-skill');
    });
  });

  it('copy button shows success state after copy', async () => {
    render(<SkillCard item={baseSkill} />);
    const copyBtn = screen.getByLabelText(/复制/);
    fireEvent.click(copyBtn);
    // 等待状态更新
    await waitFor(() => {
      expect(copyBtn.textContent).toMatch(/已复制/);
    });
  });

  it('edit button calls onEdit with the item', () => {
    const onEdit = vi.fn();
    render(<SkillCard item={baseSkill} onEdit={onEdit} />);
    const editBtn = screen.getByLabelText('编辑');
    fireEvent.click(editBtn);
    expect(onEdit).toHaveBeenCalledWith(baseSkill);
  });

  it('delete button calls onDelete with the id', () => {
    const onDelete = vi.fn();
    // mock confirm 让删除确认通过
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<SkillCard item={baseSkill} onDelete={onDelete} />);
    const deleteBtn = screen.getByLabelText('删除');
    fireEvent.click(deleteBtn);
    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it('edit and delete buttons are absent when callbacks are undefined', () => {
    render(<SkillCard item={baseSkill} />);
    // 没有 onEdit/onDelete 时不渲染编辑/删除按钮
    expect(screen.queryByLabelText('编辑')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('删除')).not.toBeInTheDocument();
  });

  it('different source renders different label (git)', () => {
    const gitSkill = { ...baseSkill, source: 'git' as const, install_command: 'git clone x' };
    render(<SkillCard item={gitSkill} />);
    expect(screen.getByText('git')).toBeInTheDocument();
  });
});
