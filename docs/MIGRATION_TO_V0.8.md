# v0.7 → v0.8 Skills 迁移指南 (Phase D D5)

> 目标读者: hotspot 维护者 + 二次开发者。从 v0.7.4-image 升级到 v0.8.0-skills
> 时需要做什么、哪些功能被替代、哪些 API 被冻结。

---

## 1. 一句话总结

v0.8 不删任何路由 (Phase 7 已冻结物理删除), 只**叠加**一个 Skill/Playbook 双轨
看板型 AI 智能体。所有 v0.7 功能原地可用。

---

## 2. 新增 / 变化一览

### 2.1 新增能力

| 能力 | 路径 / API | 启用开关 |
|---|---|---|
| Skill 商店 | `/skill-store` | `skill_registry` gate |
| Skill Builder | `/skill-store/new` | `user_skills` gate |
| Skill 详情 + 历史 + 反馈 | `/skill-store/<id>` | (同上) |
| Dashboard 看板 | `/dashboard` | (随 skill_registry) |
| Playbook 调度 | `playbooks/*.yml` + `/api/scheduler/playbooks` | `playbook_engine` gate |
| Eval 评测框架 | `skill_eval/fixtures/*.yaml` | 测试用 |
| Webhook 触发 | `POST /api/trigger/webhook/{source}` | `trigger_gate` gate |

### 2.2 替代关系 (无破坏)

| 旧用法 (v0.7) | 新用法 (v0.8) | 说明 |
|---|---|---|
| 手动跑脚本 | Skill / Playbook | skill_type=A 巡检替代手工 cron 脚本 |
| 工作台 6 cognitive modes | Skill + Playbook | 已于 v0.7.0 物理删除 |
| `playbook_engine_v0_7.py` (旧 schema) | `playbook_engine/{core,loader,step,scheduler}.py` (新 schema) | YAML schema `kind=Playbook` + `metadata.name` |

### 2.3 冻结 / 不变

- `data/judge/action/` 三层目录 — v0.7.0 已物理删除, 不可恢复
- 6 cognitive modes — 同上
- 所有 Phase 7 之前的路由 (`/api/skills` 等) — 保持原状
- 信息流: collectors → quality → scheduler → api/main.py — 不变

---

## 3. Feature Gate 切换 (运维侧)

默认全部 `false` (fail-closed)。线上启用顺序建议:

1. `skill_registry = true` → 验证 `/skill-store` 列出 20 skill
2. `user_skills = true` → 验证 `/skill-store/new` 可创建
3. `playbook_engine = true` → 验证 cron 调度生效
4. `trigger_gate = true` → webhook 端点可外部触发

每个开关都需要 backend **重启** 才生效 (FastAPI 启动时一次性注册路由)。

---

## 4. 数据库迁移 (DBA 侧)

Phase C/D 共 +3 SQL migration (序号 094 / 95 / 无新增 D1) — 全部 `IF NOT EXISTS`,
v0.7.4-image → v0.8.0-skills 升级时 `init_db()` 自动应用, 无需手工:

- `094_v08_playbook_engine.sql` — `playbook_schedules` + `playbook_runs`
- `095_v08_user_skills.sql` — `user_skills`
- (D1 不新增, 复用 `trigger_tickets` / `skill_runs` 现有表)

迁移顺序保证: 091 (Phase A trigger_tickets/skill_runs) → 094 → 095, 数字递增。

---

## 5. Playbook YAML schema 变化 (重要!)

### 旧 (v0.7 codegarden orchestration, 仍可读但不推荐):

```yaml
name: test-pb
steps:
  - name: step1
    run: echo hello
```

### 新 (v0.8 PlaybookEngine, C1 起强制):

```yaml
kind: Playbook          # 顶层 kind 必须 = Playbook
metadata:
  name: test-pb
  desc: 'unit test playbook'
inputs:
  hours:
    type: int
    default: 24
trigger:
  cron: "0 9 * * *"
  timezone: Asia/Shanghai
steps:
  - id: step1            # 注意: id 不是 name
    kind: api            # skill / api / condition 三选一
    action: GET /api/_dummy
    output: api_result
```

