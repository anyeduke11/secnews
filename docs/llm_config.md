# LLM 配置说明

## 概述

Phase 16 引入了 Hybrid AI 架构，支持多 LLM 提供商混合调度。配置文件位于 `config/llm.yaml`，通过 Pydantic schema（`backend/config/llm_schema.py`）校验。缺失配置文件时自动降级为外部 Agent 模式，不影响现有功能。

## 支持的 LLM 提供商

| 提供商 | type 值 | 需要 API Key | 费用 |
|--------|---------|-------------|------|
| Ollama | `ollama` | 否 | 免费（本地） |
| OpenAI | `openai` | OPENAI_API_KEY | 按量付费 |
| 通义千问 | `openai_compatible` | QWEN_API_KEY | 按量付费 |
| Anthropic | `anthropic` | ANTHROPIC_API_KEY | 按量付费 |

## 配置每个提供商

### Ollama（本地推荐）

1. 安装 Ollama：`brew install ollama`（macOS）或官网下载
2. 拉取模型：`ollama pull qwen2.5:7b && ollama pull qwen2.5:14b`
3. 确保 Ollama 服务运行在 `http://127.0.0.1:11434`
4. 默认配置即可工作，无需 API Key

### OpenAI

1. 在 [platform.openai.com](https://platform.openai.com) 注册并创建 API Key
2. 设置环境变量：`export OPENAI_API_KEY="sk-xxx"`
3. 可选：修改 `models` 字段指定不同的模型名

### 通义千问（Qwen）

1. 在 [dashscope.aliyun.com](https://dashscope.aliyun.com) 开通服务并获取 API Key
2. 设置环境变量：`export QWEN_API_KEY="sk-xxx"`
3. 阿里云 DashScope 兼容 OpenAI API 格式，使用 `openai_compatible` 类型

### Anthropic

1. 在 [console.anthropic.com](https://console.anthropic.com) 获取 API Key
2. 设置环境变量：`export ANTHROPIC_API_KEY="sk-ant-xxx"`
3. 目前仅用于 `summary` 和 `chunk_summary` 两类任务

## 任务覆写（Task Overrides）

`task_overrides` 允许为特定任务指定独立的 provider 和参数，覆盖全局配置：

```yaml
task_overrides:
  t1_score:           # 评分任务：本地跑，低延迟零成本
    provider: ollama
    model: qwen2.5:7b
    temperature: 0.0
    max_tokens: 50
  t3_summary:         # 摘要任务：GPT-4o 保证质量
    provider: openai
    model: gpt-4o
    temperature: 0.3
    max_tokens: 500
```

目前支持的任务 ID：
- `t1_score` — 文章评分
- `t3_summary` — 单篇摘要
- `t3_chunk_summary` — 分块摘要（支持 `batch_size` 参数）

## 降级策略（Fallback）

`fallback_order` 定义了当默认 provider 失败时的降级顺序。默认策略：

```
ollama（本地免费）→ qwen（国产便宜）→ openai（兜底）
```

每个 provider 的请求失败（超时、限流、API 错误）后会自动尝试下一个。所有 provider 都失败时，返回错误并记录日志。

## 费用控制

```yaml
cost_alert:
  daily_usd_limit: 5.0       # 日消费上限
  monthly_usd_limit: 100.0   # 月消费上限
  on_exceeded: warn           # 超限行为：warn / block / fallback_local
```

- `warn`：仅警告，不阻断请求
- `block`：阻断所有远程 API 调用
- `fallback_local`：自动切换到本地 Ollama

`rate_limits` 控制 API 调用频率，避免触发限流：

```yaml
rate_limits:
  requests_per_minute: 60      # 每分钟请求数上限
  tokens_per_minute: 100000    # 每分钟 token 上限
```

## 缓存策略

LLM 响应结果默认缓存 24 小时，减少重复调用和费用：

```yaml
cache:
  enabled: true
  ttl_seconds: 86400        # 24 小时过期
  similarity_threshold: 0.95 # 语义相似度阈值，高于此值命中缓存
```

缓存键基于输入文本的 embedding 相似度匹配，而非精确字符串匹配。`similarity_threshold` 控制匹配灵敏度，值越高匹配越严格。

## 总开关

```yaml
enabled: true  # false 时完全禁用 Hybrid AI，降级为外部 Agent 模式
```

当 `enabled: false` 或配置文件不存在时，系统回退到 Phase 16 之前的 v1.7 Option A 模式（外部 Agent 驱动），不影响现有功能。

## 快速开始

1. **最小配置**：仅安装 Ollama 并拉取模型，`llm.yaml` 默认配置即可工作
2. **混合模式**：设置 OpenAI API Key，系统自动在本地和云端之间调度
3. **全量配置**：按需设置 Qwen 和 Anthropic 的 API Key，获得完整的降级保障

## 常见问题

**Q: 配置文件不存在会怎样？**
A: `load_llm_config()` 返回 `None`，系统静默降级为外部 Agent 模式，不报错。

**Q: 多个 provider 如何选择？**
A: 默认使用 `default_provider`，失败后按 `fallback_order` 依次尝试。`task_overrides` 可以按任务覆盖。

**Q: 本地 Ollama 需要什么硬件？**
A: qwen2.5:7b 约 4GB 显存，qwen2.5:14b 约 8GB 显存。无 GPU 也可用 CPU 运行，但速度较慢。