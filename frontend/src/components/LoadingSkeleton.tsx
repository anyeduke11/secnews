import React from 'react';

export function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="rounded-[var(--radius-md)] p-4 animate-shimmer"
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
          }}
        >
          {/* Badge + time row */}
          <div className="flex items-center justify-between mb-3">
            <div className="h-3.5 w-14 rounded-[var(--radius-full)]" style={{ backgroundColor: 'var(--bg-hover)' }} />
            <div className="h-3 w-10 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
          </div>
          {/* Title lines */}
          <div className="space-y-1.5 mb-3">
            <div className="h-3.5 w-full rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
            <div className="h-3.5 w-4/5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
          </div>
          {/* Summary lines */}
          <div className="space-y-1 mb-3">
            <div className="h-3 w-full rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
            <div className="h-3 w-3/5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
          </div>
          {/* Bottom row */}
          <div className="flex items-center justify-between pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <div className="h-3 w-16 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
            <div className="h-3 w-12 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}
