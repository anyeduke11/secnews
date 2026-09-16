import { Outlet } from 'react-router-dom';
import { ToastProvider } from './Toast';
import { SentinelShell } from './sentinel/SentinelShell';

// 工具页壳 = SentinelShell (layer=null: 四菜单 tab 由 menuOf 自动高亮归属) + 居中内容容器。
// 2026-09-10 壳统一: 左侧 AppNav 侧栏删除 — 其 14 项入口与壳内四菜单导航 / 各页内导航全量重复
// (SK 能力包 → /skill-store 页内 v1 区块, 知识管理 → /knowledge 页内 KnowledgeTabs)。
// 2026-09-13 NAV4 + P2: 更多菜单 (SentinelMoreMenu / UTILITY_GROUPS) 物理删除, 工具页高亮由 menuOf 接管
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
          className="tool-main max-w-[1580px] mx-auto px-4 sm:px-6 pt-4 pb-16"
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