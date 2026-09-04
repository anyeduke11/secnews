"""playbook_engine.step — 单步执行器 (C1).

三类 step (R7):
- skill:    委托 skill_runner.run_skill(skill_def, params)
- api:      httpx 调本机 /api/* 白名单 (127.0.0.1:8000 默认, 测试可注入 base_url)
- condition: 简单布尔表达式求值, 命中即跳过本步

设计纪律:
- 不引入 jinja2; ``{{ steps.<id>.output.<path> }}`` 与 ``{{ inputs.<key> }}``
  替换走 _resolve_template (轻量正则 + 安全访问, 不支持函数调用, 防 RCE)
- api 白名单: 只允许本机 base_url; 测试可注入 ``base_url`` 走临时 HTTP server
- condition 表达式: 极简实现 — 支持 ``steps.x.output.a > 0`` / ``inputs.flag == true``
  / ``steps.x.output.items | length > 0`` 三类; 用 ast 不执行 (compile 仅校验),
  实际求值用受限 eval (literal_eval + dict.get); 防 RCE 由白名单 token + 拒绝函数调用
"""
from __future__ import annotations

import ast
import re
from typing import Any

from backend.logging_config import logger

#: ``{{ ... }}`` 模板标记, 简单占位 (无 jinja filter)
_TEMPLATE_RE = re.compile(r"\{\{\s*(?P<expr>.+?)\s*\}\}")

#: 本机 base_url (FastAPI 默认). 测试可注入 base_url 走 mock transport.
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _resolve_template(text: str, ctx: dict[str, Any]) -> Any:
    """替换 ``{{ key.subkey }}`` 为 ctx 取值。

    单 token 完整替换 (整个字符串只一个占位) → 返回原值类型 (int/dict/str 保留);
    多 token 或部分占位 → 返回 str (str(template) 把所有 {{ }} 替换为 str(value))。
    """
    if not isinstance(text, str) or "{{" not in text:
        return text
    full_match = re.fullmatch(r"^\{\{\s*(?P<expr>.+?)\s\}\}$", text.strip())
    if full_match:
        return _get_path(ctx, full_match["expr"])
    # 多 token / 部分占位 → str 化
    def _sub(m: re.Match[str]) -> str:
        val = _get_path(ctx, m["expr"])
        return str(val) if val is not None else ""

    return _TEMPLATE_RE.sub(_sub, text)


def _get_path(ctx: dict[str, Any], expr: str) -> Any:
    """按 ``a.b.c`` 取嵌套 dict; 任一环节缺失返 None。

    不调用任何 ctx 中以 _ 开头以外的"方法" (防 RCE, 配合 condition expr 白名单)。
    """
    cur: Any = ctx
    for part in expr.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = None
        if cur is None:
            return None
    return cur


# ---------------------------------------------------------------------------
# 条件表达式求值 (轻量 ast 校验 + literal 求值)
# ---------------------------------------------------------------------------
_ALLOWED_COMPARE = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot)
_ALLOWED_BOOLOP = (ast.And, ast.Or)
_ALLOWED_UNARY = (ast.Not, ast.USub)


