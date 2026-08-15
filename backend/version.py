"""应用版本号单一来源 (Single Source of Truth)。

所有需要展示应用版本的地方 (main.py FastAPI(version=...)、
exceptions.py 错误响应体、/api/health 等) 一律从这里 import,
禁止在别处再硬编码应用版本号。

注意: API 响应体内的 ``version`` 字段若表示 *数据格式/协议版本*
(如 export envelope、sync bundle), 与应用版本无关, 不受此约束。

v0.4.0 (2026-08-16): 审计重构 — Phase 0-6 全部修复落地
(知识闭环数据流 / 采集管道 / 同步安全 / 导航操作流统一), 见
docs/audit_first_principles_plan.md。
"""

APP_VERSION = "0.4.0"
