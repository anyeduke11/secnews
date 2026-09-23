# 设置页结构化重构 · 三期实施计划 (Settings IA Refactor Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 [设计稿](../specs/2026-09-22-settings-refactor-design.md) 把 `/settings` 从 17 cat 收敛为 7 cat / 5 组的纯配置心智页面，同步修复 4 个后端病灶并治理 settings 表 namespace。

**Architecture:** 三期独立交付独立回归 — P1 前端 IA 重组（17→7 cat、删 8 组件、redirect 更新）；P2 后端修正（MCP 自锁解除 + toggle 持久化 + features 单源 + 能力开关端点 + settings_service）；P3 settings 表 namespace 治理（prefix 契约 + webhook.secret 迁加密存储 + sync bundle 白名单化，不拆表）。

**Tech Stack:** React 18 + TS + Vitest（colocated test）；FastAPI + SQLite（settings KV 表）；feature_gates.toml（16 gate，5s TTL 热重载）；Fernet 加密体系（llm_secrets/encryption_keys）。

**守卫基线（开工前必读）:**
- api 行数门：`backend/tests/test_api_layer_guard.py` `_LINE_EXEMPTIONS` — `settings.py: 304`（实测 303，余量 1）、`mcp.py` 无豁免（150=上限，只能减不能加）；`_registry.py: 271`（实测 271，**净零行增**）。
- 架构数字门：`python scripts/generate_meta.py --check` — 当前 87 routers / 147 services；P2 完成后预计 89 / 148，须同批同步 ARCHITECTURE.md + 根/api/services/scripts 四个 AGENTS.md + CLAUDE.md。
- 前端守卫：`routes/__tests__/nav4_shell.test.tsx` 锁定 /settings 路由与 menuOf。
- 环境命令：后端 `.venv/bin/python3 -m pytest backend/tests/ -q`；前端 `cd frontend && npx tsc --noEmit && npx vitest run`。python 用 `.venv/bin/python3`（系统无 python）。

---

# Phase 1 (P1) — 前端 IA 重组

### Task 1: sections.tsx 重写（17 cat → 7 cat）

**Files:**
- Modify: `frontend/src/components/settings/sections.tsx`（全文件重写，189 行 → ~110 行）

- [ ] **Step 1: 重写 SectionKey / 分组 / SECTIONS**

```tsx
/**
 * settings/sections — 设置页面区段定义 (2026-09-22 IA 重构: 17 cat → 7 cat / 5 组)
 *
 * 第一性原理: 设置页 = 用户对系统可持久化偏好的低频写入口。
 * 只读监控/数据浏览/一次性动作已按裁决迁出或删除 (见设计稿 §2)。
 *
 * overview   — 总览: 体检 + 版本/运行状态 + 跳转 (原 dashboard+about)
 * general    — 通用: 主题/模式/刷新/兴趣画像/能力开关 (原 general + sentinel tab2)
 * models     — 模型配置: LLM Provider/密钥/模型池/三场景 (新, 收 image_models+pipeline 模型部分)
 * collection — 采集与管线: 信源/质量规则/调度/KL 队列/资讯门禁
 * network    — 网络: 代理
 * connectivity — 集成与凭据: 同步/MCP/密钥状态
 * ops        — 运维: 维护/导出动作/dsh 启停
 *
 * 旧 cat 映射: dashboard→overview · image_models/pipeline(模型)→models · pipeline(队列)→collection
 *             sync/integration/secrets→connectivity · maintenance/export→ops · about→overview
 *             sentinel→general(能力开关) · feedback/knowledge/alerts→已删除
 */
import React from 'react';
import { Icon } from '../Icon';

export type SectionKey =
  | 'overview'
  | 'general'
  | 'models'
  | 'collection'
  | 'network'
  | 'connectivity'
  | 'ops';

export interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  desc?: string;
  layout?: 'form' | 'mixed';
  group: SectionGroup;
}

export type SectionGroup = 'overview' | 'general' | 'system' | 'connectivity' | 'ops';

export const SECTION_GROUP_LABELS: Array<{ group: SectionGroup; label: string }> = [
  { group: 'overview', label: '' },
  { group: 'general', label: '通用偏好' },
  { group: 'system', label: '系统配置' },
  { group: 'connectivity', label: '连接与凭据' },
  { group: 'ops', label: '运维' },
];

export const SECTIONS: SectionDef[] = [
  {
    key: 'overview',
    label: '总览',
    icon: <Icon size={12}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></Icon>,
    desc: '体检 · 版本 · 快速跳转',
    group: 'overview',
  },
  {
    key: 'general',
    label: '通用',
    icon: <Icon size={12}><circle cx="12" cy="12" r="3" /><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" /></Icon>,
    desc: '主题 / 模式 / 能力开关',
    layout: 'mixed',
    group: 'general',
  },
  {
    key: 'models',
    label: '模型配置',
    icon: <Icon size={12}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9z" /><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></Icon>,
    desc: 'LLM Provider / 密钥 / 场景模型',
    layout: 'mixed',
    group: 'system',
  },
  {
    key: 'collection',
    label: '采集与管线',
    icon: <Icon size={12}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></Icon>,
    desc: '信源 / 质量 / KL 队列 / 资讯门禁',
    layout: 'mixed',
    group: 'system',
  },
  {
    key: 'network',
    label: '网络',
    icon: <Icon size={12}><path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><circle cx="12" cy="20" r="1" /></Icon>,
    desc: '代理 / 连接',
    group: 'connectivity',
  },
  {
    key: 'connectivity',
    label: '集成与凭据',
    icon: <Icon size={12}><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>,
    desc: '同步 / MCP / 主密钥',
    group: 'connectivity',
  },
  {
    key: 'ops',
    label: '运维',
    icon: <Icon size={12}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a2 2 0 0 1 7.94-7.94l-3.76 3.76z" /></Icon>,
    desc: '维护 / 导出 / dsh 启停',
    group: 'ops',
  },
];
```

