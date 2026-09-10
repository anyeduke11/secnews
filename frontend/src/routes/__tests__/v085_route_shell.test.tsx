/**
 * v0.8.5 反向收敛守卫 (spec: docs/v0.8.5/V0.8.5_PLAN.md §4.1 / §5)
 *
 * 方向锁 (2026-09-08 裁决): v0.8 Sentinel 三层是唯一壳; V1SentinelShell 物理删除;
 * v1 四入口降级重定向。任何会话想再换壳/复活平行入口, 此测试先红。
 * 取代 c09_route_shell.test.tsx — 其锁定的 C09 决策已被 v0.8.5 反转,
 * 若未来再调方向, 必须显式重写本文件 + 撤销 spec 横幅, 不允许静默漂移。
 *
 * Mimosa 约束: 路由配置不能重复声明 (React Router 警告 + 后声明覆盖前者)。
 */

import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";
import { waitFor } from "@testing-library/react";

const ROOT = process.cwd();
const ROUTES_TSX = readFileSync(join(ROOT, "src/routes/index.tsx"), "utf-8");
const V1_PROTOTYPE_TSX = readFileSync(join(ROOT, "src/components/v1/V1Prototype.tsx"), "utf-8");

/** 取路由声明所在行 (本项目路由 element 单行书写) */
function routeLine(path: string): string | undefined {
  return ROUTES_TSX.split("\n").find(l => l.includes(`path="${path}"`));
}

describe("v0.8.5 §5: 三层 Sentinel 恢复", () => {
  const restored: Array<[string, RegExp]> = [
    ["/", /P\.SentinelHomePage/],
    ["/judge", /P\.SentinelJudgePage/],
    ["/judge/graph", /P\.SentinelGraphPage/],
    ["/action", /P\.SentinelActionPage/],
    ["/garden", /P\.SentinelGardenPage/],
  ];
  for (const [path, pageRe] of restored) {
    it(`${path} 必须恢复且由 Sentinel 页面承载`, () => {
      const line = routeLine(path);
      expect(line).toBeTruthy();
      if (line) expect(line).toMatch(pageRe);
    });
  }

  it("三层路由组必须套 SentinelLayout (全屏、无 AppNav)", () => {
    expect(ROUTES_TSX).toContain("<Route element={<SentinelLayout />}>");
  });

  it("各 Sentinel 页必须自嵌 SentinelShell 且 layer 正确 (心跳条常驻的载体)", () => {
    const expectLayer: Array<[string, string]> = [
      ["src/components/sentinel/SentinelHomePage.tsx", 'layer="data"'],
      ["src/components/sentinel/SentinelJudgePage.tsx", 'layer="judge"'],
      ["src/components/sentinel/SentinelGraphPage.tsx", 'layer="judge"'],
      ["src/components/sentinel/SentinelActionPage.tsx", 'layer="action"'],
      ["src/components/sentinel/SentinelGardenPage.tsx", 'layer="action"'],
    ];
    for (const [file, layer] of expectLayer) {
      const src = readFileSync(join(ROOT, file), "utf-8");
      expect(src).toContain("<SentinelShell");
      expect(src).toContain(layer);
    }
  });

  it("SentinelShell 三层导航必须指向 / /judge /action (不允许再映射到 v1 入口)", () => {
    const shell = readFileSync(join(ROOT, "src/components/sentinel/SentinelShell.tsx"), "utf-8");
    // 只取 LAYER_DEFS 块判定 (更多菜单 UTILITY_GROUPS 的 to: '/knowledge' 是合法工具入口)
    const block = /const LAYER_DEFS[\s\S]*?^\];/m.exec(shell);
    expect(block).toBeTruthy();
    if (block) {
      expect(block[0]).toMatch(/layer: 'data',[^\n]*to: '\/',/);
      expect(block[0]).toMatch(/layer: 'judge',[^\n]*to: '\/judge',/);
      expect(block[0]).toMatch(/layer: 'action',[^\n]*to: '\/action',/);
      expect(block[0]).not.toMatch(/to: '\/intel'|to: '\/cases'|to: '\/knowledge'/);
    }
  });
});

