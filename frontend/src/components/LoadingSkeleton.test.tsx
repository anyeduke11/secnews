// frontend/src/components/LoadingSkeleton.test.tsx
// Phase 6 — LoadingSkeleton 测试
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { LoadingSkeleton } from './LoadingSkeleton';

describe('LoadingSkeleton', () => {
  it('renders 12 placeholder cards', () => {
    const { container } = render(<LoadingSkeleton />);
    // 每个卡片有 4 个 shimmer 块 (badge + 2 title + 2 summary + 2 bottom)
    // 总数 = 12 * 4 = 48
    const animatedDivs = container.querySelectorAll('.animate-shimmer');
    expect(animatedDivs.length).toBe(12);
  });

  it('uses grid layout', () => {
    const { container } = render(<LoadingSkeleton />);
    const grid = container.querySelector('.grid');
    expect(grid).toBeInTheDocument();
  });
});