- [ ] **Step 2: 类型检查确认无其他文件因 SectionKey 收窄而报错前，先跑 tsc 收集破坏面**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: 一批 TS 错误（SettingsPage switch 的旧 case、SettingsDashboard QUICK_JUMPS 引用已删 cat 等）— 这是 Task 2/3 的工作清单，记录下来。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/sections.tsx
git commit -m "refactor(settings): sections 17 cat -> 7 cat / 5 组 (P1 Task 1)"
```

### Task 2: SettingsPage 装配更新

**Files:**
- Modify: `frontend/src/components/settings/SettingsPage.tsx`（217 行 → ~150 行）

- [ ] **Step 1: 更新 import 块** — 删除 `ModeSwitcher` 之外的已删组件导入将在 Task 9 处理；本 Task 只改装配。新 import：

```tsx
import { ModeSwitcher } from './ModeSwitcher';
import { GeneralSettings } from './GeneralSettings';
import { PracticeDomainsCard } from './PracticeDomainsCard';
import { FeatureGatesCard } from './FeatureGatesCard';       // Task 5 新建
import { ModelsSettings } from './ModelsSettings';            // Task 4 新建
import { CollectionScheduleInfo } from './CollectionScheduleInfo';
import { QualitySettings } from './QualitySettings';
import { SourceSettings } from './SourceSettings';
import { KLQueueCard } from './KLQueueCard';                  // Task 6 新建
import { InfoFilterCard } from '../secnews/settings/InfoFilterCard';
import { ProxySettings } from './ProxySettings';
import { SyncSettings } from './SyncSettings';
import { MCPSettingsCard } from './MCPSettingsCard';
import { SecretsStatusCard } from './SecretsStatusCard';
import { DatabaseMaintenance } from './DatabaseMaintenance';
import { ExportActionsCard } from './ExportActionsCard';      // Task 7 新建
import { DshControlCard } from '../secnews/settings/DshControlCard';
import { SettingsDashboard } from './SettingsDashboard';
import { useFeatureFlags } from '../../hooks/useFeatureFlags';
```

- [ ] **Step 2: 重写 renderContent switch**（默认落 overview；未知 cat 由 `SECTIONS.some` 校验已兜底）

```tsx
  const renderContent = () => {
    switch (activeSection) {
      case 'overview':
        return <SettingsDashboard onJump={setActiveSection} />;
      case 'general':
        return (
          <div className="space-y-2">
            <ModeSwitcher />
            <GeneralSettings theme={theme} onThemeChange={setThemeMode} />
            <PracticeDomainsCard />
            <FeatureGatesCard />
          </div>
        );
      case 'models':
        return <ModelsSettings />;
      case 'collection':
        return (
          <div className="space-y-2">
            <CollectionScheduleInfo />
            <QualitySettings open={open} />
            <SourceSettings open={open} />
            <KLQueueCard />
            <InfoFilterCard />
          </div>
        );
      case 'network':
        return <ProxySettings open={open} />;
      case 'connectivity':
        return (
          <div className="space-y-2">
            <SyncSettings />
            {features.mcp ? <MCPSettingsCard open={open} /> : (
              <div className="st-info">MCP 扩展未启用（可在「通用 → 能力开关」开启后重启生效）</div>
            )}
            <SecretsStatusCard />
          </div>
        );
      case 'ops':
        return (
          <div className="space-y-2">
            <DatabaseMaintenance />
            <ExportActionsCard />
            <DshControlCard />
          </div>
        );
    }
  };
