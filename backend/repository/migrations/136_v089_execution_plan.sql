-- v0.8.9 P3 C3-1 (D2 裁决): ExecutionPlan 落列 — 另加三列, plan_json 账本语义不动
-- (plan_json 装账本审批快照 {proposal_id, kind, dual_sign}, migration 131;
--  边界计划是另一语义, 混用会混淆账本 run 与 action run 的审计 — 勘察 §8)
-- executor: 'manual' | 'pi' (谁执行; R-1 人工回执 claim 时落 'manual', R-3 pi 派发落 'pi')
-- boundary_hash: 审批冻结的 plan 内容指纹 (sha256, L4 审计逐条比对依据)
-- execution_plan_json: 审批信封 {plan, status: draft|approved|rejected, submitted_by,
--                  approved_by, approved_at, source: manual|ai_draft} (P10 §4: 存 run 行内不加表)

ALTER TABLE v1_runs ADD COLUMN executor TEXT;
ALTER TABLE v1_runs ADD COLUMN boundary_hash TEXT;
ALTER TABLE v1_runs ADD COLUMN execution_plan_json TEXT;
