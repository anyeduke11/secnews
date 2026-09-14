/**
 * NAV4 四菜单壳守卫 (spec: docs/NAV4_IA_REDESIGN_2026-09-12.md + docs/v0.8.5/V0.8.5_PLAN.md 修订注③)
 *
 * 方向锁 (2026-09-13 裁决): SentinelShell 唯一壳改为四菜单 (资讯/知识/行动/设置);
 * /judge → /, /cases → /action, /judge/graph → /knowledge/graph。
 * 任何会话想再换壳/复活平行入口, 此测试先红。
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const ROUTES_TSX = readFileSync(join(ROOT, "src/routes/index.tsx"), "utf-8");
const SHELL_TSX = readFileSync(join(ROOT, "src/components/sentinel/SentinelShell.tsx"), "utf-8");
const SENTINEL_CSS = readFileSync(join(ROOT, "src/components/sentinel/sentinel.css"), "utf-8");
const THEME_CONTEXT = readFileSync(join(ROOT, "src/contexts/ThemeContext.tsx"), "utf-8");
const INDEX_CSS = readFileSync(join(ROOT, "src/index.css"), "utf-8");
const LAYOUT_TSX = readFileSync(join(ROOT, "src/components/PageLayout.tsx"), "utf-8");

/** 取路由声明所在行 (本项目路由 element 单行书写) */
function routeLine(path: string): string | undefined {
  return ROUTES_TSX.split("\n").find(l => l.includes(`path="${path}"`));
}

describe("NAV4 §5: 四菜单 SentinelShell", () => {
  const menus: Array<[string, string, RegExp]> = [
    ["/", "data", /SentinelHomePage/],
    ["/knowledge", "knowledge", /KnowledgePage/],
    ["/action", "action", /SentinelActionPage/],
    ["/settings", "settings", /SettingsPage/],
  ];
  for (const [path, _layer, pageRe] of menus) {
    it(`${path} 必须由对应页面承载`, () => {
      const line = routeLine(path);
      expect(line).toBeTruthy();
      if (line) expect(line).toMatch(pageRe);
    });
  }

  it("SentinelShell 四菜单导航必须指向 / /knowledge /action /settings", () => {
    const block = /const LAYER_DEFS[\s\S]*?^\];/m.exec(SHELL_TSX);
    expect(block).toBeTruthy();
    if (block) {
      expect(block[0]).toMatch(/layer: 'data',[^\n]*to: '\/',/);
      expect(block[0]).toMatch(/layer: 'knowledge',[^\n]*to: '\/knowledge',/);
      expect(block[0]).toMatch(/layer: 'action',[^\n]*to: '\/action',/);
      expect(block[0]).toMatch(/layer: 'settings',[^\n]*to: '\/settings',/);
      // 旧三层映射必须消失
      expect(block[0]).not.toMatch(/to: '\/judge'/);
    }
  });

  it("menuOf() 必须覆盖 27 条路由归属 (无 null 悬空)", () => {
    const menuOfBlock = /export function menuOf[\s\S]*?^\}/m.exec(SHELL_TSX);
    expect(menuOfBlock).toBeTruthy();
    // 至少覆盖关键路径前缀
    const src = menuOfBlock?.[0] ?? "";
    expect(src).toContain("pathname.startsWith('/knowledge')");
    expect(src).toContain("pathname.startsWith('/action')");
    expect(src).toContain("pathname.startsWith('/settings')");
    expect(src).toContain("pathname.startsWith('/secnews')");
  });
});

describe("NAV4 §5: 旧路径重定向 (透传 query)", () => {
  it("/judge → / (QueryRedirect 透传 query)", () => {
    const line = routeLine("/judge");
    expect(line).toBeTruthy();
    expect(line).toContain("QueryRedirect");
    expect(line).toContain('to="/"');
  });

  it("/cases → /action (QueryRedirect 透传 query)", () => {
    const line = routeLine("/cases");
    expect(line).toBeTruthy();
    expect(line).toContain("QueryRedirect");
    expect(line).toContain('to="/action"');
  });

  it("/judge/graph → /knowledge/graph (301 redirect)", () => {
    const line = routeLine("/judge/graph");
    expect(line).toBeTruthy();
    expect(line).toContain("/knowledge/graph");
  });

  it("/knowledge/graph 必须由 SentinelGraphPage 承载", () => {
    const line = routeLine("/knowledge/graph");
    expect(line).toBeTruthy();
    expect(line).toMatch(/SentinelGraphPage/);
  });
});

describe("NAV4 §5: 页面壳高亮归属", () => {
  const expectLayer: Array<[string, string]> = [
    ["src/components/sentinel/SentinelHomePage.tsx", 'layer="data"'],
    ["src/components/sentinel/SentinelActionPage.tsx", 'layer="action"'],
    ["src/components/v1/CaseDetailPage.tsx", 'layer="action"'],
  ];
  for (const [file, layer] of expectLayer) {
    it(`${file} 必须使用 ${layer}`, () => {
      const src = readFileSync(join(ROOT, file), "utf-8");
      expect(src).toContain("<SentinelShell");
      expect(src).toContain(layer);
    });
  }
});