```

同时把头部副标题默认文案改为 `'系统设置 · 配置中心'`，注释中 "16/17 cat" 字样更新为 7 cat。

- [ ] **Step 3: Commit**（此时尚未编译通过 — FeatureGatesCard/KLQueueCard/ModelsSettings/ExportActionsCard 待建，与 Task 4-7 合并验证）

```bash
git add frontend/src/components/settings/SettingsPage.tsx
git commit -m "refactor(settings): SettingsPage 装配 7 cat (P1 Task 2)"
```

### Task 3: FeatureGatesCard（能力开关，P1 先只读 + 数据源换新端点留 P2 接线）

**Files:**
- Create: `frontend/src/components/settings/FeatureGatesCard.tsx`
- Test: `frontend/src/components/settings/FeatureGatesCard.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
/**
 * FeatureGatesCard — 能力开关卡测试
 * 意图: 16 gate 从 /api/settings/features 只读呈现 (P1); P2 的 PUT 端点就绪后接通 toggle。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { FeatureGatesCard } from './FeatureGatesCard';

const FEATURES = {
  codegarden: true, codegarden_phase2b: true, sync: true, tech_stack: true,
  security_graph: true, secnews: true, dsh: true, info_filter: true,
  skill_registry: true, trigger_gate: true, user_skills: true,
  interest_engine: true, semantic_filter: true, ai_classify: true,
  pipeline_ner: true, mcp: false,
};

describe('FeatureGatesCard — 能力开关 (只读期)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/settings/features')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(FEATURES) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染 16 个 gate 与启停状态, mcp=false 显示已停用', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => expect(screen.getByText('能力开关')).toBeInTheDocument());
    expect(screen.getByText('secnews')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('mcp')).toBeInTheDocument());
    // 16 行
    await waitFor(() => {
      const rows = screen.getAllByRole('switch');
      expect(rows).toHaveLength(16);
    });
  });

  it('P1 阶段开关为只读 (disabled), 提示来源', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => {
      const sw = screen.getAllByRole('switch')[0] as HTMLButtonElement;
      expect(sw.disabled).toBe(true);
    });
    expect(screen.getByText(/feature_gates\.toml/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败** — `cd frontend && npx vitest run src/components/settings/FeatureGatesCard.test.tsx` → FAIL (模块不存在)

- [ ] **Step 3: 实现组件**

```tsx
/**
 * FeatureGatesCard — 能力开关 (原 sentinel 只读控制台 Tab2 可写化第一期)
 *
 * P1: 16 gate 全量只读呈现 (数据源 GET /api/settings/features, P2 起键从
 * extensions 白名单单源派生); toggle disabled, 注明 TOML 来源与重启语义。
 * P2: /api/settings/feature-gates/{name} PUT 就绪后接通 toggle (env 覆盖时 409 提示)。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';

type FeatureMap = Record<string, boolean>;

const GATE_DESCS: Record<string, string> = {
  secnews: '情报核心: 三层工作流/判读台/知识管线',
  codegarden: '代码花园视图',
  codegarden_phase2b: 'CodeGarden 运维层 (服务网格/资源中枢)',
  mcp: 'MCP 工具面 (agent 适配端点)',
  sync: 'WebDAV 跨设备同步',
  tech_stack: '技术栈图谱',
  security_graph: 'ATT&CK / CVE 安全图谱',
  dsh: 'dsh 认知大脑 (受管子进程)',
  info_filter: '独立资讯筛选门禁',
  skill_registry: 'Skill 商店',
  trigger_gate: '触发源门禁 (webhook/KL/collector)',
  user_skills: '用户自建 Skill',
  interest_engine: '兴趣引擎 (行为信号+域权重)',
  semantic_filter: '语义筛选',
  ai_classify: 'AI 分类',
  pipeline_ner: '管线 NER 实体抽取',
};

export function FeatureGatesCard() {
  const [features, setFeatures] = useState<FeatureMap | null>(null);

  useEffect(() => {
    let dead = false;
    getJSON<FeatureMap>('/api/settings/features')
      .then(d => { if (!dead) setFeatures(d ?? {}); })
      .catch(() => { if (!dead) setFeatures({}); });
    return () => { dead = true; };
  }, []);

  const keys = Object.keys(GATE_DESCS);

  return (
    <div className="st-card">
      <h3>能力开关</h3>
      <p className="st-section-desc">
        源：<code className="st-code">backend/config/feature_gates.toml</code>。
        改动经 TOML 写入后 5s 内影响运行时读数；路由注册与定时任务需重启后端生效。
      </p>
      {features === null ? (
        <p className="st-cellnote">载入中…</p>
      ) : keys.length === 0 ? (
        <p className="st-cellnote">未能读取能力开关 — 后端不可达时不显示默认值，以免误判。</p>
      ) : (
        <div className="st-rule-list">
          {keys.map(k => {
            const on = Boolean(features[k]);
            return (
              <div className="st-rule" key={k}>
                <div>
                  <p className="st-label">{k}</p>
                  <p className="st-fcode">{GATE_DESCS[k]}</p>
                </div>
                <div className="st-ctrl">
                  <button
                    type="button"
                    className="st-switch"
                    role="switch"
                    aria-checked={on}
                    disabled
                    aria-label={`${k}：${on ? '已启用' : '已停用'}（只读）`}
                  />
                  <span className={`st-chip${on ? ' ok' : ''}`}><i aria-hidden />{on ? 'ON' : 'OFF'}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 跑测试通过** — 同 Step 2 命令 → PASS。注意: 16 键来自 GATE_DESCS 常量而非响应（响应可能缺键），测试断言 `toHaveLength(16)` 依赖此实现。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/FeatureGatesCard.tsx frontend/src/components/settings/FeatureGatesCard.test.tsx
git commit -m "feat(settings): FeatureGatesCard 能力开关卡 (P1 Task 3, 只读期)"
```

### Task 4: ModelsSettings 装配组件（模型配置唯一入口）

**Files:**
- Create: `frontend/src/components/settings/ModelsSettings.tsx`
- Test: `frontend/src/components/settings/ModelsSettings.test.tsx`

- [ ] **Step 1: 写失败测试**（断言装配: ProviderPanel + SecretsPanel + 模型池状态 + ScenarioModelsPanel 各渲染一次；模型池卡消费 /api/llm/status）

```tsx
/**
 * ModelsSettings — 模型配置区装配测试
 * 意图: LLM 模型配置唯一入口 — Provider / 密钥 / 模型池 / 三场景四卡齐全, 不重复渲染。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ModelsSettings } from './ModelsSettings';

const LLM_STATUS = {
  enabled: true, scenario: 'deep',
  providers: { deepseek: { status: 'ok', model: 'deepseek-v4-pro' } },
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/llm/status')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LLM_STATUS) } as Response);
    }
    if (url.startsWith('/api/secrets/status')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ initialized: true, unlocked: false }) } as Response);
    }
    if (url.startsWith('/api/secrets')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('ModelsSettings — 模型配置区', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('装配四卡: Provider / 密钥 / 模型池 / 三场景, 各一次', async () => {
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText('模型池')).toBeInTheDocument());
    expect(screen.getByText(/deepseek-v4-pro/)).toBeInTheDocument();
    // 子面板标题存在且各一个 (ProviderPanel/SecretsPanel 自带标题)
    expect(screen.getAllByText(/Provider/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/场景/).length).toBeGreaterThanOrEqual(1);
  });

  it('模型池卡: llm 不可达时如实空态', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response)));
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText(/模型状态不可用/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 跑测试确认失败** — 模块不存在。

- [ ] **Step 3: 实现** — 薄装配壳（复用既有 quality/ 面板，**不复制逻辑**）：

```tsx
/**
 * ModelsSettings — 模型配置区 (2026-09-22 IA 重构: LLM 配置唯一入口)
 *
 * 装配: ProviderPanel (provider 切换) + SecretsPanel (LLM 密钥 CRUD)
 *      + LlmPoolCard (模型池状态, 自 /api/llm/status) + ScenarioModelsPanel (三场景)。
 * 来源: 原 collection 内嵌 Provider/Secrets 面板 + pipeline 模型档位 + image_models cat, 按裁决归一。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';
import { ProviderPanel } from './quality/ProviderPanel';
import { SecretsPanel } from './quality/SecretsPanel';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';

interface LLMStatus {
  enabled?: boolean;
  providers?: Record<string, { status?: string; model?: string }>;
}

function LlmPoolCard() {
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  useEffect(() => {
    let dead = false;
    getJSON<LLMStatus>('/api/llm/status').catch(() => null).then(d => { if (!dead) setLlm(d); });
    return () => { dead = true; };
  }, []);
  const providers = Object.entries(llm?.providers ?? {});
  return (
    <div className="st-card">
      <h3>模型池</h3>
      <p className="st-section-desc">已配置 provider 的实时状态（来源 /api/llm/status）。</p>
      {providers.length === 0 ? (
        <p className="st-cellnote">模型状态不可用 — 后端不可达或未配置 provider。</p>
      ) : (
        <div className="st-rule-list">
          {providers.map(([name, p]) => (
            <div className="st-rule" key={name}>
              <div><p className="st-label">{name}</p></div>
              <div className="st-ctrl">
                <span className={`st-chip${p.status === 'ok' ? ' ok' : ' bad'}`}>
                  <i aria-hidden />{p.model ?? name} [{p.status ?? '?'}]
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ModelsSettings() {
  return (
    <div className="space-y-2">
      <ProviderPanel />
      <SecretsPanel />
      <LlmPoolCard />
      <ScenarioModelsPanel scope="settings-models" compact />
    </div>
  );
}
```

- [ ] **Step 4: 跑测试** — 若子面板实际标题与断言文案不符，以真实渲染为准修正断言文案（断言意图不变：四卡各一次、空态如实）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ModelsSettings.tsx frontend/src/components/settings/ModelsSettings.test.tsx
git commit -m "feat(settings): ModelsSettings 模型配置唯一入口 (P1 Task 4)"
```

### Task 5: QualitySettings 瘦身 + KLQueueCard 拆出

**Files:**
- Modify: `frontend/src/components/settings/QualitySettings.tsx`（移除 ProviderPanel/SecretsPanel 装配，保留规则+LLM 检测；删除 "与 /settings?cat=image_models 同源" 文案行）
- Create: `frontend/src/components/settings/KLQueueCard.tsx`（自 PipelineSettings L86-108 + L111-146 抽取 KL 队列 section，模型档位 section **不搬**（归 models，由 LlmPoolCard 覆盖））
- Test: `frontend/src/components/settings/KLQueueCard.test.tsx`

- [ ] **Step 1: 写 KLQueueCard 失败测试**

```tsx
/** KLQueueCard — KL 队列只读卡 (自 PipelineSettings 拆出) */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { KLQueueCard } from './KLQueueCard';

