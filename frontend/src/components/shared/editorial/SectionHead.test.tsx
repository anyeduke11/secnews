import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SectionHead } from './SectionHead';

describe('SectionHead', () => {
  it('renders title', () => {
    render(<SectionHead title="Section" />);
    expect(screen.getByText('Section')).toBeDefined();
  });

  it('renders slim variant without border-bottom', () => {
    const { container } = render(<SectionHead title="Slim" slim />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('slim');
  });

  it('renders right slot', () => {
    render(<SectionHead title="Section" right={<span>right</span>} />);
    expect(screen.getByText('right')).toBeDefined();
  });
});
