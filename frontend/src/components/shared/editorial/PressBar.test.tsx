import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PressBar, PressItem } from './PressBar';

describe('PressBar', () => {
  it('renders children', () => {
    render(<PressBar><div>press</div></PressBar>);
    expect(screen.getByText('press')).toBeDefined();
  });

  it('applies pressbar class', () => {
    const { container } = render(<PressBar />);
    const el = container.firstElementChild as HTMLElement | undefined;
    expect(el?.className).toContain('pressbar');
  });
});

describe('PressItem', () => {
  it('renders label and value', () => {
    render(<PressBar><PressItem label="L" value="V" /></PressBar>);
    expect(screen.getByText('L')).toBeDefined();
    expect(screen.getByText('V')).toBeDefined();
  });
});
