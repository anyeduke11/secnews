# 热点地图 · 全站 UI 设计方案（UI_DESIGN_SPEC）

> 版本：Stage 1 · 2026-08-19
> 配套：`docs/LAYOUT_REDESIGN_PLAN.md`（路线图）｜ `docs/LAYOUT_AUDIT_STAGE_0.md`（审计）
> 本方案 = 信息架构 + 视觉方向 + 组件状态规范 + 操作动线 + 屏幕适配 + 备份还原 SOP。

---

## 1. 产品理念与目标用户

**一句话定位**：AI 时代 IT 与安全从业者的「热点工作站」——三层架构（资料层 → 判断层 → 行动层）串联个人情报流水线。

| 维度 | 结论 |
|---|---|
| 目标用户 | IT / 安全从业者（10 年经验层），重度 RSS + 图谱 + 标讯场景 |
| 关键任务 | ① 扫热点（/data）② 盯信号（/judge）③ 出活（/action）④ 知识复利（/knowledge） |
| 产品理念 | 信息密度高但不乱；一次会话完成「看 → 判 → 动」闭环；数据可信可溯 |
| 品牌约束 | 暗色技术美学 + 亮色日报版双轨；等宽字体工程感；分类色板即品牌识别 |

## 2. 信息架构（IA）

### 2.1 顶层结构（三层流水线为骨架）

```
SecNews 工作站
├── 资料层  /data            热点瀑布流 · 采集 · 收藏 · 历史
│   ├── /data/import         信息导入（RSS/URL/文件）
│   ├── /data/favorites      收藏
│   └── /data/history        历史
├── 判断层  /judge           趋势 · 标讯分析
│   ├── /judge/trends        趋势分析
│   └── /judge/bid-analysis  标讯分析
├── 行动层  /action          报告 · 复利 · 待办 · 发件 · 复核 · 技能 · CodeGarden · 标讯预警
└── 知识库  /knowledge       4 领域（导入/处理/编译/复利）× 6 模式（简报/扫描/深读/预警/发件/复盘）
```

### 2.2 命名与动线冲突治理（Stage 1 批 1）

| 问题 | 决策 | 理由 |
|---|---|---|
| `/brief` vs `/knowledge/briefing` | **并存**，标注为「全局简报视图」与「知识库 6 模式之一」 | 二者渲染不同组件，前者跨实体、后者属阅读流；Stage 6 按使用频率定去留 |
| `/deep/:type/:id` vs `/knowledge/deep-read/:id` | **并存**，前者跨实体深读、后者属知识库阅读流 | 同上 |
| 4 领域 vs 6 模式两级导航 | 保留，Stage 1 不动结构 | 涉及真实交互回归（Stage 6 风险 L3 需逐页核验） |
| 旧路由 `/judge/*` 6 条跳转 | 统一标注「v0.4 兼容性保留」 | 防误删老深链，Stage 6 再清理 |

## 3. 视觉方向

### 3.1 美学定位

**「工程终端 × 日报排版」**：等宽字体（JetBrains Mono）传递工程感，卡片栅格 + 分类色板做信息分区，克制的动效（120–320ms ease-out）只在高影响力时刻出现。

### 3.2 色彩

- **主 accent**：`--accent` 亮青（亮 `#00acc1` / 暗 `#00bcd4`），所有可点态 / 激活态 / 链接的锚点色
- **分类色板即品牌**：ai / security / finance / startup / bid / general / github 七色，亮暗双轨独立
- **语义色**：success / warning / error / info 亮暗双轨

### 3.3 排版（Stage 1 字号下限）

| 层级 | 规格 | 理由 |
|---|---|---|
| 正文 / 组件文本 | ≥ **11px** | 可读性下限（治理前存在 8/9/10px 122 处违规） |
| CTA / 按钮 | **12px** | 主操作需权重差异，仅 1px 差不足以在扫描中区分 |
| 基础字号（桌面） | 13px | 工作站密度基线 |
| 基础字号（手机 / 平板 / 宽屏） | 14px | 触摸缩放与远视距补偿 |
| 元数据 | 用 `--text-muted` 颜色 + `tabular-nums` 降权 | 不再用更小字号，避免越界 |

> `--text-min: 11px` token 已就位（`index.css`）。tsx 内联 `text-[8/9/10px]` 62 处属 Stage 2 收编范围。

## 4. 组件状态规范

