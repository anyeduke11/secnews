/**
 * v0.7.4-image (S10) — snapshot test: evaluate 调用方源码 body 含 scenario='deep'.
 *
 * 不用 mock fetch (SecNewsAnalyze 组件树太重, 启动成本大于快照价值)。
 * 直接用 fs.readFileSync 读源文件 + 正则断言 'scenario: 'deep'' 字面量
 * 在 fetch body 里。
 *
 * 这等于把"前端 evaluate 调用接了场景路由"作为代码契约:
 * 任何人改回去 (删 scenario 字段) 测试就挂, 等于强制 code review 关。
 *
 * P0-8/E10 (2026-10-02): SentinelJudgePage 用例随组件物理删除移除
 * (NAV4 后 /judge 恒 redirect, 组件 563 行不可达)。
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// __dirname = .../frontend/src/components, ../../ = repo root
const REPO = resolve(__dirname, '../..');

describe('v0.7.4-image scenario=deep 注入契约', () => {
  it('SecNewsAnalyze evaluate 调用 body 含 scenario: \'deep\'', () => {
    const src = readFileSync(
      resolve(REPO, 'src/components/secnews/analyze/SecNewsAnalyze.tsx'),
      'utf-8',
    );
    // Batch 5 裸 fetch 清扫: 该调用改走 postJSON (内部仍 JSON.stringify),
    // 契约不变 — 断言 scenario: 'deep' 字面量仍在 evaluate 调用 body 对象里
    expect(src).toMatch(/JSON\.stringify\(\s*\{[^}]*scenario:\s*'deep'[^}]*\}\s*\)|postJSON\(\s*'\/api\/llm\/evaluate'\s*,\s*\{[^}]*scenario:\s*'deep'[^}]*\}/);
  });
});
