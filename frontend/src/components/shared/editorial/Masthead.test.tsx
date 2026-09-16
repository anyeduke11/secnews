import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Masthead } from './Masthead';

describe('Masthead', () => {
  it('renders brand/title/sub', () => {
    render(<Masthead brand="B" title="T" sub="S" />);
    expect(screen.getByText('B')).toBeDefined();
    expect(screen.getByText('T')).toBeDefined();
    expect(screen.getByText('S')).toBeDefined();
  });

  it('renders right slot', () => {
    render(<Masthead title="T" right={<span>right</span>} />);
    expect(screen.getByText('right')).toBeDefined();
  });

  it('applies masthead class', () => {
    const { container } = render(<Masthead title="T" />);
    const el = container.firstElementChild as HTMLElement | undefined;
    expect(el?.className).toContain('masthead');
  });
});
