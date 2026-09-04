# v0.8 Skills Agent Checklist

> 基线 (R5, 2026-09-03 @ git `e066951`): pytest 3437 / vitest 370 (观测 1 次 flaky, 复跑全绿) / tsc 0 错 / routers 68 / services 107 / migrations 87 .sql
> 铁律: 任何阶段全量跑出现基线回归 = 硬失败, 修复优先于新功能

## 基线与分支

- [x] 分支 `refactor/v0.8-skills` 从 main 建立 (基线 HEAD 实为 `919e2ca`, 2026-09-03 之后 main 有新提交; 基线数字 3437/370 记录于 PROGRESS.md v0.8 段)
- [x] feature_gates.toml 登记 skill_registry / trigger_gate 两 gate 默认 false, 全关态启动冒烟通过 (core 不受影响; agent_loop/playbook_engine/user_skills 留 B/C 随实现登记)

## Phase A (W1 末) — 2026-09-04 验收

- [x] trigger-gate: 61/min 第 61 次 → 429 (per-user); 限流不误伤全局 (test_trigger_gate 17 case)
- [x] trigger-gate: REALTIME ticket 出队先于 BATCH (测试断言); 运行中任务不被抢占
- [x] trigger-gate: 模拟崩溃后重启, pending ticket 重新消费 (崩溃不丢)
- [x] migration 091 存在: trigger_tickets + skill_runs 两表
- [x] 20 个内置 skill 全部注册 (A=12/B=1/C=4/D=3), 每个含 skill_type + target/pipeline + schema + 独立 gate (R1 契约: A/B 类不持有 prompt_template)
- [x] abstractor.py 反模式 linter: 对 CRUD / 已有 cron / 高 QPS 输入输出反模式警告 (8 case)
- [x] `/skill-store` 路由可访问 (原 /skills 被 Phase 41 占用, 路径偏离裁决记录于 PROGRESS), 列 20 卡片, 启停写 settings.kv + audit_log (SSE 推送留 B6 接线)
- [x] 卡片为预注册态: "跑一次"按钮 Phase A 语义 = 入队返回 ticket_id (执行接线 B5)
- [x] `pytest 3516 passed / 6 skipped (≥3490 ✓, 零回归) / vitest 386 (≥382 ✓) / tsc 0 错`
- [ ] i18n skill.* namespace zh-CN + en-US 双满 — **已知偏离**: A4 硬编码中文 + TODO(D3) 注释, R11 每 commit 双满推迟至 D3 统一迁移 (含 ~80 key)
- [x] `generate_meta.py --check` 通过 (routers 70 同步)

## Phase B (W2 末)

- [ ] migration 092 loop_checkpoints 存在; EXECUTE 后崩溃 → 从 checkpoint 续跑 (测试)
- [ ] A/B 类 skill 走 fast-path: 零 LLM token 消耗, 耗时接近直调 service (测试断言 metrics)
- [ ] C/D 类走完整五阶段; REFLECT 失败 retry 1 → 仍失败 commit partial=True
- [ ] 点 "信源质量巡检" → 跑完 → 产物落 llm-wiki-2.0 → skill_runs 历史可查 (run_id 贯穿)
- [ ] migration 093 feedback_log 存在; 👍 反馈写 agent_memory, recall API 命中 ≥1 条
- [ ] user_memory v1 旧接口不破坏 (既有测试零回归)
- [ ] dsh mock/真子进程 settings.kv 切换; 真子进程失败自动回退 mock
- [ ] SSE event_type=skill_run 阶段序列正确 (A/B 2 阶段 / C/D 5 阶段)
- [ ] `pytest ≥3550 (= 3437+109) / vitest ≥394 (= 370+24) / 零回归`

## Phase C (W3 末)

- [ ] playbook YAML: JSON Schema 校验 + Jinja 条件; 引用未注册 skill → 校验失败 (R8 悬空引用拦截)
- [ ] step 类型仅 skill / api (本机 /api/* 白名单) / condition — 无 script 执行路径 (代码审计确认)
- [ ] 50 step / 1h 上限强制停止 + 写 audit
- [ ] 3 个 example YAML 跑通 (全部引用 20 清单内 skill); daily-source-health cron 8am 自动触发 (测试)
- [ ] migration 094 user_skills 存在; 自建 "我的日报" skill 跑通 + 软删 + dry-run; 上限 50
- [ ] Eval 5 fixture 跑通, 报告落 SQLite
- [ ] codegarden_orchestration 旧路由保留可用
- [ ] `pytest ≥3595 (= 3437+154) / vitest ≥402 (= 370+32) / 零回归`

## Phase D (W4 末)

- [ ] webhook `/api/trigger/webhook/{source}`: HMAC 缺签名 → 401; 同签名超 ±5min 重放 → 401 (测试)
- [ ] KL T4 完成事件触发 "质量巡检" skill (联动验证)
- [ ] collector failure 事件入口经 trigger-gate
- [ ] Dashboard: 20 skill 状态矩阵 + 触发器时间线 + 健康卡片 + 反馈统计
- [ ] i18n 全栈双满 (~80 新 key, 每 commit 双满); a11y: 按钮 keyboard 可达 + ARIA label
- [ ] 错误信封三字段 `{detail: {message, code, hint}}` 全 API 一致; `scripts/gen_ts_types.py` CI drift 校验通过
- [ ] BS-Agent 9 特性逐项验收 (plan §19.7.1): 单一入口 (代码审计无绕过路径) / 优先级 / 持久化队列 / 状态机 / 4 runner 派发 / 记忆闭环 / 产物落 wiki / 3 playbook / SSE 推送 — 9/9
- [ ] J→A 闭环布线验证 (R10: ai_hub 结论 → alert_engine, D1 落地时代码级确认)
- [ ] `pytest ≥3610 (= 3437+173) / vitest ≥420 (= 370+50) / tsc 0 错 / 零回归`
- [ ] routers 68→76 / services 107→115 (generate_meta 同步)
- [ ] tag `v0.8.0-skills` 推送; ARCHITECTURE/PROGRESS/CHANGELOG 同步; V0.8_USER_GUIDE + MIGRATION_TO_V0.8 交付

## 期末使用性硬指标 (R-验收升级, tag 后 2 周)

- [ ] ≥8/20 内置 skill 被真实触发 ≥3 次 (数据源 skill_runs 表) — 区分 "建成" 与 "用成"

## 明确不引入 (边界守卫)

- [ ] 无 Playbook script step 实现 (R7)
- [ ] 无 WebSocket 依赖引入 (R6)
- [ ] 无 E 类操作型 skill / MCP tools 包装为 skill / marketplace (P1-6 / P1-7)
