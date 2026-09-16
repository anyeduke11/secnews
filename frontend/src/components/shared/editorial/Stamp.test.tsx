import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Stamp } from './Stamp';

describe('Stamp', () => {
  it('renders children with default props', () => {
    render(<Stamp>DEFAULT</Stamp>);
    expect(screen.getByText('DEFAULT')).toBeDefined();
  });

  it('applies color class and text', () => {
    render(<Stamp color="ok">OK</Stamp>);
    const el = screen.getByText('OK');
    expect(el.className).toContain('st-ok');
  });

  it('applies variant class', () => {
    render(<Stamp variant="hollow">HOLLOW</Stamp>);
    const el = screen.getByText('HOLLOW');
    expect(el.className).toContain('st-hollow');
  });

  it('applies size class', () => {
    render(<Stamp size="lg">LG</Stamp>);
    const el = screen.getByText('LG');
    expect(el.className).toContain('st-lg');
  });
});