describe('KLQueueCard — KL 队列卡', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/secnews/pipeline')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ queue: { pending: 3, running: 1, error: 2 } }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染 pending/running/error 三格', async () => {
    render(<KLQueueCard />);
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 确认失败** → **Step 3: 实现**（把 PipelineSettings 的 KL section 逐字搬入，包 st-card 壳，自取 `getSecNewsPipeline`）：

```tsx
/** KLQueueCard — KL 管线队列只读卡 (原 pipeline cat 拆出, 数据 GET /api/secnews/pipeline) */
import { useCallback, useEffect, useState } from 'react';
import { getSecNewsPipeline } from '../../api/secnews';

interface PipelineStats { queue?: { pending?: number; running?: number; error?: number } }

export function KLQueueCard() {
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const refresh = useCallback(async () => {
    try { setPipeline(await getSecNewsPipeline<PipelineStats>()); } catch { setPipeline(null); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const q = pipeline?.queue;
  const cells = [
    ['pending', '待处理', 'mint'], ['running', '进行中', 'mint'], ['error', '失败', 'red'],
  ] as const;
  return (
    <div className="st-card">
      <h3>KL 管线队列</h3>
      <p className="st-section-desc">raw → chunk → score → rank 多阶段管线的运行队列与心跳。</p>
      {q ? (
        <div className="st-cellgrid">
          {cells.map(([key, label, color]) => (
            <div key={key} className="st-cell">
              <span className="st-cellk">{label}</span>
              <span className={`st-cellv sm ${color}`}>{q[key] ?? 0}</span>
            </div>
          ))}
        </div>
      ) : <p className="st-cellnote">队列状态不可用。</p>}
    </div>
  );
}
```

- [ ] **Step 4: QualitySettings 瘦身** — 删除其渲染树中 `<ProviderPanel />` 与 `<SecretsPanel />` 及对应 import；删除 L84 附近 "三场景模型选择 — 与 /settings?cat=image_models 同源" 描述行。同步修正 `QualitySettings.test.tsx` 中因面板迁出而失效的用例（迁往 ModelsSettings 的断言删除，规则/LLM 检测断言保留）。
- [ ] **Step 5: 跑测试** — `cd frontend && npx vitest run src/components/settings/KLQueueCard.test.tsx src/components/settings/QualitySettings.test.tsx` → PASS。
- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings/KLQueueCard.tsx frontend/src/components/settings/KLQueueCard.test.tsx frontend/src/components/settings/QualitySettings.tsx frontend/src/components/settings/QualitySettings.test.tsx
git commit -m "refactor(settings): QualitySettings 瘦身 + KLQueueCard 拆出 (P1 Task 5)"
```

### Task 6: ExportActionsCard（导出动作卡）

**Files:**
- Create: `frontend/src/components/settings/ExportActionsCard.tsx`（ExportSettings 内容改为 st-card 语义的运维动作卡：HTML/XLSX window.open + 「去报告页」navigate；不保留独立 cat）
- Test: `frontend/src/components/settings/ExportActionsCard.test.tsx`（断言两个导出 href 与跳转按钮；无 API 请求）

- [ ] **Step 1: 写失败测试**

```tsx
/** ExportActionsCard — 导出动作卡 (原 export cat, 一次性动作归运维) */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExportActionsCard } from './ExportActionsCard';

describe('ExportActionsCard — 导出动作卡', () => {
  it('提供 HTML/XLSX 两个导出入口与报告页跳转', () => {
    render(<MemoryRouter><ExportActionsCard /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /HTML 报告/ })).toHaveAttribute('href', '/api/export');
    expect(screen.getByRole('link', { name: /XLSX/ })).toHaveAttribute('href', '/api/export/xlsx');
    expect(screen.getByRole('link', { name: /报告页/ })).toHaveAttribute('href', '/report');
  });
});
```

- [ ] **Step 2: 确认失败** → **Step 3: 实现**（`<a href="/api/export" download>` 两个链接 + `<Link to="/report">`；导出由浏览器直下，不用 window.open）→ **Step 4: 跑测试 PASS** → **Step 5: Commit** `feat(settings): ExportActionsCard 导出动作卡 (P1 Task 6)`。

### Task 7: SettingsDashboard 总览改造（吸收 About + QUICK_JUMPS 更新）

**Files:**
- Modify: `frontend/src/components/settings/SettingsDashboard.tsx`
  - `QUICK_JUMPS`（L70-79）替换为 6 项指向新 cat：`general`(通用/能力开关)、`models`(模型配置)、`collection`(采集与管线)、`network`(网络)、`connectivity`(集成与凭据)、`ops`(运维)；
  - 追加「版本与运行状态」卡（吸收 AboutSettings：APP_VERSION 来源 — `import.meta.env` 无版本时用 `--`，运行状态复用本组件已拉取的 `/api/health` 的 `ok/uptime_s`；uptime 用既有 `fmtUptime`）；
  - `type SectionKey` import 路径不变（Task 1 已收窄）。
- Modify: `frontend/src/components/settings/SettingsDashboard.test.tsx` — QUICK_JUMPS 断言与新 6 tile 对齐。

- [ ] **Step 1: 更新测试断言**（新 tiles 清单 + 版本卡渲染）；**Step 2: 跑测试 FAIL**；**Step 3: 改造组件**；**Step 4: 跑测试 PASS**；**Step 5: Commit** `refactor(settings): 总览吸收版本卡 + QUICK_JUMPS 7 cat (P1 Task 7)`。

### Task 8: 删除批次 + redirect 更新

**Files:**
- Delete: `frontend/src/components/settings/FeedbackSettings.tsx`、`KnowledgeSettings.tsx`、`AlertSettings.tsx`、`AboutSettings.tsx`、`ExportSettings.tsx`、`secnews/settings/PipelineSettings.tsx`、`secnews/settings/AgentRunnerCard.tsx`、`sentinel/SentinelSettingsPage.tsx`、`sentinel/SentinelSettingsPage.test.tsx`、`sentinel/sentinel-settings.css`、`secnews/ImageStudio.tsx`、`secnews/ImageStudio.test.tsx`
- Modify: `frontend/src/routes/index.tsx:118,234,237` — 三条 redirect：
  - `/sentinel/settings` → `/settings?cat=general`
  - `/secnews/image` → `/settings?cat=models`
  - `/secnews/settings` → `/settings?cat=collection`
- Modify: `frontend/src/routes/ROUTE_REGISTRY.md` L57 附近同步三行。
- 检查残留引用: `grep -rn "SentinelSettingsPage\|AgentRunnerCard\|PipelineSettings\|FeedbackSettings\|KnowledgeSettings\|AlertSettings\|AboutSettings\|ImageStudio\|image_models" frontend/src` → 必须为 0（`ImageStudio` 若被其他页引用则一并处理；`ScenarioModelsPanel.tsx` 头注释 L5 的旧路由说明更新为 models）。

- [ ] **Step 1: 用 DeleteFile 删除上述文件**；**Step 2: 更新 3 条 redirect + ROUTE_REGISTRY.md**；**Step 3: grep 残留清零**；**Step 4: Commit** `refactor(settings): 删除 8 个定位不符组件 + redirect 更新 (P1 Task 8)`。

### Task 9: P1 收口 — 全量前端回归

- [ ] `cd frontend && npx tsc --noEmit` → 0 错
- [ ] `cd frontend && npx vitest run` → 0 失败（SettingsDashboard/QualitySettings/MCPSettingsCard/ProxySettings/PracticeDomainsCard/InfoFilterCard/Nav4 全绿）
- [ ] `cd frontend && npx vite build --logLevel error` → OK
- [ ] Commit（如有修复）`fix(settings): P1 回归修复`

---

# Phase 2 (P2) — 后端修正

### Task 10: mcp_settings_api.py（ungated 设置端点 + toggle 持久化）

**Files:**
- Create: `backend/api/mcp_settings_api.py`
- Test: `backend/tests/test_mcp_settings_api.py`
- Modify: `backend/api/_registry.py`（settings include 旁登记，**净零行增**：与 settings 同一行复合 import 或并入既有行）
- Modify: `backend/api/mcp.py`（删除 L110-147 两个端点 + `ToggleEnabledRequest` + `enable/disable` import，150→~95 行）

- [ ] **Step 1: 写失败测试**

```python
"""mcp_settings_api — ungated MCP 设置端点测试 (migration: 自锁解除 + 持久化)。

验收 (设计稿 §4.1/4.2):
- extensions.mcp=false (TOML 默认) 时 PUT /api/settings/mcp/enabled 仍 200 — 不再自锁
- enable 写 settings kv feature.mcp_server (重启回读), 响应 note 如实
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp_settings.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    # 关键: 不 monkeypatch extensions.mcp=true — 默认 gate=false 下端点必须可达
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestMcpSettingsUngated:
    def test_put_enabled_reachable_when_gate_off(self, client, monkeypatch):
        monkeypatch.setattr(config, "feature_mcp", True)
        r = client.put("/api/settings/mcp/enabled", json={"enabled": False})
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["persisted"] is True
        assert "重启" not in body["note"]  # server 开关立即生效, note 不再误导

    def test_toggle_persists_to_settings_kv(self, client, monkeypatch):
        monkeypatch.setattr(config, "feature_mcp", True)
        client.put("/api/settings/mcp/enabled", json={"enabled": False})
        from backend.repository.settings_repo import SettingsRepository
        assert SettingsRepository().get("feature.mcp_server") is False

    def test_get_config_still_gated_404(self, client):
        # 读配置依赖 MCP server 本体, gate=false → 404 (与旧契约一致)
        r = client.get("/api/settings/mcp/config")
        assert r.status_code == 404
```

- [ ] **Step 2: 跑测试 FAIL**（端点 404 — 现由 gated mcp.py 承载且 toggle 无 persisted 字段）

- [ ] **Step 3: 新建 `backend/api/mcp_settings_api.py`**（路由清单注释 + ≤150 行）

```python
"""MCP 设置 API (ungated 基础设施, 2026-09-22 设置重构 P2)。