| 组件 | 状态 | 规格 | 备注 |
|---|---|---|---|
| **卡片** `card-base` | default | `--bg-card` + `--border-color` + `radius-md` | Stage 1 唯一卡片类 |
| | hover | border 升 `--text-muted`，背景升 `--bg-hover` | legacy `card-compact` 收编后获得此 affordance |
| | active | 背景保持 `--bg-hover` | |
| **主按钮** `btn-primary` | 12px / 700 / `--accent` 填充 | hover 85% 透明，active scale .97，disabled 35% 透明 | CTA |
| **描边按钮** `btn-accent` | 12px / 600 / accent 描边 | hover `--accent-soft` 填充 | 次 CTA |
| **幽灵按钮** `btn-ghost` | 12px / 500 / 中性描边 | hover 文本升 `--text-primary` | 三级操作 |
| **徽章** `.cluster-badge` 等 | 11px / 700 / tracking .06em | 辨识靠粗体 + 字距，非更小字号 | Stage 1 从 10px 升 |
| **输入** `.editorial-input/select` | focus `--accent` 边 + 3px soft 光晕 | hover 背景升 | 表单基线 |

> **组件分期策略**：卡片已统一；按钮 / 徽章已收敛；`/codegarden` 与 `/knowledge` 深层组件属 Stage 4/6 专项。

## 5. 操作动线（三大痛点治理）

### 5.1 信息层级混乱 → 字号 / 色彩双轨降权
- **调整**：正文 ≥11px、CTA 12px、元数据用色降权（不再用小字号）；宽屏栅格升 4 列缩短标题行长。
- **理由**：扫描路径中主标题行长决定阅读速度；字号下限保证任何信息不被「隐形」。

### 5.2 操作动线绕 → 保留三层骨架 + 路由命名治理
- **调整**：App.tsx 拆分为 `ThemeContext / lazy-imports / routes` 三模块，路由表即结构图；冲突路由加注释决策。
- **理由**：路由表可读 = 动线可读；`FavoritesPanel` 死代码移除减少认知负担；后续 Stage 按频率清理兼容跳转。

### 5.3 视觉一致性差 → card 基线 + 主题双轨
- **调整**：34 处 legacy 卡片类（16 文件）全量收编 `card-base`；`:root` 默认亮色、`:root[data-theme="dark"]` 覆盖。
- **理由**：消灭「同站不同卡片」；CSS 默认与 JS 默认对齐后，首次加载无闪色，亮色优先与 v1.9 日报版叙事一致。

## 6. Stage 1 变更明细（全站基础设施）

| # | 任务 | 改动 | 验证 |
|---|---|---|---|
| 1 | card 基线 | legacy CSS 块删除，16 文件类名机械替换 | 292/292 tests |
| 2 | 主题双轨 | CSS 亮为默认、dark 覆盖 | 首屏无闪色 |
| 3 | App 拆分 | 306 → 15 行，3 新模块 | tsc / build 通过 |
| 4 | 字号下限 | index.css 16 处 9/10px → 11px；按钮 3 类 → 12px | grep 全站无 <11px |
| 5 | 断点 | 平板 / 宽屏基础字号兜底；栅格 2xl 起 4 列；CategoryNav 移动端横滚 | 4 分辨率目检 |

## 7. 屏幕适配规范

| 断点 | 行为 | 调整 |
|---|---|---|
| <640px 手机 | CategoryNav 单行横滚（不换行 3–4 行吃首屏） | 负 margin 对齐页面左缘 |
| 640–1023px 平板 | 基础字号 +1px | 触摸距离补偿 |
| 1024–1535px 桌面 | 3 列栅格 | 工作站密度 |
| ≥1536px 宽屏 | 4 列栅格 + 基础字号 +1px | 标题行长收束 + 远视距 |

## 8. 备份与一键还原 SOP

```bash
# 任一 Stage 启动前备份（快照含未提交改动，HEAD 不变）
./scripts/layout-backup.sh <stage-name>

# 一键还原到某 stage（HEAD 不动，工作树覆盖为备份内容，当前改动自动 stash 可找回）
./scripts/layout-restore.sh <stage-name>
./scripts/layout-restore.sh latest        # 最近一次备份
./scripts/layout-restore.sh list          # 列出所有备份
git stash pop                             # 找回还原时被覆盖的工作
```

> 当前备份：`backup/stage-1-infra-20260819-094211` @ `f5d841cd`
> 还原：`./scripts/layout-restore.sh stage-1-infra`

## 9. 后续 Stage 路线（治理优先级）

| Stage | 范围 | 解决痛点 | 风险 |
|---|---|---|---|
| 2 | `/data` 首屏聚合 + `/settings` 分区 | 信息层级 | L1 |
| 3 | `/judge` 卡片收编 + 空态 | 一致性 | L1 |
| 4 | `/action` 栅格收编 + CodeGarden 组件化 | 一致性 | L2 |
| 5 | `/brief` + 剩余顶层 | 动线 | L1 |
| 6 | `/knowledge` 6 模式整合 + 断点全量 | 动线 | **L3** |
