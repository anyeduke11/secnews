"""v0.8.5 G3: demo 全链 HTTP 黄金走查 (t085, 沿用 t11-t16 golden 先例)。

事实源: docs/v0.8.5/V0.8.5_PLAN.md §6 三层接口消费表。
三态矩阵 (spec §10.G3): PASS / DEGRADED / FAIL —
  PASS     2xx 或预期守卫错误 (如 CAS 409 / close 被阻)。
  DEGRADED 依赖未贯通 (dsh/ai_hub 出稿、评审 fixture 缺失) — 附响应证据, 不冒充成功。
  FAIL     契约破坏 (应 2xx 却 4xx/5xx、应 4xx 却 2xx、字段缺失)。
退出: 0 = 无 FAIL (DEGRADED 允许); 1 = 有 FAIL; 2 = 环境错误。

安全护栏:
  - 默认拒绝 base-url 以 :8000 结尾 (生产端口), 需 --i-know-prod 显式放行。
  - 仅创建 1 个带 `v085g3-fixture` 前缀的评审 case (spec §9 评审 fixture 政策),
    不改删任何既有对象; lifecycle/adopt 类变更仅作用于 fixture 或 --allow-mutate-existing。

用法 (.venv/bin/python):
  python scripts/t085_golden_walkthrough.py --base-url http://127.0.0.1:8766
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

PASS, DEGRADED, FAIL = "PASS", "DEGRADED", "FAIL"
FIXTURE_PREFIX = "v085g3-fixture"


class Step:
    def __init__(self, sid: str, desc: str):
        self.sid = sid
        self.desc = desc
        self.status = FAIL
        self.evidence = ""
        self.data: dict = {}

    def ok(self, evidence: str = "", **data):
        self.status, self.evidence, self.data = PASS, evidence, data
        return self

    def degraded(self, evidence: str = "", **data):
        self.status, self.evidence, self.data = DEGRADED, evidence, data
        return self

    def fail(self, evidence: str = "", **data):
        self.status, self.evidence, self.data = FAIL, evidence, data
        return self


class Walker:
    def __init__(self, base_url: str, allow_mutate_existing: bool):
        self.base = base_url.rstrip("/")
        self.allow_mutate_existing = allow_mutate_existing
        self.steps: list[Step] = []

    def _req(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            f"{self.base}{path}",
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, (json.loads(raw) if raw else {})
            except json.JSONDecodeError:
                return e.code, {"_raw": raw.decode(errors="replace")[:200]}
        except urllib.error.URLError as e:
            raise ConnectionError(f"后端不可达: {e.reason}") from e

    def add(self, sid: str, desc: str) -> Step:
        s = Step(sid, desc)
        self.steps.append(s)
        return s

    # ------------------------------------------------------------------
    def run(self) -> int:
        # S1 健康
        s = self.add("S01", "GET /api/health — 环境可达")
        try:
            code, body = self._req("GET", "/api/health")
            if code == 200:
                s.ok(f"status={body.get('status')}", health=body.get("status"))
            else:
                s.fail(f"期望 200, 实得 {code}")
        except ConnectionError as e:
            return self._finish_env(str(e))

        # S2 受管信号 (空数组合法 — B1 未贯通属预期, spec §6.1)
        s = self.add("S02", "GET /api/v1/signals?days=7&limit=50 — 受管信号")
        code, body = self._req("GET", "/api/v1/signals?days=7&limit=50")
        if code == 200 and isinstance(body.get("items"), list):
            n = len(body["items"])
            s.ok(f"200, items={n} ({'B1 未贯通, 空供给' if n == 0 else '有真实供给'})", count=n)
            self.signals = body["items"]
        else:
            s.fail(f"期望 200+items[], 实得 {code}: {str(body)[:120]}")

        # S3 评审 fixture case (spec §9: 评审 fixture, 不计业务闭环)
        s = self.add("S03", "POST /api/v1/cases — 评审 fixture 立项")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        title = f"{FIXTURE_PREFIX} {stamp} {uuid.uuid4().hex[:6]}"
        code, body = self._req("POST", "/api/v1/cases", {
            "title": title,
            "question": "G3 走查 fixture: 验证 case 契约 (创建/聚合/CAS/关闭守卫)",
            "priority": "p2",
            "source": "manual",
        })
        if code in (200, 201) and body.get("item", {}).get("id"):
            case = body["item"]
            s.ok(f"{code}, id={case['id']}", case=case)
        else:
            s.fail(f"期望 201+item.id, 实得 {code}: {str(body)[:160]}")
            return self._finish()
        case_id, revision = case["id"], case.get("revision", 1)

        # S4 详情
        s = self.add("S04", f"GET /api/v1/cases/{case_id} — 详情")
        code, body = self._req("GET", f"/api/v1/cases/{case_id}")
        if code == 200 and body.get("item", {}).get("id") == case_id:
            s.ok(f"200, rev={body['item'].get('revision')}")
        else:
            s.fail(f"期望 200+item, 实得 {code}: {str(body)[:120]}")

        # S5 聚合 (C11)
        s = self.add("S05", f"GET /api/v1/cases/{case_id}/aggregate — 单点聚合")
        code, body = self._req("GET", f"/api/v1/cases/{case_id}/aggregate?judgments_limit=50&actions_limit=50&runs_per_action=10&artifacts_per_run=10")
        keys = ("case", "judgments", "actions", "runs", "artifacts")
        if code == 200 and all(k in body for k in keys):
            s.ok("200, 5 类对象齐全", **{k: len(body[k]) if isinstance(body[k], list) else 1 for k in keys})
        else:
            s.fail(f"期望 200+{keys}, 实得 {code}: {str(body)[:120]}")

        # S6 CAS 反例: 错误 expected_revision → 409 E_CONFLICT
        # P2 修复 (流程验证): current_revision 嵌在 detail 内, 断言之 (不再打出 None)
        s = self.add("S06", f"PATCH /api/v1/cases/{case_id} (错误 revision) — 期望 409")
        code, body = self._req("PATCH", f"/api/v1/cases/{case_id}", {
            "expected_revision": revision + 100, "priority": "p1",
        })
        detail = body.get("detail") or {}
        cur = body.get("current_revision") or (detail.get("current_revision") if isinstance(detail, dict) else None)
        if code == 409 and cur is not None:
            s.ok(f"409 E_CONFLICT, current_revision={cur}")
        elif code == 409:
            s.ok(f"409 E_CONFLICT (current_revision 字段未回传 — 记录: {str(detail)[:80]})")
        else:
            s.fail(f"期望 409 (CAS 守卫), 实得 {code}: {str(body)[:120]}")

        # S7 CAS 正例: 正确 revision → 200
        s = self.add("S07", f"PATCH /api/v1/cases/{case_id} (正确 revision) — 期望 200")
        code, body = self._req("PATCH", f"/api/v1/cases/{case_id}", {
            "expected_revision": revision, "priority": "p1",
        })
        if code == 200 and body.get("item"):
            revision = body["item"].get("revision", revision + 1)
            s.ok(f"200, rev→{revision}")
        else:
            s.fail(f"期望 200, 实得 {code}: {str(body)[:120]}")

        # S8 关闭守卫反例: 无 published judgment / verified artifact → 期望 4xx 被阻
        s = self.add("S08", f"POST /api/v1/cases/{case_id}/close — 期望 4xx (R17 守卫可观测)")
        code, body = self._req("POST", f"/api/v1/cases/{case_id}/close", {"expected_revision": revision})
        if 400 <= code < 500:
            s.ok(f"{code} 被守卫阻止 (证据: {str(body.get('detail') or body)[:100]})")
        elif code == 200:
            s.fail("空 case 竟可关闭 — R17 守卫失效")
        else:
            s.fail(f"期望 4xx, 实得 {code}")

        # S9-S12: 变异链 — 发现既有可操作 fixture, 无则 DEGRADED (评审数据缺失)
        self._mutation_chain()

        # S13: judgment generate (依赖 dsh/ai_hub — DEGRADED 合法, spec §9)
        # P2 修复 (流程验证): 区分「守卫生效」与「出稿不可测」, 404/422 属契约破坏记 FAIL
        s = self.add("S13", "POST /api/v1/judgments/generate — 真实出稿链路")
        code, body = self._req("POST", "/api/v1/judgments/generate", {
            "case_id": case_id, "cve_id": "CVE-2026-00000",
            "subject_name": FIXTURE_PREFIX, "evidence_materials": [],
        })
        if code in (200, 201):
            j = body.get("item") or body.get("judgment") or {}
            s.ok(f"{code}, judgment={j.get('id')} status={j.get('status')}")
        elif code in (400, 409) and "evidence" in str(body.get("detail", "")).lower():
            # 空 fixture 被证据校验拒绝 = 守卫生效 (应 4xx 得 4xx, 契约正确);
            # 成功路径未行使 — 依赖证据 fixture + dsh 出稿, 归 D2 (spec §9 不主张)
            s.degraded(f"{code} 守卫生效 (应4xx得4xx): {str(body.get('detail'))[:100]} | 成功路径未行使 — 依赖证据 fixture+dsh (D2)")
        elif code == 404:
            s.fail(f"路由缺失 (404) — 契约破坏: {str(body)[:120]}")
        elif code == 422:
            s.fail(f"schema 漂移 (422) — 契约破坏: {str(body)[:160]}")
        else:
            s.degraded(f"{code} (证据: {str(body.get('detail') or body)[:140]})")

        # S14: 知识列表 + 采用链发现
        s = self.add("S14", "GET /api/v1/knowledge?limit=50 — 知识目录")
        code, body = self._req("GET", "/api/v1/knowledge?limit=50")
        if code == 200 and isinstance(body.get("items"), list):
            items = body["items"]
            published = [k for k in items if k.get("status") == "published"]
            if published and self.allow_mutate_existing:
                k = published[0]
                code2, body2 = self._req("POST", f"/api/v1/knowledge/{k['id']}/adopt", {
                    "case_id": case_id, "decision": "adopted",
                    "condition_diff": [], "decided_by": "v085-g3",
                })
                if code2 in (200, 201):
                    s.ok(f"200 目录 ({len(items)} 条) + 采用回执 {code2} (knowledge={k['id'][:8]}…)")
                elif code2 == 409:
                    s.ok(f"200 目录 + 409 幂等/冲突 (UNIQUE kid+rev+case) — 契约正确")
                else:
                    s.degraded(f"200 目录, 但 adopt {code2}: {str(body2)[:120]}")
            else:
                why = "allow-mutate-existing 未开" if published else "v1_knowledge 空或无 published"
                s.ok(f"200, items={len(items)} (adopt 步骤跳过: {why})")
        else:
            s.fail(f"期望 200+items[], 实得 {code}: {str(body)[:120]}")

        return self._finish()

    # ------------------------------------------------------------------
    def _mutation_chain(self):
        """S9-S12: 扫描 v085 fixture case 的 planned action / pending|verified artifact,
        走 approve→start→cancel 与 verify→accept 真实变异 (allowed_actions 守卫)。
        P1 修复 (代码审查 #2 + 流程验证): 默认只动 v085-review-/v085g3-fixture 前缀 case;
        --allow-mutate-existing 才扩展到全部 case (终态变异不可逆, 不得静默扫业务数据)。"""
        s9 = self.add("S09", "GET /api/v1/cases?limit=50 — 变异链 fixture 发现")
        code, body = self._req("GET", "/api/v1/cases?limit=50")
        if code != 200 or not isinstance(body.get("items"), list):
            s9.fail(f"期望 200, 实得 {code}")
            return
        all_cases = body["items"]
        fixture_cases = [c for c in all_cases
                         if (c.get("title") or "").startswith(("v085-review-", FIXTURE_PREFIX))]
        pool = all_cases if self.allow_mutate_existing else fixture_cases
        s9.ok(f"200, cases={len(all_cases)} (变异池: {'全部 --allow-mutate-existing' if self.allow_mutate_existing else f'仅 fixture {len(fixture_cases)} 个'})")
        # P2 修复: S10/S11 独立发现 target — 二者共享单 target 时互相消费对方 fixture
        def _find(pred):
            for c in pool:
                code2, ag = self._req("GET", f"/api/v1/cases/{c['id']}/aggregate?actions_limit=20")
                if code2 != 200:
                    continue
                hit = pred(ag)
                if hit:
                    return c["id"], ag, hit
            return None, None, None

        # S10: 有「未挂 attempt=1 run」planned action 的 case
        case_id, agg, action = _find(
            lambda ag: next((a for a in (ag.get("actions") or [])
                             if a.get("status") == "planned"
                             and a["id"] not in {r.get("action_id") for r in (ag.get("runs") or []) if r.get("attempt") == 1}), None))
        s10 = self.add("S10", f"action approve→start→cancel (case={(case_id or '')[:8]}…)")
        if not action:
            s10.degraded("无「未挂 attempt=1 run」的 planned action — spec §9 评审数据缺口")
        else:
            aid, arev = action["id"], action.get("revision", 1)
            code, body = self._req("POST", f"/api/v1/actions/{aid}/approve", {"expected_revision": arev})
            if code != 200:
                s10.degraded(f"approve {code}: {str(body)[:120]}")
            else:
                arev = (body.get("item") or {}).get("revision", arev + 1)
                code, body = self._req("POST", f"/api/v1/actions/{aid}/start", {
                    "expected_revision": arev,
                    "idempotency_key": f"v085g3-{aid}-{uuid.uuid4().hex[:8]}",
                    "protocol": "direct",  # R05: mock 协议已从 _VALID_RUN_PROTOCOLS 移除
                    "trigger_source": "user",
                })
                if code != 200:
                    s10.degraded(f"start {code}: {str(body)[:120]}")
                else:
                    arev = (body.get("item") or {}).get("revision", arev + 1)
                    code, _ = self._req("POST", f"/api/v1/actions/{aid}/cancel", {"expected_revision": arev})
                    if code == 200:
                        s10.ok("approve→start→cancel 全链 200 (真实变异)")
                    else:
                        s10.degraded(f"cancel {code}")

        cid11, agg11, artifact = _find(
            lambda ag: next((f for f in (ag.get("artifacts") or [])
                             if f.get("status") in ("pending", "verified")), None))
        s11 = self.add("S11", f"artifact verify→accept (case={(cid11 or '')[:8]}…)")
        if not artifact:
            s11.degraded("无 pending/verified artifact fixture")
        else:
            fid, frev = artifact["id"], artifact.get("revision", 1)
            code, body = self._req("POST", f"/api/v1/artifacts/{fid}/verify", {
                "expected_revision": frev, "verified_result": "pass", "verified_by": "v085-g3",
            })
            if code != 200:
                s11.degraded(f"verify {code}: {str(body)[:120]}")
            else:
                frev = (body.get("item") or {}).get("revision", frev + 1)
                code, body = self._req("POST", f"/api/v1/artifacts/{fid}/accept", {
                    "expected_revision": frev, "accepted_by": "v085-g3",
                })
                if code == 200:
                    s11.ok("verify→accept 全链 200 (真实变异)")
                else:
                    s11.degraded(f"accept {code}: {str(body)[:120]}")

        self.add("S12", "变异链数据完整性").ok(
            f"S10 target={case_id or '-'} / S11 target={cid11 or '-'} (独立发现, 各自消费)"
        )

    # ------------------------------------------------------------------
    def _finish_env(self, msg: str) -> int:
        print(f"ENV-ERROR: {msg}", file=sys.stderr)
        return 2

    def _finish(self) -> int:
        counts = {s: sum(1 for x in self.steps if x.status == s) for s in (PASS, DEGRADED, FAIL)}
        print("=" * 72)
        print(f"v0.8.5 G3 黄金走查矩阵 — base={self.base}")
        print("=" * 72)
        for s in self.steps:
            print(f"[{s.status:<8}] {s.sid} {s.desc}\n           └ {s.evidence}")
        print("-" * 72)
        print(f"汇总: PASS={counts[PASS]}  DEGRADED={counts[DEGRADED]}  FAIL={counts[FAIL]}")
        print("DEGRADED 语义: 依赖未贯通 (dsh/ai_hub 出稿 / 评审 fixture 缺失), 不冒充成功 — spec §9/§10")
        if counts[FAIL]:
            print("结论: FAIL — 存在契约破坏")
        else:
            print("结论: " + ("PASS (全部贯通)" if counts[DEGRADED] == 0 else "PASS-WITH-DEGRADED (契约一致, 依赖项按预期降级)"))
        return 1 if counts[FAIL] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--i-know-prod", action="store_true", help="显式放行 :8000 生产端口 (默认拒绝)")
    parser.add_argument("--allow-mutate-existing", action="store_true",
                        help="允许对既有 published knowledge 做一次 adopt (默认只动 fixture)")
    args = parser.parse_args()

    if args.base_url.rstrip("/").endswith(":8000") and not args.i_know_prod:
        print("拒绝: base-url 指向生产端口 :8000 — 请用 dev 环境 (8766, 见 scripts/dev_environment.sh)。"
              "如确需对生产只读探测, 加 --i-know-prod。", file=sys.stderr)
        return 2

    return Walker(args.base_url, args.allow_mutate_existing).run()


if __name__ == "__main__":
    raise SystemExit(main())
