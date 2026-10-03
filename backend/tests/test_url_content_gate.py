"""URLContentGate SSRF 防护回归 — v0.8.6 P0-9 / 审计 F0-11 (R6)。

F0-11 根因: ``_fetch_title`` 此前裸 ``session.get(url, ssl=False)`` —
item.url 是采集来的**不可信输入**, 可指向内网 (读回响应 = SSRF), 且
TLS 校验被禁用 (MITM)。其前置校验门 URLValidityGate 又已从管线移除,
正文抓取成为唯一出站路径却零校验。

锁定 (审计验收 "SSRF 用例 (http://127.0.0.1) 被阻断"):
1. 内网/回环 URL 在**发起任何连接前**被 validate_url 拒收 (error 以
   "SSRF blocked" 开头) — 用例不触网, 字面 IP 路径不依赖 DNS;
2. ``run_async`` 把 SSRF 阻断映射为可区分的 ``ssrf_blocked`` flag
   (quality_check_logs 里可审计), 不混入普通 ``url_unreachable``;
3. 源码契约: ``ssl=False`` 不得回归 (本仓守卫测试惯用的源文本断言)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.url_content_gate import URLContentGate, _fetch_title

_GATE_SRC = Path(__file__).resolve().parents[1] / "quality" / "url_content_gate.py"


def _make_item(url: str) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id="ssrf-probe",
        title="Test Article",
        source="test",
        url=url,
        category=Category.AI,
        published_at=now,
        fetched_at=now,
    )


class TestFetchTitleBlocksSsrf:
    @pytest.mark.asyncio
    async def test_loopback_blocked_before_connect(self):
        """审计验收用例: http://127.0.0.1 在连接前被拒, 错误串带 SSRF 标记。"""
        title, error = await _fetch_title("http://127.0.0.1/admin", 8)
        assert title == ""
        assert error is not None and error.startswith("SSRF blocked")

    @pytest.mark.asyncio
    async def test_private_ip_blocked(self):
        """RFC1918 私网段同样拒收 (字面 IP 路径, 不触网不依赖 DNS)。"""
        title, error = await _fetch_title("http://192.168.1.1/router", 8)
        assert title == ""
        assert error is not None and error.startswith("SSRF blocked")

    @pytest.mark.asyncio
    async def test_localhost_name_blocked(self):
        title, error = await _fetch_title("http://localhost:8000/api/secret", 8)
        assert error is not None and error.startswith("SSRF blocked")

    @pytest.mark.asyncio
    async def test_non_http_scheme_blocked(self):
        """file:// 等非白名单 scheme 拒收。"""
        title, error = await _fetch_title("file:///etc/passwd", 8)
        assert error is not None and error.startswith("SSRF blocked")


class TestGateFlagsSsrf:
    @pytest.mark.asyncio
    async def test_run_async_marks_ssrf_blocked(self):
        """SSRF 阻断必须打 ssrf_blocked flag (非 url_unreachable) —
        门禁日志里两类失败可审计区分。"""
        gate = URLContentGate(timeout=2)
        result = await gate.run_async(_make_item("http://127.0.0.1/x"))
        assert result.passed is False
        assert "ssrf_blocked" in result.flags
        assert "url_unreachable" not in result.flags
        assert "SSRF blocked" in (result.reason or "")


class TestNoSslDisable:
    def test_no_ssl_false_in_calls(self):
        """AST 契约: 任何调用不得传 ssl=False (F0-11 "移除 ssl=False" 验收)。

        AST 断言而非源文本 — docstring 引述历史时不误报; 且覆盖文件内
        全部调用点 (直接/间接禁用 TLS 都算违规)。
        """
        import ast

        tree = ast.parse(_GATE_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "ssl":
                        assert (
                            isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ), f"line {node.lineno}: ssl 参数必须是 True, 不得禁用校验"