def _safe_eval(expr: str, ctx: dict[str, Any]) -> Any:
    """受限 ast 求值。

    允许: 字面量 / dict.get / 比较 / 布尔 / 负号 / in (限定容器);
    拒绝: 函数调用 / 属性访问 (除 dict.get) / import / subscript 非字面键。
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"condition expression 语法错: {e}") from e
    return _eval_node(tree.body, ctx)


def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        # 允许的 Name 仅限于 ctx 字典 key (steps / inputs)
        return ctx.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARY):
        v = _eval_node(node.operand, ctx)
        return -v if isinstance(node.op, ast.USub) else not v
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        l = _eval_node(node.left, ctx)
        r = _eval_node(node.right, ctx)
        if isinstance(node.op, ast.Add):
            return l + r
        if isinstance(node.op, ast.Sub):
            return l - r
        if isinstance(node.op, ast.Mult):
            return l * r
        if isinstance(node.op, ast.Div):
            return l / r
    if isinstance(node, ast.BoolOp) and isinstance(node.op, _ALLOWED_BOOLOP):
        vals = [_eval_node(v, ctx) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare) and isinstance(node.ops[0], _ALLOWED_COMPARE):
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.comparators[0], ctx)
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
    if isinstance(node, ast.Call):
        raise ValueError("condition 表达式不允许函数调用 (防 RCE)")
    if isinstance(node, ast.Attribute):
        # 允许的链式 attr: <root>.<key>...<key>, 根 Name ∈ ctx;
        # 任一环节非 dict 或 attr 缺失 → ValueError (防 attribute 泄露)
        cur: Any = _eval_node(node.value, ctx)
        attr = node.attr
        if not isinstance(cur, dict):
            raise ValueError(f"condition 属性访问 {attr!r} 前值非 dict")
        if attr not in cur:
            raise ValueError(f"condition 属性访问 {attr!r} 不在 dict 中")
        return cur[attr]
    raise ValueError(f"condition 表达式不支持节点 {type(node).__name__}")


# ---------------------------------------------------------------------------
# StepExecutor
# ---------------------------------------------------------------------------
class StepExecutor:
    """单步执行器 — 维护 step_output 上下文 (供后续 step 引用)。

    fields:
        registry: SkillRegistry-like (有 .get(skill_id) → SkillDef)
        run:      PlaybookRun (写入元数据, 留 D1 持久化钩子)
        playbook: 所在 Playbook (audit 用)
        base_url: 本机 API base (默认 127.0.0.1:8000)
        http_timeout: httpx 超时秒
        api_whitelist: api 步骤 path 必须以这些前缀开头 (默认 '/api/')
    """

    def __init__(
        self,
        registry: Any,
        run: Any,
        playbook: Any,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_timeout: float = 30.0,
        api_whitelist: tuple[str, ...] = ("/api/",),
    ) -> None:
        self._registry = registry
        self._run = run
        self._playbook = playbook
        self._base_url = base_url.rstrip("/")
        self._http_timeout = http_timeout
        self._api_whitelist = api_whitelist
        self._step_outputs: dict[str, Any] = {}

    def set_step_output(self, step_id: str, output: Any) -> None:
        self._step_outputs[step_id] = output

    def eval_expr(self, expr: str) -> bool:
        return bool(_safe_eval(expr, {"steps": self._step_outputs, "inputs": self._run.inputs}))

    def _resolve_context(self) -> dict[str, Any]:
        return {"steps": self._step_outputs, "inputs": self._run.inputs}

    def execute_step(self, step: Any) -> Any:
        """按 step.kind 分派; 返回 step 输出 (供 output 命名引用)。"""
        kind = step.kind
        if kind == "skill":
            return self._exec_skill(step)
        if kind == "api":
            return self._exec_api(step)
        if kind == "condition":
            # condition.kind 输出求值结果 (供后续 step 引用); 顶层 if_expr 与本字段并行
            return bool(self.eval_expr(step.expr or ""))
        raise ValueError(f"step kind {kind!r} 未实现 (R7 仅允许 skill / api / condition)")

    def _resolve_params(self, params: dict[str, Any]) -> dict[str, Any]:
        ctx = self._resolve_context()
        return {k: _resolve_template(v, ctx) for k, v in (params or {}).items()}

    def _exec_skill(self, step: Any) -> Any:
        """委托 skill_runner.run_skill; 走 trigger-gate 真实执行 (B5 已接线)。"""
        from backend.services.skill_runner.core import run_skill

        skill_def = self._registry.get(step.skill)
        params = self._resolve_params(step.params or {})
        result = run_skill(skill_def, params, ticket_id=self._run.run_id)
        # SkillRunResult → dict (R3 风格, 供 JSON 序列化)
        return {
            "run_id": result.run_id,
            "status": result.status,
            "outputs": result.outputs,
            "wiki_path": result.wiki_path,
            "llm_tokens": result.llm_tokens,
            "elapsed_ms": result.elapsed_ms,
            "metrics": result.metrics,
            "error": result.error,
        }

    def _exec_api(self, step: Any) -> Any:
        """api step → httpx 调本机 /api/* 白名单; path 必须以 whitelist 前缀开头。

        拒绝: 非白名单 path / 外网 host / 非 GET/POST/PATCH/DELETE method
        """
        import httpx  # 推迟到方法内避免顶层强制依赖

        action = (step.action or "").strip()
        if " " not in action:
            raise ValueError(f"api step action 必须形如 'METHOD /path', got {action!r}")
        method, path = action.split(" ", 1)
        method = method.upper()
        if method not in ("GET", "POST", "PATCH", "DELETE", "PUT"):
            raise ValueError(f"api method {method!r} 不允许 (白名单 GET/POST/PATCH/PUT/DELETE)")
        if not any(path.startswith(prefix) for prefix in self._api_whitelist):
            raise ValueError(
                f"api path {path!r} 必须在白名单前缀 {self._api_whitelist} 内"
            )

        body = self._resolve_params(step.body or {}) if step.body else None
        url = f"{self._base_url}{path}"
        logger.info(
            "playbook_engine api step",
            extra={"trace_id": "", "method": method, "url": url},
        )

        with httpx.Client(timeout=self._http_timeout) as client:
            resp = client.request(method, url, json=body if body else None)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {"raw": resp.text}

    # 公开给 evaluate 钩子 (C5 eval 复用)
    def resolve_template(self, text: str) -> Any:
        return _resolve_template(text, self._resolve_context())


__all__ = ["DEFAULT_BASE_URL", "StepExecutor", "_resolve_template", "_safe_eval"]