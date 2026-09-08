/**v1.0 C09 反例测试 (R14/R23/R24 路由壳+UI 收尾).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §9 C09] + [REVIEW_2026-09-07.md R14/R23/R24] +
[docs/v1.0/V1.0.0_UI_UX_SPEC.md §2 信息架构与 URL].
Mimosa 约束: 路由配置不能重复声明 (会触发 React Router 警告 + 后声明的覆盖前者).
*/

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const ROUTES_TSX = readFileSync(join(ROOT, "src/routes/index.tsx"), "utf-8");
const V1_PROTOTYPE_TSX = readFileSync(
  join(ROOT, "src/components/v1/V1Prototype.tsx"),
  "utf-8"
);


/**
 * R23 反例基线 → 修复断言: 4 真路由 (workbench / intel / cases / knowledge)
 * 全部挂 V1Prototype (单一组件). C09 修复: 拆 4 真实页面 (WorkbenchPage / IntelPage /
 * CasesPage / KnowledgePage),每路由一个组件.
 */
describe("C09 R23: 4 真路由不应全挂 V1Prototype", () => {
  it("R23 修复 1: /workbench 不应 element=V1Prototype", () => {
    // 找 /workbench 路由行 — 用 DOTALL 让 .*? 跨多行
    const workbenchRoute = ROUTES_TSX.match(
      /<Route\s+path="\/workbench"[\s\S]*?element=\{<Suspense[\s\S]*?\/>\s*}\s*\/>/
    );
    expect(workbenchRoute).toBeTruthy();
    if (workbenchRoute) {
      const routeLine = workbenchRoute[0];
      expect(routeLine).not.toContain("P.V1Prototype");
      // 修复后应是独立 WorkbenchPage
      expect(routeLine).toMatch(/P\.WorkbenchPage|WorkbenchPage/);
    }
  });

  it("R23 修复 2: /intel /cases /knowledge 不应全挂 V1Prototype", () => {
    for (const path of ["/intel", "/cases", "/knowledge"]) {
      // 找首个 /intel 等路由声明 (避免 /knowledge/import 子路由)
      // v1.0.1: 路由 element 可能用 <V1SentinelShell>...<P.IntelPage />...</V1SentinelShell>
      //         等多层嵌套, 改用宽松匹配 `<Route path="${path}" element=` 起点 + 取到下一个 >,
      //         不再依赖自闭合 />
      const re = new RegExp(`<Route\\s+path="${path.replace(/\//g, "\\/")}"[^>]*>`, "g");
      const matches = ROUTES_TSX.match(re);
      expect(matches).toBeTruthy();
      if (matches) {
        const firstMatch = matches[0];
        // element 必须是独立 v1 page (P.IntelPage/P.CasesPage/P.KnowledgePage)
        // 或 V1SentinelShell 包裹, 不能直接是 P.V1Prototype (R23 要求拆 3 独立 page)
        expect(firstMatch).toMatch(/P\.(IntelPage|CasesPage|KnowledgePage|WorkbenchPage)|V1SentinelShell/);
        expect(firstMatch).not.toContain("P.V1Prototype>");
      }
    }
  });
});


/**
 * R23 反例基线: /v1-prototype 还在 + /knowledge 重复声明.
 * C09 修复: 删 /v1-prototype 兼容路由 + 合并重复 /knowledge 声明 (只保留一个).
 */
describe("C09 R23: 不应有 /v1-prototype 兼容 + 重复 /knowledge 声明", () => {
  it("R23 修复 3: /v1-prototype 兼容路由应已删除", () => {
    // 旧 v1.0 T15 留兼容 /v1-prototype 路径, C09 收尾后应删
    const v1PrototypeRoute = /<Route\s+path="\/v1-prototype"[^>]*\/>/.exec(ROUTES_TSX);
    expect(v1PrototypeRoute).toBeNull();
  });

  it("R23 修复 4: /knowledge 路由声明只应有 1 个 (V1Prototype + KnowledgePage 不共存)", () => {
    // 找所有 path="/knowledge" 行 (不能是 /knowledge/xxx 子路由)
    const matches = ROUTES_TSX.match(/<Route\s+path="\/knowledge"(?!\/)[^>]*\/>/g);
    const count = matches ? matches.length : 0;
    // C09 修复后只应 1 个 /knowledge 声明 (用 IntelPage 或类似真实页面, 不用 V1Prototype)
    expect(count).toBeLessThanOrEqual(1);
  });
});


