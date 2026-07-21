// frontend/src/components/Icon.test.tsx
// Phase 6 — Icon 共享组件测试
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Icon } from './Icon';

describe('Icon', () => {
  it('renders an SVG with default size 14', () => {
    const { container } = render(
      <Icon>
        <line x1="1" y1="1" x2="2" y2="2" />
      </Icon>
    );
    const svg = container.querySelector('svg')!;
    expect(svg).toBeInTheDocument();
    expect(svg.getAttribute('width')).toBe('14');
    expect(svg.getAttribute('height')).toBe('14');
  });

  it('respects custom size', () => {
    const { container } = render(
      <Icon size={24}>
        <circle cx="12" cy="12" r="10" />
      </Icon>
    );
    const svg = container.querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('24');
    expect(svg.getAttribute('height')).toBe('24');
  });

  it('is hidden from assistive tech (aria-hidden=true)', () => {
    const { container } = render(
      <Icon>
        <path d="M0 0" />
      </Icon>
    );
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('uses currentColor for stroke', () => {
    const { container } = render(
      <Icon>
        <line x1="0" y1="0" x2="1" y2="1" />
      </Icon>
    );
    expect(container.querySelector('svg')).toHaveAttribute('stroke', 'currentColor');
  });
});
