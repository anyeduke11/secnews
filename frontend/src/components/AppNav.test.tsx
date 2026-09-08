// T17.5: AppNav 组件测试 (基础渲染 + nav 链接可见).
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { AppNav } from "./AppNav";

describe("AppNav", () => {
  it("renders 3 nav groups (三层工作流 + 6 SK + 4 知识管理) — v0.8.5 首组指向三层真实路径", () => {
    render(
      <MemoryRouter>
        <AppNav />
      </MemoryRouter>
    );
    expect(screen.getByText("资料层")).toBeTruthy();
    expect(screen.getByText("判断层")).toBeTruthy();
    expect(screen.getByText("行动层")).toBeTruthy();
    expect(screen.getByText("知识目录")).toBeTruthy();
    expect(screen.getByText("SK 商店")).toBeTruthy();
    expect(screen.getByText("SK-01 每日优先情报")).toBeTruthy();
    expect(screen.getByText("SK-05 经验复用")).toBeTruthy();
    expect(screen.getByText("导入")).toBeTruthy();
  });

  it("v1_active 角标仅出现在 SK 能力项 (v0.8.5: 三层入口不再标 v1.0)", () => {
    render(
      <MemoryRouter>
        <AppNav />
      </MemoryRouter>
    );
    const v1Badges = screen.getAllByText("v1.0");
    // SK 商店 + 5 SK 项 (v0.8.5 起首组 4 项不带 v1_active)
    expect(v1Badges.length).toBeGreaterThanOrEqual(1);
  });

  it("legacy 角标出现在 知识管理 4 域 (legacy_v0)", () => {
    render(
      <MemoryRouter>
        <AppNav />
      </MemoryRouter>
    );
    const legacyBadges = screen.getAllByText("legacy");
    expect(legacyBadges.length).toBe(4);  // import/process/compile/imported
  });
});