/**
 * R24 反例基线: / 仍走 SentinelHomePage (旧壳) + 多个 /judge /action /garden 旧入口.
 * C09 修复: / 走 /workbench (NestRoute), 删 /judge /action /garden (UI_UX_SPEC §1
 * "对话只作为 Case 内补充说明" - 旧 sentinel 入口已废弃).
 */
describe("C09 R24: 默认 / 不应走旧 Sentinel 壳", () => {
  it("R24 修复 1: / 路由 element 不应是 SentinelHomePage", () => {
    const homeRoute = /<Route\s+path="\/"[^>]*\/>/.exec(ROUTES_TSX);
    expect(homeRoute).toBeTruthy();
    if (homeRoute) {
      expect(homeRoute[0]).not.toContain("SentinelHomePage");
      // 修复后 / 应走 PageLayout 内的真实页面 (WorkbenchPage 或 Navigate to /workbench)
    }
  });

  it("R24 修复 2: 旧 sentinel 入口 /judge /action /garden 应已删除", () => {
    for (const path of ["/judge", "/action", "/garden", "/judge/graph"]) {
      const re = new RegExp(`<Route\\s+path="${path.replace(/\//g, "\\/")}"[^>]*\\/>`);
      const match = re.exec(ROUTES_TSX);
      expect(match).toBeNull();
    }
  });
});


/**
 * R14 反例基线: V1Prototype 仍 export 6 个 MOCK_* 数组占位 (C04 deprecated 标了,
 * C09 真删). 修复后 V1Prototype 不再含 MOCK_CASES / MOCK_JUDGMENTS / MOCK_ACTIONS /
 * MOCK_RUNS / MOCK_ARTIFACTS / MOCK_KNOWLEDGE, 走真实 API (失败显 unavailable, 不 fallback).
 */
describe("C09 R14: V1Prototype 不应再有 MOCK_* 占位", () => {
  it("R14 修复 1: V1Prototype.tsx 不应再 export MOCK_CASES / MOCK_JUDGMENTS", () => {
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_CASES\s*:/);
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_JUDGMENTS\s*:/);
  });

  it("R14 修复 2: V1Prototype.tsx 不应再 export MOCK_ACTIONS / MOCK_RUNS", () => {
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_ACTIONS\s*:/);
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_RUNS\s*:/);
  });

  it("R14 修复 3: V1Prototype.tsx 不应再 export MOCK_ARTIFACTS / MOCK_KNOWLEDGE", () => {
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_ARTIFACTS\s*:/);
    expect(V1_PROTOTYPE_TSX).not.toMatch(/const\s+MOCK_KNOWLEDGE\s*:/);
  });

  it("R14 修复 4: V1Prototype 不应 usingFallback state (real data fail → unavailable)", () => {
    // usingFallback state = true 会在 API 失败时显 mock 数据, 违反 AC-11 "API 断开不显示空数据"
    // 排除注释和文档字符串: 只查代码中 usingFallback = (赋值, 不是 .text 或 'usingFallback' 描述)
    // 简单粗暴: 查 const [usingFallback, setUsingFallback] = useState 模式
    expect(V1_PROTOTYPE_TSX).not.toMatch(/useState<.*>\s*\(\s*true\s*\)/);
    expect(V1_PROTOTYPE_TSX).not.toMatch(/setUsingFallback/);
  });
});


/**
 * R24 反例基线: V1Prototype 内层有 4 主入口 tabs (workbench / intel / cases / knowledge),
 * 与 AppNav 主导航并存 (2 套导航真相). C09 修复: 删 V1Prototype 内层 tabs,
 * 1 个壳 + 1 个主导航 (AppNav 已在 T17.5 落地 14 项).
 */
describe("C09 R24: V1Prototype 不应再有内层 4 tabs", () => {
  it("R24 修复: V1Prototype 不应 export 内层 4 主入口 tab 切换逻辑", () => {
    // 内层 tab 切换通常有 activeTab / setActiveTab state
    const hasActiveTab = /activeTab|setActiveTab|currentTab|setCurrentTab/.test(V1_PROTOTYPE_TSX);
    expect(hasActiveTab).toBe(false);
  });
});
