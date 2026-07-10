# Hotspot 管理员手册 (ADMIN_MANUAL.md)

> 本仓库: **https://github.com/anyeduke11/hotspot**
> 仓库主: `anyeduke11` · 默认分支: `main` · 授权: **GPL-3.0**
> 状态: `public` · 描述: AI时代IT从业者的工作台，主要聚焦资讯，标讯，待办，密钥管理，LLM管理等

---

## 一、仓库信息

| 项 | 值 |
|----|----|
| 名称 | `hotspot` |
| 完整路径 | `anyeduke11/hotspot` |
| 默认分支 | `main` |
| 可见性 | **public** |
| 主语言 | Python |
| 体积 | 709 KB |
| 仓库主 | `anyeduke11` (LinuxSelf) |
| 关联账户 | `secnews` (同主,Windows 平台推送) |
| LICENSE | GNU GPL v3.0 |
| 创建时间 | 2026-07-05 |
| 最近推送 | 2026-07-10 |
| 权限范围 | admin / maintain / push / triage / pull |

---

## 二、首次公开(已完成)

**关键节点**:

| 日期 (UTC) | 事件 | SHA | 作者 |
|-----------|------|-----|------|
| 2026-07-05 | 仓库创建 | `42abca5` | secnews |
| 2026-07-10 10:15 | `anyeduke11/duke` 仓同步 hotspot | `dc2d493` | LinuxSelf |
| 2026-07-10 10:15 | SOC-kanban 清理 | `ed48c32` | LinuxSelf |
| 2026-07-10 10:24 | 推送到 `anyeduke11/hotspot` (force 覆盖) | `ae3593d9` | LinuxSelf |
| 2026-07-10 10:26 | 仓库公开 | — | — |

**历史说明**:`anyeduke11/hotspot` 仓的初始 commit 来自 Windows 平台的 `secnews` 账户(同主)。2026-07-10 10:24:02Z 由 Mac 平台 LinuxSelf 账户 force push 覆盖,新 HEAD `ae3593d9` 即为当前 master。

---

## 三、推送流程(双平台同步)

### 3.1 本地配置

```bash
# 在 Documents/hotspot/ 目录下
cd /Users/duke/Documents/hotspot

# 验证 origin
git remote -v
# origin  https://github.com/anyeduke11/hotspot.git (fetch)
# origin  https://github.com/anyeduke11/hotspot.git (push)

# 验证 user
git config user.name   # LinuxSelf
git config user.email  # AnyeDuke@gmail.com
```

### 3.2 日常推送

```bash
# 1. 检查状态
git status

# 2. 选择性 add(避免引入 . 开头缓存目录)
git add backend/ frontend/ scripts/ docs/ run.py *.md *.json
# 或限定明确文件
git add backend/api/hotspots.py

# 3. 提交
git commit -m "feat: 简明描述"

# 4. 推送到 main
git push origin main
```

### 3.3 Force Push 策略

**何时用**:
- mac/Win 双平台同时维护,内容互有覆盖
- 仓库维护者一致(都是 `anyeduke11`),无外部协作者

**何时不要用**:
- 仓库已开放给外部贡献者
- 推送前未确认 Windows 平台无未提交改动

```bash
# 强制推送到 main
git push -f origin main

# 推送到非默认分支(更安全)
git push -f origin <branch-name>
```

### 3.4 防止误推

`.gitignore` 已包含:

```
# Hidden tool / cache folders
.*/
.arts/
.claude/
.cursor/
.gemini/
.history/
.pi/
.trae/
.web_builder/

# Hidden single-file configs
.mcp.json
.merkle-snapshot.json
```

**新增 . 开头工具时**:
1. 编辑 `.gitignore` 加新条目
2. 验证:`git ls-files --others --exclude-standard | grep -E "^\."` 应为空
3. 提交 .gitignore 变更

---

## 四、日常运营

### 4.1 启用 GitHub 功能(已开启 / 待开启)

| 功能 | 状态 | 说明 |
|------|------|------|
| Issues | ✅ enabled | 用户反馈 / Bug 报告入口 |
| Wiki | ✅ enabled | 自由编辑 |
| Pages | ❌ disabled | 可用于文档站(暂不需要) |
| Discussions | ❌ disabled | 社区交流(可视需求启用) |
| Downloads | ✅ enabled | 二进制分发 |
| Secret scanning | ❌ disabled | **建议公开仓库开启** |
| Dependabot | ❌ disabled | **建议公开仓库开启** |