describe("NAV4 §5: SecNewsShell 拆挂 (6 视图 + redirect)", () => {
  it("SecNewsShell 不再被 routes/index.tsx 路由引用 (退役过渡)", () => {
    expect(ROUTES_TSX).not.toMatch(/<P\.SecNewsShell\s*\/>/);
    expect(ROUTES_TSX).not.toMatch(/<Route\s+path="\/secnews"\s+element=.*SecNewsShell/);
  });

  it("/secnews index → /secnews/feed (Navigate 重定向)", () => {
    const line = ROUTES_TSX.split("\n").find(l => l.includes('path="/secnews"'));
    expect(line).toBeTruthy();
    expect(line).toMatch(/Navigate.*\/secnews\/feed/);
  });

  const directRoutes: Array<[string, RegExp]> = [
    ["/secnews/feed", /SecNewsFeed/],
    ["/secnews/pipeline", /SecNewsPipeline/],
    ["/secnews/knowledge", /SecNewsKnowledge/],
    ["/secnews/analyze", /SecNewsAnalyze/],
    ["/secnews/analytics", /SecNewsAnalytics/],
    ["/secnews/observability", /SecNewsObservability/],
  ];
  for (const [path, pageRe] of directRoutes) {
    it(`${path} 必须直接挂 PageLayout, 由对应页面承载`, () => {
      const line = routeLine(path);
      expect(line).toBeTruthy();
      expect(line).toMatch(pageRe);
      expect(line).not.toMatch(/SecNewsShell/);
    });
  }

  const redirectedRoutes = ["/secnews/image", "/secnews/settings"];
  for (const path of redirectedRoutes) {
    it(`${path} 必须 redirect 到 /settings (永久合并)`, () => {
      const line = routeLine(path);
      expect(line).toBeTruthy();
      expect(line).toContain("/settings");
    });
  }
});

