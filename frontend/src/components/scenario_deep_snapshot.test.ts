/**
 * v0.7.4-image (S10) — snapshot test: 两处 evaluate 调用方源码 body 含 scenario='deep'.
 *
 * 不用 mock fetch (SentinelJudgePage / SecNewsAnalyze 两个组件树太重,
 * 启动成本大于快照价值)。直接用 fs.readFileSync 读源文件 + 正则断言
 * 'scenario: \\'deep\\'' 字面量在 fetch body 里。
 *
 * 这等于把"前端两处 evaluate 调用都接了场景路由"作为代码契约:
 * 任何人改回去 (删 scenario 字段) 测试就挂, 等于强制 code review 关。
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// __dirname = .../frontend/src/components, ../../ = repo root
const REPO = resolve(__dirname, '../..');

describe('v0.7.4-image scenario=deep 注入契约', () => {
  it('SentinelJudgePage evaluate 调用 body 含 scenario: \'deep\'', () => {
    const src = readFileSync(
      resolve(REPO, 'src/components/sentinel/SentinelJudgePage.tsx'),
      'utf-8',
    );
    expect(src).toMatch(/JSON\.stringify\(\s*\{[^}]*scenario:\s*'deep'[^}]*\}\s*\)/);
  });

  it('SecNewsAnalyze evaluate 调用 body 含 scenario: \'deep\'', () => {
    const src = readFileSync(
      resolve(REPO, 'src/components/secnews/analyze/SecNewsAnalyze.tsx'),
      'utf-8',
    );
    expect(src).toMatch(/JSON\.stringify\(\s*\{[^}]*scenario:\s*'deep'[^}]*\}\s*\)/);
  });
});