### 4.2 建议公开后开启的安全/协作功能

```bash
# 1. 开启 Secret scanning
gh repo edit anyeduke11/hotspot --enable-secret-scanning

# 2. 开启 Push protection (推前拦截)
gh repo edit anyeduke11/hotspot --enable-secret-scanning-push-protection

# 3. 开启 Dependabot
# 需在 .github/dependabot.yml 配置

# 4. 开启 Discussions(可选,等社区规模起来)
gh repo edit anyeduke11/hotspot --enable-discussions

# 5. 添加 topics(SEO / 检索)
gh repo edit anyeduke11/hotspot --add-topic "python,fastapi,react,vite,typescript,ai,security,finance,startup"
```

### 4.3 添加仓库描述 / 链接

当前 `description`:
> AI时代IT从业者的工作台，主要聚焦资讯，标讯，待办，密钥管理，LLM管理等

```bash
# 修改描述
gh repo edit anyeduke11/hotspot --description "AI 时代 IT 从业者的工作台 - 资讯聚合 / 标讯追踪 / 待办管理 / 密钥 & LLM 配置"

# 设置 homepage (如部署了 demo)
gh repo edit anyeduke11/hotspot --homepage "https://hotspot.example.com"
```

### 4.4 设置分支保护

```bash
# 启用 main 分支保护(避免直接 push 到 main)
gh api repos/anyeduke11/hotspot/branches/main/protection \
  --method PUT \
  --input - <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismissal_restrictions": {},
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF
```

**注意**:本仓目前采用**直接 force push 到 main**(只有单一主维护者),不强制 PR 流程。如果未来引入外部协作者,需切换到 PR-based 工作流。

---

## 五、Issue 管理

### 5.1 Issue 模板

仓库已有 `.github/` 目录,可能含 issue 模板。检查:

```bash
ls -la .github/
ls -la .github/ISSUE_TEMPLATE/ 2>/dev/null
```

如缺失,创建标准模板:

```bash
mkdir -p .github/ISSUE_TEMPLATE
```

**bug_report.md**:
```markdown
---
name: Bug 报告
about: 报告 Hotspot 的 Bug
title: '[Bug] '
labels: bug
---

## 复现步骤
1.
2.
3.

## 期望行为


## 实际行为


## 环境
- OS: [macOS / Windows / Linux]
- Python: [e.g. 3.14]
- Node: [e.g. 20.0]
- Branch: [main / dev]

## 日志/截图
```

**feature_request.md**:
```markdown
---
name: 功能建议
about: 提出新功能想法
title: '[Feature] '
labels: enhancement
---

## 痛点
描述当前缺失/不便的方面

## 期望方案
具体建议

## 替代方案
考虑过的其他方案
```

### 5.2 Label 体系(推荐)

```bash
# 创建 labels
gh label create "bug" --color "d73a4a" --description "功能异常或错误"
gh label create "enhancement" --color "a2eeef" --description "新功能或改进"
gh label create "documentation" --color "0075ca" --description "文档改进"
gh label create "good first issue" --color "7057ff" --description "新手友好"
gh label create "help wanted" --color "008672" --description "需要帮助"
gh label create "duplicate" --color "cfd3d7" --description "重复 issue"
gh label create "wontfix" --color "ffffff" --description "不会修复"
```

---

## 六、发布 / 版本

### 6.1 打 tag

```bash
# 创建带注释的 tag
git tag -a v2.0.0 -m "Hotspot v2.0.0 - 首次公开版本"

# 推送 tag
git push origin v2.0.0

# 验证
gh release list
```

### 6.2 创建 GitHub Release

```bash
# 用 gh CLI 创建 release
gh release create v2.0.0 \
  --title "Hotspot v2.0.0" \
  --notes "$(cat <<'EOF'
## 首次公开版本

### 包含
- 5 大领域资讯聚合
- 标讯追踪
- 待办管理
- 收藏 & 周报
- 质量门禁系统

### 授权
GNU GPL v3.0

### 致谢
- 报告 issue
- 提交 PR
EOF
)"
```

---

## 七、监控 / 维护

