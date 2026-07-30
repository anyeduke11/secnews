# Phase 7 子 PRD — 验证 + 一次性 push origin main

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §6 + §10
> **前置依赖**: Phase 1A-6 全部完成
> **预计 commit**: `chore: UI/UX refactor complete (Phase 1A-6)`

---

## 0. Goal (一句话)

全量验证 Phase 1A-6 交付（tsc / vitest / vite build / 浏览器 / 敏感文件核查），然后一次性 commit + push origin main，结束整个 UI/UX 重构。

## 1. 入口 / 出口

- **入口**: Phase 6 完成（15 测试 PASS）
- **出口**: origin main 已推送、UIUX_REFACTOR_PRD.md 状态全部 ✅

## 2. In Scope（必须做）

### 2.1 自动化验证（5 项）

| # | 验证项 | 命令 | 通过标准 |
|---|---|---|---|
| 1 | TypeScript | `cd frontend && npx tsc --noEmit` | 0 errors |
| 2 | 单元测试 | `cd frontend && npx vitest run` | 90+ PASS, 0 failed |
| 3 | 生产构建 | `cd frontend && npm run build` | < 12s 成功 |
| 4 | 后端测试 | `.venv/bin/python3 -m pytest backend/tests/ -q` | 1283 PASS |
| 5 | 硬编码颜色 | `grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" \| grep -v "^\s*//" \| wc -l` | 0 |

### 2.2 浏览器手动验证（4 项）

| # | 场景 | 验证点 |
|---|---|---|
| 1 | 暗主题 5 高频页 | /, /sync, /knowledge, /codegarden/phase2b, /todos |
| 2 | 亮主题 5 高频页 | 同上，切换无视觉断裂 |
| 3 | 主题切换无闪烁 | 点击 toggle 按钮，颜色瞬间切换 |
| 4 | 4 状态组件 | 至少触发一次 Empty/Loading/Error 场景 |

### 2.3 敏感文件核查（3 项）

| # | 文件类型 | 检查方式 |
|---|---|---|
| 1 | .env | `git status` 不应出现（应在 .gitignore） |
| 2 | proxy_config.json | 同上（应在 .gitignore） |
| 3 | backend/hotspot.db | 同上（数据库不入库） |

### 2.4 一次性 commit + push

```bash
cd /Users/duke/Documents/hotspot
git status
git add -A  # 仅当所有文件均可入库
git status  # 二次核查
git commit -m "chore: UI/UX refactor complete (Phase 1A-6)"
git push -u origin main
```

## 3. Out of Scope（明确不做）

- ❌ **不修后端代码**（除非后端测试因前端改动失败）
- ❌ **不引入新功能**（仅做收尾验证）
- ❌ **不写 release notes**（除非用户明确要求）
- ❌ **不改 docs/** 已有内容（仅更新 PRD 状态）
- ❌ **不清理 git stash**（已 Phase 1A 摘过，剩余留给后续会话）

## 4. 验证步骤

### Step 1: 自动化全量验证

```bash
cd /Users/duke/Documents/hotspot

# 1. tsc
cd frontend && npx tsc --noEmit && cd ..
# 期望: 0 errors

# 2. vitest
cd frontend && npx vitest run && cd ..
# 期望: Test Files 0 failed, Tests 90+ passed

# 3. vite build
cd frontend && npm run build && cd ..
# 期望: ✓ built in < 12s

# 4. 后端测试
.venv/bin/python3 -m pytest backend/tests/ -q
# 期望: 1283 passed

# 5. 硬编码颜色
grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" | grep -v "^\s*//" | wc -l
# 期望: 0
```

### Step 2: 浏览器手动验证

```bash
# 1. 启动 dev server
cd frontend && npm run dev &
# 等待 http://localhost:8898 启动