describe("P2 死代码清理: 更多菜单物理删除, 不得复活", () => {
  it("SentinelMoreMenu 函数已删除", () => {
    expect(SHELL_TSX).not.toMatch(/function\s+SentinelMoreMenu\s*\(/);
  });

  it("UTILITY_GROUPS 常量已删除", () => {
    expect(SHELL_TSX).not.toMatch(/const\s+UTILITY_GROUPS/);
  });

  it("SentinelShell 不再 import Link (更多菜单用过的唯一消费者)", () => {
    expect(SHELL_TSX).not.toMatch(/import\s+[^;]*\bLink\b[^;]*from\s+['"]react-router-dom['"]/);
  });

  it("sentinel.css 已清 .sn-more / .sn-menu 孤儿样式", () => {
    expect(SENTINEL_CSS).not.toMatch(/\.sn-more\b/);
    expect(SENTINEL_CSS).not.toMatch(/\.sn-menu\b/);
    expect(SENTINEL_CSS).not.toMatch(/\.sn-menu-item\b/);
    expect(SENTINEL_CSS).not.toMatch(/\.sn-menu-note\b/);
  });

  it("PageLayout 注释明确写「更多菜单物理删除」字样 (新人接手护栏)", () => {
    expect(LAYOUT_TSX).toMatch(/更多菜单.*物理删除/);
  });
});

describe("P2 纸面版 theme 入口接入", () => {
  it("ThemeMode 三态扩展: light / dark / paper", () => {
    expect(THEME_CONTEXT).toMatch(/type\s+ThemeMode\s*=\s*['"]dark['"]\s*\|\s*['"]light['"]\s*\|\s*['"]paper['"]/);
  });

  it("ThemeContext 暴露 cycleTheme (三态轮换)", () => {
    expect(THEME_CONTEXT).toMatch(/cycleTheme\s*:\s*\(\)\s*=>\s*void/);
    expect(THEME_CONTEXT).toMatch(/const\s+cycleTheme\s*=\s*useCallback/);
  });

  it("index.css :root[data-theme=\"paper\"] 块已加 (暖米黄纸底 + 衬线字体)", () => {
    expect(INDEX_CSS).toMatch(/:root\[data-theme=['"]paper['"]\]\s*\{/);
    expect(INDEX_CSS).toMatch(/--font-serif/);
  });

  it("SentinelShell 主题按钮改为 cycleTheme + 三 svg 显隐", () => {
    expect(SHELL_TSX).toMatch(/cycleTheme/);
    expect(SHELL_TSX).toMatch(/tb-paper/);
    expect(SHELL_TSX).toMatch(/theme === 'paper'/);
  });

  it("paper 主题覆写 sentinel 控件色 token (controlbar/readmore/empty-cta/flash-title)", () => {
    expect(SENTINEL_CSS).toMatch(/html\[data-theme=['"]paper['"]\]\s+\.sentinel\s+\.controlbar/);
    expect(SENTINEL_CSS).toMatch(/html\[data-theme=['"]paper['"]\]\s+\.sentinel\s+\.readmore/);
    expect(SENTINEL_CSS).toMatch(/html\[data-theme=['"]paper['"]\]\s+\.sentinel\s+\.empty-cta/);
    expect(SENTINEL_CSS).toMatch(/html\[data-theme=['"]paper['"]\]\s+\.sentinel\s+\.alert-item\s+\.flash-title/);
  });
});

describe("NAV4 P3 (2026-09-13): 临时页面 /maint /knowledge/canvas 注册与归属", () => {
  it("/maint 路由声明存在 (设置菜单「扩展域」段)", () => {
    const line = ROUTES_TSX.split("\n").find(l => l.includes('path="/maint"'));
    expect(line).toBeTruthy();
  });

  it("/knowledge/canvas 路由声明存在 (知识菜单附加视图)", () => {
    const line = ROUTES_TSX.split("\n").find(l => l.includes('path="/knowledge/canvas"'));
    expect(line).toBeTruthy();
  });

  it("menuOf() 识别 /maint → settings", () => {
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/maint['"]\)/);
  });

  it("MaintPage 走 /api/maintenance/* 真实端点 (4 工具卡映射)", () => {
    const maint = readFileSync(join(ROOT, "src/components/MaintPage.tsx"), "utf-8");
    expect(maint).toMatch(/\/api\/maintenance\/health/);
    expect(maint).toMatch(/\/api\/maintenance\/backup-verify/);
    expect(maint).toMatch(/\/api\/maintenance\/vacuum/);
    expect(maint).toMatch(/\/api\/maintenance\/cleanup/);
  });

  it("KnowledgeCanvasPage 用 ECharts roam + draggable (纯前端 demo)", () => {
    const canvas = readFileSync(join(ROOT, "src/components/KnowledgeCanvasPage.tsx"), "utf-8");
    expect(canvas).toMatch(/roam:\s*true/);
    expect(canvas).toMatch(/draggable:\s*true/);
    expect(canvas).toMatch(/DEMO_NODES|DEMO_EDGES/);
  });
});

describe("NAV4 §5: menuOf 全分支归属守卫 (21 个未测分支)", () => {
  // 文本层断言: SentinelShell.tsx 必须显式包含对应 startsWith 分支.
  // 运行时层由 SentinelShell.test.tsx 已有的 /settings /action /todos 覆盖 (运行时行为验证).

  it("knowledge 分支覆盖 /knowledge /deep /reviews /tags /extract /search /dashboard /skill-store", () => {
    // line 162: /knowledge /deep /reviews → knowledge
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/knowledge['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/deep['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/reviews['"]\)/);
    // line 167: /tags /extract /search /dashboard /skill-store → knowledge
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/tags['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/extract['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/search['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/dashboard['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/skill-store['"]\)/);
  });

  it("action 分支覆盖 /action /garden /report /todos", () => {
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/action['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/garden['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/report['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/todos['"]\)/);
  });

  it("settings 分支覆盖 /settings /secrets /sync /skills /codegarden /maint", () => {
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/settings['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/secrets['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/sync['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/skills['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/codegarden['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/maint['"]\)/);
  });

  it("data 分支覆盖 / /judge /cases /history /quality", () => {
    // line 161: / /judge /cases → data
    expect(SHELL_TSX).toMatch(/pathname\s*===\s*['"]\/['"]/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/judge['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/cases['"]\)/);
    // line 168: /quality /history → data
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/quality['"]\)/);
    expect(SHELL_TSX).toMatch(/startsWith\(['"]\/history['"]\)/);
  });

  it("secnews 子视图 4 归属: feed/pipeline/analytics→data, knowledge→knowledge, analyze→action, observability→settings", () => {
    // 4 个子字符串必须存在 (顺序不强制, 文本层断言)
    expect(SHELL_TSX).toMatch(/feed['"]\s*\|\|\s*sub\s*===\s*['"]pipeline['"]\s*\|\|\s*sub\s*===\s*['"]analytics['"]/);
    expect(SHELL_TSX).toMatch(/sub\s*===\s*['"]knowledge['"]/);
    expect(SHELL_TSX).toMatch(/sub\s*===\s*['"]analyze['"]/);
    expect(SHELL_TSX).toMatch(/sub\s*===\s*['"]observability['"]/);
  });

  it("/oauth-callback 等未命中路径 → menuOf 返回 null (兜底分支)", () => {
    // menuOf 末尾必须是 `return null;` 而不是 `return undefined;` 或 `return 'data';`
    expect(SHELL_TSX).toMatch(/return\s+null\s*;?\s*\n\s*\}\s*\n/);
  });
});