### 7.1 流量统计

```bash
# 看近 14 天流量
gh api repos/anyeduke11/hotspot/traffic/views 2>&1 | python3 -m json.tool

# 看克隆来源
gh api repos/anyeduke11/hotspot/traffic/clones 2>&1 | python3 -m json.tool

# 看 star 增长
gh api repos/anyeduke11/hotspot/stargazers 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Total stars: {len(data)}')
for s in data[-5:]:
    print(f'  {s[\"login\"]} at {s[\"starred_at\"]}')
"
```

### 7.2 依赖更新

**Dependabot 配置** (`/.github/dependabot.yml`):

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "deps(python)"

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "deps(npm)"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

### 7.3 CI 触发检查

仓库目前无 CI(`.github/workflows/` 目录在 secnews 推送时创建,可能为空)。建议补:

```yaml
# /.github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest tests/ -q

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: cd frontend && npm ci && npm run build
```

---

## 八、双平台协调规范

**核心原则**:`anyeduke11` 和 `secnews` 是同一主维护者,跨平台同步采用**最新覆盖**(last-write-wins)。

### 8.1 工作流

| 平台 | 推送规则 |
|------|---------|
| macOS (LinuxSelf) | 默认推送,可 force |
| Windows (secnews) | 推送前先 `git pull --rebase`;建议不在 Windows 长期维护 |

### 8.2 冲突处理

```bash
# 在 Windows 上:
git fetch origin
git rebase origin/main   # 或 git pull --rebase

# 解决冲突后
git push origin main     # 正常 push
```

### 8.3 避免混乱建议

- **Mac 为主要开发平台**(`anyeduke11/hotspot` 的 origin 已在 Mac)
- Windows 推送前必须先 pull
- 大型改动在 Mac 完成,Windows 仅为消费/调试

---

## 九、安全 / 合规

### 9.1 GPL-3.0 义务

- **Copyleft**:派生作品必须同样 GPL-3.0 开源
- **专利授权**:贡献者授予使用者专利使用权
- **禁止闭源封装**:不能将本仓代码嵌入闭源产品而不开源
- **完整源码**:分发时必须提供对应源代码

### 9.2 贡献协议

- 贡献者通过 PR 提交,即视为同意 GPL-3.0
- 建议增加 `CONTRIBUTING.md` 明确说明
- 可加 DCO / CLA 流程(超出本仓当前规模)

### 9.3 敏感信息扫描

推送前必查:

```bash
# 扫描密钥
git ls-files | xargs grep -lE "AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}" 2>/dev/null

# 扫描 .env 误提交
git ls-files | grep -E "\.env$" | head -5
```

**注意**:`.env` 已在 `.gitignore` 中,正常不会被跟踪。

---

## 十、应急响应

### 10.1 误推敏感信息

```bash
# 1. 立即重置密钥(假设泄露的是 API key 等)
# 2. 从 git history 清除
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch <sensitive-file>" \
  --prune-empty --tag-name-filter cat -- --all

# 3. force push
git push -f origin main

# 4. 通知协作者重新 clone
```

### 10.2 仓库被举报 / DMCA

1. GitHub 会邮件通知主维护者
2. 评估内容,如有侵权立即删除
3. 如争议,通过 GitHub Support 申诉

### 10.3 备份策略

```bash
# 定期 bare clone 备份
git clone --bare https://github.com/anyeduke11/hotspot.git /Users/duke/backup/hotspot-$(date +%Y%m%d).git

# 清理 30 天前的备份
find /Users/duke/backup -name "hotspot-*.git" -mtime +30 -exec rm -rf {} \;
```

---

## 十一、参考

| 资源 | 链接 |
|------|------|
| 仓库 | https://github.com/anyeduke11/hotspot |
| Issues | https://github.com/anyeduke11/hotspot/issues |
| LICENSE | https://github.com/anyeduke11/hotspot/blob/main/LICENSE |
| GitHub 文档 | https://docs.github.com |
| gh CLI 文档 | https://cli.github.com/manual/ |
| GPL-3.0 全文 | https://www.gnu.org/licenses/gpl-3.0.html |

---

**手册版本**: v1.0
**生效日期**: 2026-07-10
**维护人**: `anyeduke11` (LinuxSelf)
**下次审查**: 公开后 30 天,或新增协作者时
