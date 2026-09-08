// T17.5: AppNav - 4 主入口 + 6 v1 SK + 知识管理 4 域 共 14 项 nav + 390 宽 Hamburger 折叠.
//
// 桌面: 左 fixed SideNav 240-280px.
// 移动 (max-width: 390px): 顶部 56px Hamburger toggle + 全屏 Drawer.
import { useState } from "react";
import { NavLink } from "react-router-dom";

interface AppNavItem {
  to: string;
  label: string;
  icon: string;
  v1_active?: boolean;  // T17.5: v1_active 高亮
  legacy?: boolean;  // T17.5: legacy_v0 折叠
}

interface AppNavGroup {
  title: string;
  items: AppNavItem[];
}

const NAV_GROUPS: AppNavGroup[] = [
  {
    title: "4 主入口 (v1.0)",
    items: [
      { to: "/workbench", label: "今日工作", icon: "📊", v1_active: true },
      { to: "/intel", label: "情报", icon: "📡", v1_active: true },
      { to: "/cases", label: "事项", icon: "📋", v1_active: true },
      { to: "/knowledge", label: "知识", icon: "📚", v1_active: true },
    ],
  },
  {
    title: "6 SK 受管能力包 (v1.0)",
    items: [
      { to: "/skill-store", label: "SK 商店", icon: "🎯", v1_active: true },
      { to: "/skill-store/daily-priority-intel", label: "SK-01 每日优先情报", icon: "📅", v1_active: true },
      { to: "/skill-store/cve-impact-brief", label: "SK-02 漏洞影响研判", icon: "🎯", v1_active: true },
      { to: "/skill-store/inspection-materials", label: "SK-03 排查材料", icon: "🔍", v1_active: true },
      { to: "/skill-store/action-retrospective", label: "SK-04 行动后提炼", icon: "📝", v1_active: true },
      { to: "/skill-store/reuse-experience", label: "SK-05 经验复用", icon: "🔄", v1_active: true },
    ],
  },
  {
    title: "知识管理",
    items: [
      { to: "/knowledge/import", label: "导入", icon: "📥", legacy: true },
      { to: "/knowledge/process", label: "处理", icon: "⚙️", legacy: true },
      { to: "/knowledge/compile", label: "编译", icon: "🛠️", legacy: true },
      { to: "/knowledge/imported", label: "已导入", icon: "✅", legacy: true },
    ],
  },
];

export function AppNav() {
  const [open, setOpen] = useState(false);  // mobile drawer toggle
  // 关闭 mobile drawer on nav (避免 URL 变化后还展开)
  const onNav = () => {
    if (typeof window !== "undefined" && window.innerWidth < 640) setOpen(false);
  };

  return (
    <>
      {/* 移动 Hamburger 按钮 (max-width: 639px 显) */}
      <button
        type="button"
        aria-label="打开导航"
        onClick={() => setOpen(v => !v)}
        className="sm:hidden fixed top-2 left-2 z-30 px-3 py-2 rounded border text-sm"
        style={{ background: "var(--bg-card)", borderColor: "var(--line)", color: "var(--text-primary)" }}
      >
        ☰
      </button>

      {/* 桌面 SideNav (min-width: 640px 显) */}
      <nav
        aria-label="主导航"
        className="hidden sm:block fixed left-0 top-0 bottom-0 w-64 overflow-y-auto border-r"
        style={{ background: "var(--bg-card)", borderColor: "var(--line)" }}
      >
        <NavBody onNav={onNav} />
      </nav>

      {/* 移动 Drawer (max-width: 639px 显, open 时) */}
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 sm:hidden"
            style={{ background: "rgba(0,0,0,0.5)" }}
            onClick={() => setOpen(false)}
            aria-label="关闭导航"
          />
          <nav
            aria-label="主导航 (移动)"
            className="fixed left-0 top-0 bottom-0 w-64 z-50 sm:hidden overflow-y-auto border-r"
            style={{ background: "var(--bg-card)", borderColor: "var(--line)" }}
          >
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="关闭"
                className="px-2 py-1 text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                ✕
              </button>
            </div>
            <NavBody onNav={onNav} />
          </nav>
        </>
      )}
    </>
  );
}

function NavBody({ onNav }: { onNav: () => void }) {
  return (
    <div className="p-3 space-y-4">
      {NAV_GROUPS.map((g, gi) => (
        <div key={gi}>
          <h3
            className="text-[10px] font-bold uppercase mb-2 px-2"
            style={{ color: "var(--ink-3, var(--text-muted))" }}
          >
            {g.title}
          </h3>
          <ul className="space-y-0.5">
            {g.items.map((it, ii) => (
              <li key={ii}>
                <NavLink
                  to={it.to}
                  onClick={onNav}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors ${
                      isActive ? "font-bold" : "opacity-80 hover:opacity-100"
                    }`
                  }
                  style={({ isActive }) => ({
                    background: isActive ? "var(--accent, var(--color-success))" : "transparent",
                    color: isActive ? "var(--text-on-light)" : "var(--text-primary)",
                    borderLeft: it.v1_active
                      ? "3px solid var(--color-success)"
                      : it.legacy
                      ? "3px solid var(--line, var(--border-muted))"
                      : "3px solid transparent",
                  })}
                >
                  <span>{it.icon}</span>
                  <span className="flex-1 truncate">{it.label}</span>
                  {it.v1_active && (
                    <span
                      className="text-[9px] px-1 rounded font-bold"
                      style={{ background: "var(--color-success)", color: "var(--text-on-light)" }}
                    >
                      v1.0
                    </span>
                  )}
                  {it.legacy && (
                    <span
                      className="text-[9px] px-1 rounded opacity-60"
                      style={{ background: "var(--line, var(--border-muted))" }}
                    >
                      legacy
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
