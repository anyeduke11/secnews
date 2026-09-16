import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EditorialCard } from './EditorialCard';

describe('EditorialCard', () => {
  it('renders children', () => {
    render(<EditorialCard>content</EditorialCard>);
    expect(screen.getByText('content')).toBeDefined();
  });

  it('applies card class and base styles', () => {
    const { container } = render(<EditorialCard />);
    const el = container.firstElementChild as HTMLElement | undefined;
    expect(el?.className).toContain('card');
  });

  it('calls onClick when clicked', () => {
    const fn = vi.fn();
    render(<EditorialCard onClick={fn}>clickable</EditorialCard>);
    fireEvent.click(screen.getByText('clickable'));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
