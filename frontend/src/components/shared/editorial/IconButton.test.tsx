import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IconButton } from './IconButton';

describe('IconButton', () => {
  it('renders children', () => {
    render(<IconButton ariaLabel="test">X</IconButton>);
    expect(screen.getByLabelText('test')).toBeDefined();
  });

  it('calls onClick when clicked', () => {
    const fn = vi.fn();
    render(<IconButton onClick={fn} ariaLabel="click" />);
    fireEvent.click(screen.getByLabelText('click'));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('applies active class', () => {
    render(<IconButton active ariaLabel="active" />);
    expect(screen.getByLabelText('active').className).toContain('on');
  });
});