describe("v0.8.5 §5: v1 四入口降级重定向 (透传 query)", () => {
  it("/workbench /intel → / ; /cases → /judge (QueryRedirect)", () => {
    const wb = routeLine("/workbench");
    expect(wb).toBeTruthy();
    expect(wb).toContain("QueryRedirect");
    expect(wb).toContain('to="/"');

    const intel = routeLine("/intel");
    expect(intel).toBeTruthy();
    expect(intel).toContain("QueryRedirect");
    expect(intel).toContain('to="/"');

    const casesLine = routeLine("/cases");
    expect(casesLine).toBeTruthy();
    expect(casesLine).toContain("QueryRedirect");
    expect(casesLine).toContain('to="/judge"');
  });

  it("/workbench /intel /cases 不再挂任何 page 组件", () => {
    for (const p of ["/workbench", "/intel", "/cases"]) {
      const line = routeLine(p);
      expect(line).not.toMatch(/P\.(WorkbenchPage|IntelPage|CasesPage)/);
    }
  });
});

describe("v0.8.5 §4.1: V1SentinelShell 物理删除 (双断言)", () => {
  it("fs 断言: 文件不存在", () => {
    expect(existsSync(join(ROOT, "src/components/sentinel/V1SentinelShell.tsx"))).toBe(false);
  });

  it("grep 断言: 全 src 无 import / JSX 用法 (注释提及不算引用)", () => {
    let out = "";
    try {
      out = execSync(
        'grep -rnE --exclude-dir=.mimosa --exclude=v085_route_shell.test.tsx "(import .*V1SentinelShell|from .*/V1SentinelShell|<V1SentinelShell)" src',
        { encoding: "utf-8", cwd: ROOT },
      );
    } catch {
      // grep exit 1 = 无匹配, 正是期望
    }
    expect(out.trim()).toBe("");
  });
});

// ── 2026-09-10 壳统一 (owner 裁决: 打散左侧菜单, 横向导航, 能力归位各页): 工具页 PageLayout 亦走 SentinelShell ──
describe("2026-09-10 壳统一: AppNav 左侧栏物理删除 (双断言) + PageLayout 走 SentinelShell", () => {
  it("fs 断言: AppNav.tsx 不存在 (SK 能力包 → /skill-store 页内区块, 知识管理 → KnowledgeTabs)", () => {
    expect(existsSync(join(ROOT, "src/components/AppNav.tsx"))).toBe(false);
  });

  it("grep 断言: 全 src 无 AppNav import / JSX 用法", () => {
    let out = "";
    try {
      out = execSync(
        'grep -rnE --exclude-dir=.mimosa --exclude=v085_route_shell.test.tsx "(import .*\\bAppNav\\b|from .*/AppNav|<AppNav)" src',
        { encoding: "utf-8", cwd: ROOT },
      );
    } catch {
      // grep exit 1 = 无匹配, 正是期望
    }
    expect(out.trim()).toBe("");
  });

  it("PageLayout 必须以 SentinelShell layer={null} 为壳 (一个路由只渲染一个壳)", () => {
    const layout = readFileSync(join(ROOT, "src/components/PageLayout.tsx"), "utf-8");
    expect(layout).toContain("<SentinelShell layer={null}>");
  });
});

// ── 继承 C09 R14/R24 的有效纪律 (真实 API, 无 mock 回退, 无内层导航) ──
describe("v0.8.5 继承: V1Prototype 纪律 (原 C09 R14/R24)", () => {
  it("不应再有 MOCK_* 占位 (真实 API, 失败显 unavailable)", () => {
    expect(V1_PROTOTYPE_TSX).not.toMatch(
      /const\s+MOCK_(CASES|JUDGMENTS|ACTIONS|RUNS|ARTIFACTS|KNOWLEDGE)\s*:/
    );
  });

  it("不应有 usingFallback / 内层主 tabs (URL 是唯一导航真相源)", () => {
    expect(V1_PROTOTYPE_TSX).not.toMatch(/setUsingFallback/);
    expect(V1_PROTOTYPE_TSX).not.toMatch(/activeTab|setActiveTab|currentTab|setCurrentTab/);
  });
});

// ── P2 修复 (代码审查 #4): query 透传是 spec §5 裁决语义, 用运行时断言锁定 ──
describe("v0.8.5 §5: QueryRedirect 运行时透传 query", () => {
  it("/cases?status=blocked → /judge?status=blocked (非仅字符串断言)", async () => {
    const { MemoryRouter, Routes, Route, useLocation } = await import("react-router-dom");
    const { render, screen } = await import("@testing-library/react");
    const { QueryRedirect } = await import("../index");
    function Probe() {
      const loc = useLocation();
      return <div data-testid="loc">{loc.pathname}{loc.search}</div>;
    }
    render(
      <MemoryRouter initialEntries={["/cases?status=blocked"]}>
        <Routes>
          <Route path="/cases" element={<QueryRedirect to="/judge" />} />
          <Route path="/judge" element={<Probe />} />
          <Route path="*" element={<Probe />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/judge?status=blocked"));
  });
});