# 2. 浏览器打开
# - 暗主题 5 页: /, /sync, /knowledge, /codegarden/phase2b, /todos
# - 切亮主题 5 页（同路径）
# - 验证无硬编码残留、无 4 状态组件缺失
```

### Step 3: 敏感文件核查

```bash
cd /Users/duke/Documents/hotspot
git status | grep -E "\.env$|proxy_config|hotspot\.db$"
# 期望: 空输出（已被 .gitignore 过滤）

# 核查 .gitignore
grep -E "^\.env$|proxy_config|hotspot\.db" .gitignore
# 期望: 至少 3 条
```

### Step 4: 一次性 commit + push

```bash
cd /Users/duke/Documents/hotspot

# 1. 检查状态
git status

# 2. 二次核查：不应有敏感文件
git status | grep -E "\.env$|proxy_config|hotspot\.db$" && echo "ERROR: 敏感文件" && exit 1

# 3. 暂存
git add frontend/ docs/UIUX_*.md
# 注意: 不 add backend/ 除非有改动

# 4. 提交
git commit -m "$(cat <<'EOF'
chore: UI/UX refactor complete (Phase 1A-6)

UI/UX 全面重构完成：
- Phase 1A: 设计系统骨架（token + 原子组件 + 嵌套 Layout）
- Phase 1B: 拆 6 大文件为 24 子组件
- Phase 2-4: SecNews / Knowledge / CodeGarden 业务组件 token 化
- Phase 5: 系统/工具页 + 45 组件最小改动
- Phase 6: 15 高频组件测试补强

效果：
- 0 硬编码颜色
- 暗/亮双主题完整适配
- 4 状态组件统一（Empty/Loading/Error/Success）
- 90+ vitest 用例 PASS
- 1283 后端测试全 PASS
EOF
)"

# 5. 推送
git push -u origin main
# 期望: 推送成功
```

### Step 5: 更新 master PRD 状态

编辑 `docs/UIUX_REFACTOR_PRD.md`:
- §4.1-4.5 状态 → ✅
- §5 状态 → ✅
- §10 复选框全部勾选

## 5. 验证清单（DoD）

```bash
# 1. 自动化全绿
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
# 期望: 全部成功

# 2. 后端测试
.venv/bin/python3 -m pytest backend/tests/ -q
# 期望: 1283 passed

# 3. 0 硬编码
grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" | grep -v "^\s*//" | wc -l
# 期望: 0

# 4. 0 emoji UI 图标（可选抽样）
grep -rE "[\xF0-\xF4][\x80-\xBF]{3}" frontend/src --include="*.tsx" | grep -v "^\s*//" | wc -l
# 期望: ≤ 5（页面文字 emoji 允许，UI 控件 emoji 不允许）

# 5. 推送成功
git log origin/main..HEAD
# 期望: 空（已同步）

# 6. PRD 状态更新
grep -E "✅|⏳" docs/UIUX_REFACTOR_PRD.md | head -20
# 期望: Phase 1A-6 全部 ✅
```

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| push 时冲突 | 推送前 `git fetch origin` + `git status` 检查 |
| 敏感文件误提交 | Step 3 二次核查，grep .env/proxy_config/hotspot.db |
| 后端测试因前端构建变化失败 | Phase 1A-6 严格不动 backend/，理论上无影响 |
| 浏览器验证发现问题 | 立即修复 → 重新走 Phase 2-5 流程，不绕过 |
| vite build 慢 | 拆分已优化（Phase 1B），仍超时则查依赖 |

## 7. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| push 策略 | 一次性 push | master PRD 决策 6 锁定 |
| commit message 格式 | conventional | 与项目历史一致 |
| 浏览器验证 | 人工 | 无 e2e 框架 |
| 敏感文件过滤 | .gitignore | 已配置 |

## 8. 完成后

- 更新 master PRD §10 复选框全部 ✅
- 更新 `AGENTS.md` / `CLAUDE.md` 状态摘要
- 在 `docs/CHANGELOG.md`（如有）记录本次重构
- 关闭 UIUX_REFACTOR_PRD，进入下一个工作流
