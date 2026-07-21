// frontend/src/components/KnowledgeFilters.test.tsx
// Phase 6 — KnowledgeFilters 知识过滤测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { KnowledgeFilters } from './KnowledgeFilters';

describe('KnowledgeFilters', () => {
  beforeEach(() => {
    // Mock fetch with sensible defaults
    global.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve({ topics: [] }),
      })
    ) as any;
  });

  it('renders 5 filter selects', () => {
    render(<KnowledgeFilters onFilterChange={vi.fn()} />);
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBe(5);
  });

  it('domain select has security option', () => {
    render(<KnowledgeFilters onFilterChange={vi.fn()} />);
    const domainSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement;
    expect(domainSelect.querySelector('option[value="security"]')).toBeInTheDocument();
  });

  it('changing domain calls onFilterChange with the value', async () => {
    const onFilterChange = vi.fn();
    render(<KnowledgeFilters onFilterChange={onFilterChange} />);
    const domainSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(domainSelect, { target: { value: 'ai' } });

    await waitFor(() => {
      expect(onFilterChange).toHaveBeenCalledWith(
        expect.objectContaining({ domain: 'ai', topic: '' })
      );
    });
  });

  it('changing domain resets topic to empty', async () => {
    const onFilterChange = vi.fn();
    render(<KnowledgeFilters onFilterChange={onFilterChange} />);
    const selects = screen.getAllByRole('combobox');
    const domainSelect = selects[0];

    fireEvent.change(domainSelect, { target: { value: 'ai' } });
    await waitFor(() => {
      const lastCall = onFilterChange.mock.calls[onFilterChange.mock.calls.length - 1][0];
      expect(lastCall.topic).toBe('');
    });
  });

  it('topic select is disabled when no topics loaded', () => {
    render(<KnowledgeFilters onFilterChange={vi.fn()} />);
    const topicSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    expect(topicSelect).toBeDisabled();
  });

  it('topic select is enabled after topics loaded', async () => {
    (global.fetch as any) = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve({ topics: ['llm', 'agent'] }),
      })
    );
    render(<KnowledgeFilters onFilterChange={vi.fn()} />);
    const domainSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(domainSelect, { target: { value: 'ai' } });

    await waitFor(() => {
      const topicSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
      expect(topicSelect).not.toBeDisabled();
    });
  });

  it('timeRange default is all', () => {
    const onFilterChange = vi.fn();
    render(<KnowledgeFilters onFilterChange={onFilterChange} />);
    // First call to onFilterChange happens on mount
    const initial = onFilterChange.mock.calls[0][0];
    expect(initial.timeRange).toBe('all');
  });

  it('changing timeRange to week updates filter', () => {
    const onFilterChange = vi.fn();
    render(<KnowledgeFilters onFilterChange={onFilterChange} />);
    const selects = screen.getAllByRole('combobox');
    const timeSelect = selects[4];
    fireEvent.change(timeSelect, { target: { value: 'week' } });

    const lastCall = onFilterChange.mock.calls[onFilterChange.mock.calls.length - 1][0];
    expect(lastCall.timeRange).toBe('week');
  });
});