迁移检查清单:

- [ ] 顶层加 `kind: Playbook`
- [ ] `name:` → `metadata.name:` (平级挪到 metadata 下)
- [ ] `steps[].name` → `steps[].id`
- [ ] `run:` (旧脚本) → 改写为 `kind: api` + HTTP 调用 (R7 砍 script)
- [ ] 危险命令 (sudo / rm -rf 等) 移除, 否则 validate 拒绝

---

## 6. skill_registry 内部 API 变化

### 6.1 POST /api/skill-registry/{id}/run

v0.7 之前: 直接执行 skill (同步)
v0.8 起: **只入队不执行** (Phase A 预注册态语义), 返回 `ticket_id`; 执行由 worker 出队后异步完成

客户端如果想等结果, 轮询 `GET /api/skill-registry/runs/{ticket_id}` 或用 SSE
(`/api/events`)。

### 6.2 settings.kv key 命名

| 操作 | key | value |
|---|---|---|
| 启用 | `skill.<id>.enabled` | `true` |
| 停用 | `skill.<id>.enabled` | `false` |
| webhook secret | `webhook.secret` | 字符串 |

(沿用 v0.7 SettingsRepository 的 settings 表)

---

## 7. i18n key 变化 (前端)

旧版 (v0.7 hardcoded zh-CN):
- SkillStore / SkillDetail / SkillBuilder / Dashboard / RunHistory / FeedbackBar 文案硬编码

新版 (v0.8 Phase D D3 全部走 useI18n):
- 新增 `dashboard.*` (15 keys) / `skill.store.*` (8 keys) / `skill.builder.*` (12 keys) / `common.back`
- 合计 36 新 key (zh-CN + en-US 双语)
- 旧硬编码位置保留中文作为 fallback (locale = 'en-US' 时显示 key 名)

不影响 v0.7 文案; 切到 v0.8 后仅多出 i18n 路径, 文案不变。

---

## 8. 测试基线 (升级前自检)

```bash
# 1. 全量 backend pytest 不退化
.venv/bin/python3 -m pytest backend/tests/ --tb=line -q
# v0.7.4-image 基线: pytest 3437
# v0.8.0-skills 目标: pytest ≥3717 (Phase C 末态) → Phase D ≥3610 (R14 重锚)

# 2. 架构数字反推
python scripts/generate_meta.py --check
# v0.8.0-skills 目标: routers 76 / services 115 / jobs 51 / collectors 14

# 3. Agent assets lint (skill 长度 + frontmatter)
python scripts/harness_analyze.py --check
# 必须 0 errors
```

---

## 9. 回滚方案

如果 v0.8 引入 bug 需要紧急回滚到 v0.7.4-image:

```bash
# 1. feature_gates.toml 全部 false (gate 关闭, 路由 404)
# 2. 不需要物理删除任何代码 (新包是叠加式)
# 3. 不需要回滚 migration (表 IF NOT EXISTS, 旧 v0.7 代码无视新表)
# 4. 重启 backend → /skill-store 等端点 404, 系统回到 v0.7 行为
```

注意: 已经写入的 `playbook_schedules` / `user_skills` 数据会保留在 DB,
未来再开 gate 时直接可用。

---

## 10. 不在迁移范围 (留 v0.9 / v1.0)

- 真实 LLM skill engine (当前 Protocol 抽象 + FakeEngine 测试)
- Dashboard 触发器时间线的数据面 (`/api/trigger/tickets`)
- Playbook DAG 调度
- webhook source 动态注册 (当前硬编码 6 个白名单)
- Skill Builder 自建 skill 的沙箱执行 (当前直接调服务)

详见 `docs/V0.8_REFACTOR_PLAN.md` §10 不在范围段。