import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WireList, WireRow } from './WireList';

describe('WireList', () => {
  it('renders children', () => {
    render(<WireList><div>wire</div></WireList>);
    expect(screen.getByText('wire')).toBeDefined();
  });

  it('applies wire class', () => {
    const { container } = render(<WireList />);
    const el = container.firstElementChild as HTMLElement | undefined;
    expect(el?.className).toContain('wire');
  });
});

describe('WireRow', () => {
  it('renders title and sc', () => {
    render(<WireRow title="T" sc="S" />);
    expect(screen.getByText('T')).toBeDefined();
    expect(screen.getByText('S')).toBeDefined();
  });

  it('applies done state', () => {
    const { container } = render(<WireRow title="T" done />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('done');
  });
});
