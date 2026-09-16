import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Ticket } from './Ticket';

describe('Ticket', () => {
  it('renders title and summary', () => {
    render(<Ticket title="T" summary="S" />);
    expect(screen.getByText('T')).toBeDefined();
    expect(screen.getByText('S')).toBeDefined();
  });

  it('renders hot/lead classes', () => {
    const { container } = render(<Ticket hot lead title="Lead hot" />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('hot');
    expect(el.className).toContain('lead');
  });

  it('renders side slot', () => {
    render(<Ticket title="T" side={<span>side</span>} />);
    expect(screen.getByText('side')).toBeDefined();
  });
});