路由清单
--------
- ``GET /api/settings/mcp/config``    stdio/SSE 配置 (依赖 server 本体, feature_mcp=false 时 404)
- ``PUT /api/settings/mcp/enabled``   切换 feature.mcp_server — 立即生效 + settings kv 持久化

背景: 原两端点住在 gated mcp.py (extensions.mcp TOML 默认 false → 404),
UI 永远无法开启 MCP 的自锁; toggle 且只改进程内单例重启即丢。本文件双修。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import config
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/settings", tags=["mcp-settings"])


class ToggleEnabledRequest(BaseModel):
    enabled: bool = Field(..., description="true=启用, false=停用 MCP server")


def _toggle(enabled: bool) -> dict:
    from backend.services.feature_flag_service import enable, disable

    ok = enable("mcp") if enabled else disable("mcp")
    if not ok:
        raise HTTPException(status_code=400, detail={"message": "未知 feature flag: mcp"})
    return {
        "version": API_VERSION,
        "enabled": enabled,
        "applied": ok,
        "persisted": True,
        "note": "MCP server 开关已立即生效并持久化; /api/mcp/* 调试路由随 extensions.mcp TOML gate 重启生效",
    }


@router.get("/mcp/config")
async def get_mcp_config():
    """MCP 端点 + AI Agent settings.json 示例 (server 本体关闭时 404)。"""
    from backend.api.mcp import build_mcp_config_payload

    if not config.feature_mcp:
        raise HTTPException(status_code=404, detail={"message": "MCP server is disabled"})
    return await asyncio.to_thread(build_mcp_config_payload)


@router.put("/mcp/enabled")
async def toggle_mcp_enabled(req: ToggleEnabledRequest):
    """切换 feature.mcp_server (立即生效 + 持久化)。"""
    return await asyncio.to_thread(_toggle, req.enabled)


__all__ = ["router"]
```

- [ ] **Step 4: mcp.py 改造** — 把 `_build_stdio_config/_build_sse_config` 与工具清单组装抽为模块级函数 `build_mcp_config_payload() -> dict`（原 get_mcp_config L111-132 函数体迁入，去掉路由装饰器与 `is_mcp_enabled` 判断）；删除 `GET /settings/mcp/config`、`PUT /settings/mcp/enabled`、`ToggleEnabledRequest` 及 `enable/disable` import；`feature_flag_service` import 若仅为此两处使用则一并清理；头部路由清单注释同步。

- [ ] **Step 5: feature_flag_service enable/disable 持久化**（`backend/services/feature_flag_service.py`）

```python
def disable(name: str) -> bool:
    """运行时关闭某 flag: config 单例立即生效 + settings kv 持久化 (重启回读)。"""
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, False)
    _persist(name, False)
    return True


def enable(name: str) -> bool:
    """运行时启用某 flag: config 单例立即生效 + settings kv 持久化 (重启回读)。"""
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, True)
    _persist(name, True)
    return True


