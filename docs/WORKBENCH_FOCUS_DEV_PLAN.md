# Workbench Focus 开发目标与执行计划（GOAL）

- 日期：2026-09-12；状态：**已立项待开工**
- 产品口径：[`WORKBENCH_FOCUS_PRD_v1.0.md`](WORKBENCH_FOCUS_PRD_v1.0.md)（P0/P1/P2 范围以 PRD 为准，本文只管执行）
- 执行纪律：沿用仓库既有规则——一次一小步、每步 DEV_LOG 落账（DEV-NNNN 递增）、提交必须 `git commit <显式路径>`、并行会话编号先查 DEV_LOG 再领号。

---

## GOAL 声明

> 让安全从业者打开工作台的第一屏，只看到与自己实践方向相关的资讯，且每条可解释"为什么推给我"；
> 未勾选任何方向时，系统行为与现状完全一致。

## 完成定义（Definition of Done）

- [ ] P0 全部任务（T0.1-T0.5）交付且验收绿（见各任务退出判据）
- [ ] `npx tsc --noEmit` 0 错；`npx vitest run` 全绿；`pytest backend/tests/` 0 失败 0 回归
- [ ] `python scripts/generate_meta.py --check` 通过（若新增 service 文件，同步 ARCHITECTURE.md 数字）
- [ ] 向后兼容断言：`interest.practice_domains` 为空时，`/api/content` 响应与现状结构逐字段一致
- [ ] **独立验收门**：独立 agent 对照本文件逐条功能验收（含真实前端走查截图），实现会话不得自评 PASS
- [ ] **独立审计门**：`code-reviewer` 代码审计（重点：词表数据注入、排序稳定性、kv 写入审计、i18n 完整性），P0 级发现修复后复验
- [ ] DEV_LOG / PROGRESS.md 落账；显式 pathspec 提交；PRD/DEV_PLAN 状态行更新

## P0 任务分解（本期范围）

### T0.1 实践域词表（后端）

- 改动点：`backend/services/auto_classifier.py`
  - 新增 `PRACTICE_DOMAINS`（8 域常量）+ 三级映射扩展：`TAG_PRACTICE_MAP` / `TITLE_PRACTICE_RULES` / 复用 URL 级（低优先）
  - 新增 `classify_practice_domain(item) -> str`；`classify_item` / `batch_classify` 输出增加 `practice_domain` 字段（缺省 `None`，不破坏既有消费者）
- 词表以模块级常量 + 纯函数实现（数据驱动，便于 P1 运营化），**不引入配置文件/DB 表**（避免过度设计；运营化是 P1 的事）
- 退出判据：`tests/test_auto_classifier*.py` 新增 ≥16 用例（每域 ≥2 正例 + 1 反例），全绿；既有 `classify_domain` 行为不变（回归断言）
- 关联：`backend/scheduler/jobs/collect.py` 等消费者零改动即可受益（batch_classify 透传）

### T0.2 标注集扩展 60 → 80（后端 + 数据）

- 改动点：v1 起步标注数据（T07 admission_log 标注，迁移/种子脚本定位以 `backend/repository/migrations/097*.sql` 现状为准）
- 新增 20 条标注覆盖 8 实践域（每域 ≥2 条），标注格式与既有 60 条一致
- 退出判据：标注总数 80；实践域覆盖检查脚本断言每域 ≥2；**关闭 v1.0 T00 悬置裁决"标注集 60-80"**（在 PROGRESS.md 记裁决关闭）

### T0.3 兴趣画像（后端 + 前端）

- 后端：`backend/api/settings.py` 新增 `GET /api/settings/interests` / `PATCH /api/settings/interests`
  - 存 `settings.kv` key=`interest.practice_domains`（字符串数组，值域 = T0.1 的 8 域，服务端校验）
  - 写路径记 audit_log（沿用 `POST /api/settings/llm-provider` 的 kv + audit_log 先例，settings.py:142 处理器模式）
- 前端：Settings 页（`/settings`）新增"我的方向"多选卡（挂 InfoFilterCard 同级区块；组件放 `frontend/src/components/settings/`）
  - 勾选即保存（防抖 PATCH）+ 成功反馈；空选 = "不过滤（现状）"显式文案
- 退出判据：API 集成测试（读写/校验非法域 422/audit 落账）；vitest 组件测试（选择/取消/空态/i18n key 断言）

### T0.4 Feed 接线（后端 + 前端）

- 后端：`backend/api/content.py` 列表端点加可选 `practice_domain` 过滤参数；**排序层**：命中兴趣域加权（复用 attention 评分链，权重常量起步，不做可配置）
  - **向后兼容硬约束**：无兴趣画像时排序结果与现状一致（用固定种子 fixture 断言）
- 前端：`useHotspotData` 透传参数；FeedFilters 或摘要卡展示命中域徽标（可解释性，PRD §2.5）
- 退出判据：pytest 排序/过滤用例（含兼容断言）；vitest 徽标展示用例

### T0.5 SK-01 摘要分区（后端 + 前端）

- 改动点：SK-01 daily-priority-intel 聚合输出按实践域分区；前端优先级摘要卡按域分组渲染（无画像时单组，等于现状）
- 退出判据：聚合单测（8 域分区/空画像降级单组）；前端快照或 RTL 断言

## P1 / P2（后续 goal，先占位不展开）

- P1：v0/v1 词表统一（v1 admission 8 维 label 扩实践域）、首页默认动线切换、词表周审计机制
- P2：行为反馈权重（attention 整合）、画像漂移提示
- 两者开工前须按本文件格式补各自 DoD 与验收门

## 收尾流程（每个 Phase 结束时执行）

1. 全量门禁：tsc / vitest / pytest / `generate_meta.py --check`
2. **独立功能验收**：派独立 agent，输入 = 本文件 + PRD，逐条对照真实运行的前端与 API 响应验收；产出验收报告（PASS/FAIL 逐条 + 证据），追加至 PROGRESS.md
3. **独立代码审计**：派 `code-reviewer`，范围 = 本 Phase 全部 diff；P0 级发现必须修复并复验后才可收口
4. 落账与提交：DEV_LOG 追加、显式 pathspec 提交（`docs:`/`feat:` 前缀按内容）、PRD 状态行更新

## 风险与开放问题

| 风险 | 缓解 |
|------|------|
| 词表规则覆盖率不足（纯规则打不准实践域） | P0 验收只要求 ≥80% 抽样准确率（80 条标注集上人评）；不足则 P1 立项 LLM 分类，本 goal 不扩 |
| 排序加权影响既有用户习惯 | 权重常量起步 + 向后兼容断言 + 空画像零差异 |
| `practice_domain` 字段写入性能（batch_classify 全量回填） | 仅对新采集条目即时打标；存量回填走一次性脚本（dry-run 默认，符合 scripts 纪律），放 T0.1 收尾可选项 |
