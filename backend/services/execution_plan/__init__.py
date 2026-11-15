"""execution_plan 包 — v0.8.9 P3 边界协议 (P10 设计 D1 继承)。

角色分工 (P10 §1): LLM(dsh/ai_hub) 起草边界建议 → 人审批(默认拒绝) →
后端代码硬性 enforce → pi 只能在边界内活动 (R-3)。
本包承载: schema (ExecutionPlan) + 服务 (submit/approve/reject 冻结状态机)
+ 生成器 (ai_hub 草稿 + 人工手写兜底, C3-3)。enforce 编译器在 R-3 (P4)。
"""