def _persist(name: str, value: bool) -> None:
    """写 settings kv ``feature.<name>``; 失败仅告警 (即时生效不因持久化失败回滚)。"""
    try:
        from backend.repository.settings_repo import SettingsRepository

        SettingsRepository().set(f"feature.{name}", value)
    except Exception as e:  # pragma: no cover
        logger.warning("feature flag persist failed for %s: %s", name, e)
```

- [ ] **Step 6: main.py 启动回读** — 在 `_apply_persisted_refresh_interval()`（L48-69）之后新增同款函数并调用（scheduler 构造前）：

```python
def _apply_persisted_feature_flags() -> None:
    """设置重构 P2: 回读 API 写入的 feature flag 持久值, 覆盖 config 单例。

    仅覆盖显式写入过的 key (settings kv 存在才 setattr); 读取失败静默走默认。
    """
    try:
        from backend.repository.settings_repo import SettingsRepository

        repo = SettingsRepository()
        for key, value in repo.list_all().items():
            if key.startswith("feature.") and isinstance(value, bool):
                attr = f"feature_{key.removeprefix('feature.')}"
                if hasattr(config, attr):
                    setattr(config, attr, value)
                    log.info("feature flag restored: %s=%s", key, value)
    except Exception as e:  # pragma: no cover
        log.warning(f"persisted feature flags restore failed (ignored): {e}")
```

在 lifespan `init_db()` 之后（原 `_apply_persisted_refresh_interval()` 调用点旁）加 `_apply_persisted_feature_flags()`。

- [ ] **Step 7: _registry.py 登记（净零行增）** — 在 `settings,  # 运行时设置` 行改为 `settings, mcp_settings_api,  # 运行时设置 + MCP 设置 (ungated)`，include 区 settings 行后加 `app.include_router(mcp_settings_api.router, tags=["mcp-settings"])`（同 gate 外，无条件注册）。若行数超 271，删除同文件内其他死注释补偿（与上批同手法）。
- [ ] **Step 8: 跑测试 PASS** — `.venv/bin/python3 -m pytest backend/tests/test_mcp_settings_api.py backend/tests/test_feature_gates.py backend/tests/test_api_layer_guard.py -q`；**Step 9: Commit** `fix(api): MCP 设置端点 ungated + toggle 持久化 (P2 Task 10)`。

### Task 11: settings_flags_api.py — features 单源 + 能力开关读写端点

**Files:**
- Create: `backend/api/settings_flags_api.py`
- Test: `backend/tests/test_settings_flags_api.py`
- Modify: `backend/api/settings.py` — `get_features()`（L34-52）改为从 `backend/extensions.get_all_gates()` 派生（若 extensions 无此函数则新增：返回 `{name: enabled}` 16 键 dict，复用 `_EXTENSION_NAMES` 白名单 + 当前生效值）；`_registry.py` 登记新 router（净零行增手法同 Task 10）。

- [ ] **Step 1: 写失败测试**

```python
"""settings_flags_api — 能力开关读写端点测试 (设计稿 §4.3)。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_settings_flags.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestFeatureGates:
    def test_get_lists_16_gates_with_source(self, client):
        r = client.get("/api/settings/feature-gates")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 16
        item = next(i for i in items if i["name"] == "mcp")
        assert item["source"] in ("default", "toml", "env")
        assert item["effective_scope"] in ("runtime", "startup")

    def test_put_unknown_gate_404(self, client):
        r = client.put("/api/settings/feature-gates/nope", json={"enabled": True})
        assert r.status_code == 404

    def test_put_writes_toml_and_audits(self, client, tmp_path, monkeypatch):
        toml_path = tmp_path / "feature_gates.toml"
        toml_path.write_text('[extensions]\nsecnews = true\nmcp = false\n')
        import backend.extensions as ext
        monkeypatch.setattr(ext, "_GATES_FILE", toml_path)
        r = client.put("/api/settings/feature-gates/mcp", json={"enabled": True})
        assert r.status_code == 200
        assert "mcp = true" in toml_path.read_text()

    def test_put_env_overridden_409(self, client, tmp_path, monkeypatch):
        toml_path = tmp_path / "feature_gates.toml"
        toml_path.write_text('[extensions]\nmcp = false\n')
        import backend.extensions as ext
        monkeypatch.setattr(ext, "_GATES_FILE", toml_path)
        monkeypatch.setenv("HOTSPOT_FEATURE_GATES", '{"extensions":{"mcp":true}}')
        r = client.put("/api/settings/feature-gates/mcp", json={"enabled": False})
        assert r.status_code == 409
        assert "HOTSPOT_FEATURE_GATES" in r.json()["message"]
```

- [ ] **Step 2: FAIL** → **Step 3: 实现 `settings_flags_api.py`**：

```python
"""能力开关 API (2026-09-22 设置重构 P2 §4.3)。

路由清单
--------
- ``GET /api/settings/feature-gates``        16 gate 全量 (name/enabled/source/effective_scope)
- ``PUT /api/settings/feature-gates/{name}`` 写 TOML + audit_log; env 覆盖时 409

source 语义: default=白名单默认 / toml=TOML 显式 / env=HOTSPOT_FEATURE_GATES 覆盖 (TOML 写入无效)。
effective_scope: runtime=5s TTL 热重载即生效 / startup=需重启 (路由注册/job 调度为启动快照)。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/settings", tags=["feature-gates"])

# 路由注册依赖该 gate 的扩展域 (启动快照语义); security_graph 等仅占 job 的 gate 也算 startup
_STARTUP_SCOPED = {
    "codegarden", "codegarden_phase2b", "mcp", "sync", "dsh",
    "secnews", "info_filter", "skill_registry", "user_skills",
    "trigger_gate", "tech_stack",
}


class GateToggleRequest(BaseModel):
    enabled: bool = Field(..., description="true=启用, false=停用")


def _list_gates() -> dict:
    import backend.extensions as ext

    overrides = ext.env_overrides()  # {"extensions": {...}} 或 {}
    env_keys = set((overrides.get("extensions") or {}).keys())
    items = []
    for name in ext.extension_names():
        enabled = ext.is_extension_enabled(name)
        source = "env" if name in env_keys else (
            "toml" if name in ext.toml_explicit_keys() else "default"
        )
        items.append({
            "name": name,
            "enabled": enabled,
            "source": source,
            "effective_scope": "startup" if name in _STARTUP_SCOPED else "runtime",
        })
    return {"version": API_VERSION, "count": len(items), "items": items}


def _set_gate(name: str, enabled: bool) -> dict:
    import backend.extensions as ext

    if name not in ext.extension_names():
        raise HTTPException(status_code=404, detail={"message": f"未知 gate: {name}"})
    if name in (ext.env_overrides().get("extensions") or {}):
        raise HTTPException(
            status_code=409,
            detail={"message": f"{name} 被 HOTSPOT_FEATURE_GATES 环境变量覆盖, TOML 写入无效; 请改 env 后重启"},
        )
    ext.set_toml_gate(name, enabled)  # Task 11 Step 4 新增: 写 TOML (保留其他键)
    from backend.services.audit_service import record_audit

    record_audit(action="feature_gate.set", detail={"gate": name, "enabled": enabled})
    return {"version": API_VERSION, "name": name, "enabled": enabled,
            "note": "运行时读数 5s 内生效; 路由注册与 job 调度需重启后端"}


@router.get("/feature-gates")
async def list_feature_gates():
    return await asyncio.to_thread(_list_gates)


@router.put("/feature-gates/{name}")
async def set_feature_gate(name: str, req: GateToggleRequest):
    return await asyncio.to_thread(_set_gate, name, req.enabled)


__all__ = ["router"]
```

