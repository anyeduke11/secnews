import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BandNav } from './BandNav';

describe('BandNav', () => {
  it('renders items', () => {
    render(<BandNav items={[{ label: 'A' }, { label: 'B' }]} />);
    expect(screen.getByText('A')).toBeDefined();
    expect(screen.getByText('B')).toBeDefined();
  });

  it('applies bandnav class', () => {
    const { container } = render(<BandNav items={[{ label: 'A' }]} />);
    const el = container.firstElementChild as HTMLElement | undefined;
    expect(el?.className).toContain('bandnav');
  });

  it('calls onClick for action item', () => {
    const fn = vi.fn();
    render(<BandNav items={[{ label: 'A', onClick: fn }]} />);
    fireEvent.click(screen.getByText('A'));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
