import { Outlet } from 'react-router-dom';
import { ToastProvider } from './Toast';
import { SentinelShell } from './sentinel/SentinelShell';

// 工具页壳 = SentinelShell (layer=null: 三层 tab 不高亮, 更多菜单指示当前位置) + 居中内容容器。
// 2026-09-10 壳统一: 左侧 AppNav 侧栏删除 — 其 14 项入口与壳内三层导航 / 更多菜单 / 各页内导航全量重复
// (SK 能力包 → /skill-store 页内 v1 区块, 知识管理 → /knowledge 页内 KnowledgeTabs)。
export function PageLayout() {
  return (
    <ToastProvider>
      <a
        href="#main-content"
        className="skip-link"
        aria-label="跳转到主内容"
      >
        跳转到主内容
      </a>
      <SentinelShell layer={null}>
        <div
          id="main-content"
          className="tool-main max-w-[1320px] mx-auto px-4 sm:px-8 lg:px-10 py-4 sm:py-6"
        >
          <Outlet />
        </div>
      </SentinelShell>
    </ToastProvider>
  );
}

// v0.8.5: 三层 Sentinel 全屏布局 — 只提供 ToastProvider (v1 区块 mutation 提示需要),
// 不渲染 AppNav 侧栏: 三层页由页内 SentinelShell 提供唯一导航 (spec §4.3 壳纪律).
export function SentinelLayout() {
  return (
    <ToastProvider>
      <div
        className="min-h-[100dvh] relative"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <Outlet />
      </div>
    </ToastProvider>
  );
}