- [ ] **Step 4: extensions 模块补三个查询/写入函数**（`backend/extensions/__init__.py`，各 5-10 行，读 `_load_gates()` 缓存与 `_EXTENSION_NAMES`）：
  - `extension_names() -> list[str]`：返回 `list(_EXTENSION_NAMES)`；
  - `toml_explicit_keys() -> set[str]`：解析 TOML 文件返回显式出现过的键集合；
  - `set_toml_gate(name, enabled)`：读 TOML → 改该键 → 保留其余键写回（`tomllib` 读 + 手写序列化或 `tomli_w` 若已在依赖，否则手拼 `[extensions]` 节；写前 `Path.bak` 备份一次）；
  - `env_overrides()`：返回已解析的 env 覆盖 dict（现有逻辑抽函数复用）。
  - 注意: `record_audit` 实际函数名以 `backend/services/audit_service.py`（或现有 audit 写入点）为准 — 实施时先 `grep -rn "def record_audit" backend/` 对齐签名，`settings.py` L186 已有 `audit_log` 写入先例可照抄。
- [ ] **Step 5: settings.py features 单源** — `get_features()` 函数体替换为：

```python
def get_features() -> dict:
    """扩展域启停运行时视图 — 键从 extensions 16-gate 白名单单源派生 (P2 §4.3)。"""
    import backend.extensions as ext

    gates = {name: ext.is_extension_enabled(name) for name in ext.extension_names()}
    return {**gates, "enabled_extensions": ext.get_enabled_extensions()}
```

- [ ] **Step 6: 跑 PASS**（`test_settings_flags_api.py` + `test_feature_gates.py` + SentinelSettingsPage 已删不影响后端）→ **Step 7: Commit** `feat(api): feature-gates 读写端点 + features 16 键单源 (P2 Task 11)`。

### Task 12: settings_service.py + settings.py 走 service

**Files:**
- Create: `backend/services/settings_service.py`（~60 行：get/set/delete/list_all 转发 SettingsRepository + `set` 记 audit；P3 Task 14 在此加 prefix 契约）
- Modify: `backend/api/settings.py` — `SettingsRepository` 顶层 import（L29）替换为 `settings_service`；各端点调用点同步；行数须 ≤304（豁免上限），超则把 `get_features` 派生逻辑（Task 11 已瘦身）继续下沉 service。
- Test: `backend/tests/test_settings_service.py`（get miss 默认值 / set+audit / 未注册前缀 P3 前放行）

- [ ] **Step 1: 写失败测试** → **Step 2: FAIL** → **Step 3: 实现 service**（转发 + audit；`audit` 调用点签名先 grep 对齐）→ **Step 4: settings.py 切换** → **Step 5: 全量相关 PASS**（`test_settings_service.py test_settings_flags_api.py test_reviews_manage_api.py` + grep `backend/api` 确认 settings.py 不再 import settings_repo）→ **Step 6: Commit** `refactor(api): settings 走 settings_service (P2 Task 12)`。

### Task 13: P2 收口 — 全量回归 + 架构数字同步

- [ ] `.venv/bin/python3 -m pytest backend/tests/ -q --tb=short` → 0 失败
- [ ] `.venv/bin/python3 scripts/generate_meta.py --check` → 预期 MISMATCH (89 routers / 148 services)
- [ ] 同步：ARCHITECTURE.md（3 处数字 + 迁移号）、根/api/services/scripts AGENTS.md、CLAUDE.md（87→89 / 147→148）
- [ ] `.venv/bin/python3 scripts/generate_meta.py --check` → OK；`ruff check backend/api/mcp_settings_api.py backend/api/settings_flags_api.py backend/services/settings_service.py backend/services/feature_flag_service.py backend/api/settings.py backend/api/mcp.py`
- [ ] Commit `chore(meta): 架构数字同步 89 routers / 148 services (P2 Task 13)`

---

# Phase 3 (P3) — settings 表 namespace 治理

### Task 14: prefix 契约（fail-loud）

**Files:**
- Modify: `backend/services/settings_service.py` — `set()` 加 `_ALLOWED_PREFIXES` 校验：

```python
# settings 表 namespace 契约 (2026-09-22 P3): 写入必须落在已注册前缀内。
# state.* = 运行状态例外清单 (mitre 同步位点/dsh 模式等既有 key, 只读迁移不硬改)。
_ALLOWED_PREFIXES = (
    "collection.", "llm.", "interest.", "quality.", "feature.",
    "feature-gates.", "state.", "secrets.oauth_allowlist",
)
_DISALLOWED_EXACT = set()  # webhook.secret 在 Task 15 迁移后加入此处

def set(self, key: str, value) -> None:
    if key != "secrets.oauth_allowlist" and not key.startswith(_ALLOWED_PREFIXES):
        raise InvalidParamException(
            f"settings key '{key}' 不在注册前缀内; 新 key 须先在本契约登记 (设计稿 §5)"
        )
    ...
```

（`InvalidParamException` 从 `backend.exceptions` import；`_DISALLOWED_EXACT` 在 Task 15 完成迁移后填入 `{"webhook.secret"}`。）

- Test: `backend/tests/test_settings_service.py` 追加：写入 `webhook.subject`（未注册前缀）→ raises；写入 `state.mitre.synced_at` → OK；`secrets.oauth_allowlist` → OK。
- [ ] Steps: 测试先行 → FAIL → 实现 → PASS → Commit `feat(settings): settings kv namespace 契约 fail-loud (P3 Task 14)`。

### Task 15: webhook.secret 迁加密存储

**背景（实施必读）**: 现读点 `backend/services/trigger_gate/triggers/webhook.py:45` `from backend.services.settings_kv import SettingsRepository` — **该模块不存在**，import 失败被 `except Exception: return None` 吞掉，即生产默认路径签名校验从未生效（潜在 bug，本 Task 一并修复）。明文现状写入方：人工经 settings API/SQL 写入 `webhook.secret`。

**Files:**
- Modify: `backend/services/secrets_service.py` — `SecretsService` 新增方法（`decrypt_for_internal_use` L667 同款 unlock 窗口语义）：

```python
def find_internal_by_name(self, name: str) -> str | None:
    """按 name 取明文 (依赖 unlock 窗口), 仅供后端服务间调用; 未解锁/不存在返回 None。

    与 decrypt_for_internal_use 的区别: 按 name (webhook.secret 等基础设施凭据)
    而非数字 id 定位; 不得暴露为 HTTP 端点。
    """
    items, _total = SecretRepository().list()
    item = next((i for i in items if i.name == name), None)
    if item is None:
        return None
    return self.decrypt_for_internal_use(item.id)
```

- Modify: `backend/services/trigger_gate/triggers/webhook.py` — `_get_secret` 默认路径替换（顺带修死 import）：

```python
    def _get_secret(self) -> str | None:
        if self._secret_provider is None:
            try:
                from backend.services.secrets_service import SecretsService

                return SecretsService().find_internal_by_name("webhook.secret")
            except Exception:
                return None
        if callable(self._secret_provider):
            return self._secret_provider()
        if isinstance(self._secret_provider, dict):
            return self._secret_provider.get("webhook.secret")
        return self._secret_provider.get("webhook.secret")
```

- Create: `scripts/fix_webhook_secret_to_vault.py`（**`--dry-run` 默认 True**，scripts/AGENTS 纪律）：读 settings kv `webhook.secret` → 若存在且主密钥已 unlock（`try_auto_unlock()`）→ `SecretsService().create_secret(name="webhook.secret", model="hmac", base_url="", api_key=<secret>, master_key=<unlock态取 master_key 或提示交互>)` → 删除 settings kv 行 → 打印摘要。注意 `create_secret` 需 master_key 当场验证：脚本在 unlock 窗口内经 `_unlock_state` 取 fernet 不可复用（create 需 master 本体），故脚本流程改为：提示输入 master_key（getpass）→ 验证 → create → 删 KV → 摘要。dry-run 只打印将执行的动作。
- Test: `backend/tests/test_trigger_webhook_secret.py` — ① `SecretsService.find_internal_by_name`：创建 secret 后 unlock 态可取明文、未解锁返回 None；② `WebhookTrigger._get_secret` 默认路径 monkeypatch `SecretsService.find_internal_by_name` 返回值被采用；③ 注入 provider 路径不回归。

- [ ] **Step 1: 写失败测试** → **Step 2: FAIL** → **Step 3: 实现 service 方法 + webhook 读点** → **Step 4: PASS** → **Step 5: `scripts/fix_webhook_secret_to_vault.py --dry-run` 本机跑通** → **Step 6: settings_service `_DISALLOWED_EXACT = {"webhook.secret"}` 落地 + 对应测试** → **Step 7: Commit** `fix(security): webhook.secret 迁加密存储 + 修复死 import (P3 Task 15)`。

### Task 16: sync bundle settings 白名单化

**Files:**
- Modify: `backend/services/sync_service_constants.py` — `SETTINGS_BLOCKLIST`（L16-21）替换为白名单常量：

```python
# settings 跨端同步白名单 (2026-09-22 P3): 仅用户偏好/配置 namespace 进 bundle。
# 密钥 (webhook.secret 已迁 vault) / 运行状态 (state.*) / 服务端锁 永不跨端。
SETTINGS_SYNC_PREFIXES = (
    "collection.", "llm.", "interest.", "quality.",
)

def settings_sync_allowed(key: str) -> bool:
    return key.startswith(SETTINGS_SYNC_PREFIXES)
```

- Modify: `backend/services/sync_bundle.py` L553-556（读取侧）与 L865-872（合并侧）：

```python
        "settings": {
            k: v for k, v in SettingsRepository().list_all().items()
            if settings_sync_allowed(k)
        },
```

```python
        if not settings_sync_allowed(k):
            settings_stats["skipped"] += 1
            continue
```

  （`from backend.services.sync_service_constants import settings_sync_allowed`；`sync_service.py:83` 与 `sync_merge.py:28` 的同名 `SETTINGS_BLOCKLIST` 若为独立副本，实施时 grep 其消费点：仅作 bundle 读取/合并过滤的改为引用共享 `settings_sync_allowed`，确有其他语义的保留并注释区分——**不静默合并语义不同的同名常量**。）
- Test: `backend/tests/test_sync_bundle.py`（或就近 bundle 测试）追加：bundle 含 `collection.refresh_interval_seconds`、不含 `state.mitre.synced_at` / `webhook.secret` / `scheduler.last_run`。
- [ ] Steps: 测试 → FAIL → 实现 → `pytest backend/tests/ -k sync -q` PASS → Commit `fix(sync): settings 跨端同步白名单化 (P3 Task 16)`。

### Task 17: P3 收口 — 审计留痕 + PRD 同步 + 全量回归

- [ ] 新建 `docs/audit/PRD_ALIGNMENT_AUDIT_2026-09-22.md`（settings IA 重构落账：17→7 cat、删除组件清单、端点变更 mcp/settings/features/feature-gates、settings 表契约；格式对齐既有 audit 文件）
- [ ] 权威 PRD `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 设置页能力段同步（7 cat 结构 + feature-gates 端点）
- [ ] DEV_LOG.md 追加条目（关联 spec + audit + PRD）
- [ ] `.venv/bin/python3 -m pytest backend/tests/ -q` → 0 失败；`cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error` → 全绿
- [ ] Commit `docs(audit): 设置重构审计留痕 + PRD 同步 (P3 Task 17)`

---

## Self-Review 记录

- **Spec 覆盖**: 设计稿 §3 (P1 Task 1-9) / §4.1-4.2 (Task 10) / §4.3 (Task 11) / §4.4 (Task 12) / §5 prefix+webhook+bundle (Task 14-16) / §6 守卫 (各 Task 步骤 + Task 13/17) / §7 边界 (未做拆表、未动兄弟路由、quality.py 遗留未动) / §8 验收 ← Task 9/13/17 收口步骤逐条覆盖。✓
- **占位符扫描**: 无 TBD/TODO；Task 4 Step 4 与 Task 11 Step 4 各有一处「以真实渲染/grep 结果为准修正」的显式指令（子面板标题文案、audit 函数签名），已写明核对方法而非留空。✓
- **类型一致性**: `SectionKey` 7 值在 Task 1/2/3/7 一致；`settings_sync_allowed` 在 Task 16 三处引用一致；`find_internal_by_name` 在 Task 15 定义与消费一致。✓
