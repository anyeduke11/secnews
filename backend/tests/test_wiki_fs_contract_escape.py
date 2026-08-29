"""Frontmatter 转义与引号契约 — 锁定 2026-08-29 数据损坏修复的行为边界。

两类历史损坏 (见 scripts/fix_wiki_frontmatter_escape.py 文档):
  A. json.dumps 默认 ensure_ascii=True → 中文写成字面 ``\\uXXXX`` 存进 md;
  B. ``_quote`` 不转义内层引号 → 含 JSON 的值写成非法 YAML。
"""
from __future__ import annotations

import json

from backend.wiki_fs.contract import (
    _quote,
    _unquote,
    parse_frontmatter,
    serialize_frontmatter,
)


def _fm_of(text: str) -> dict:
    return parse_frontmatter(text)[0]


class TestEscapeDecoding:
    """A 类: 历史 \\uXXXX 必须读回真字符, 且不能误伤真实反斜杠。"""

    def test_bare_block_item_decoded(self):
        text = "---\nid: x\ntags:\n  - \\u4e66\\u7b7e\n  - SmartMarks\n---\nbody"
        assert _fm_of(text)["tags"] == ["书签", "SmartMarks"]

    def test_quoted_scalar_decoded(self):
        text = '---\nid: x\ntopic: "\\u6e17\\u900f\\u6d4b\\u8bd5"\n---\nbody'
        assert _fm_of(text)["topic"] == "渗透测试"

    def test_inline_list_items_decoded(self):
        text = '---\nid: x\ntags: ["\\u4e66\\u7b7e", "\\u5b89\\u5168"]\n---\nbody'
        assert _fm_of(text)["tags"] == ["书签", "安全"]

    def test_real_backslash_path_survives_roundtrip(self):
        # "C:\\users" 的 \\u 后跟 "sers" 非 4 位十六进制, 不该被当转义解码
        fm = {"id": "x", "local_wiki_ref": "C:\\users"}
        assert _fm_of(serialize_frontmatter(fm))["local_wiki_ref"] == "C:\\users"

    def test_doubly_escaped_stays_literal(self):
        # YAML 语义: "\\" 是字面反斜杠, 其后 u4e66 应保留为普通文本
        assert _fm_of('---\nid: x\ntitle: "A\\\\u4e66B"\n---\nbody')["title"] == "A\\u4e66B"

    def test_serialized_cjk_is_never_escaped(self):
        text = serialize_frontmatter({"id": "x", "tags": ["书签栏", "渗透测试与攻防"]})
        assert "\\u" not in text
        assert "书签栏" in text


class TestQuoting:
    """B 类: 双引号标量必须合法 — 内层 " 与 \\ 都要转义。"""

    def test_quote_escapes_inner_quotes(self):
        raw = '{"initial": 1.0, "current_score": 1.0}'
        quoted = _quote(raw)
        assert quoted.startswith('"') and quoted.endswith('"')
        assert '\\"' in quoted
        assert _unquote(quoted) == raw

    def test_quote_escapes_backslash(self):
        assert _unquote(_quote("a\\b")) == "a\\b"

    def test_retention_shape_is_legal_yaml(self):
        # 生产样本 (llm-wiki-2.0/items/*.md 的 retention 行) 曾写成非法 YAML
        value = '{"initial": 1.0, "last_accessed": "2026-08-23T07:57:38Z"}'
        text = serialize_frontmatter({"id": "x", "retention": value})
        assert text.count('\\"') == value.count('"')  # 内层引号全部转义 → YAML 合法
        assert json.loads(_fm_of(text)["retention"])["initial"] == 1.0

    def test_dict_serializes_to_parsable_json_string(self):
        # 本契约解析器不支持嵌套映射; dict 落 JSON 字符串而不是 str(dict) repr
        text = serialize_frontmatter({"id": "x", "meta": {"a": 1, "b": "中"}})
        parsed = _fm_of(text)["meta"]
        assert isinstance(parsed, str) and "'" not in parsed
        assert json.loads(parsed) == {"a": 1, "b": "中"}


class TestRoundTripStability:
    def test_serialize_parse_serialize_is_idempotent(self):
        fm = {
            "id": "x",
            "title": '他说: "这是 {一个} 测试, 带逗号"',
            "source_url": "https://e.com/a?b=1&c=2",
            "tags": ["书签栏", 'quote"inside', "back\\slash"],
            "retention": '{"initial": 1.0}',
            "mastery": 50,
            "compiled": False,
        }
        first = serialize_frontmatter(fm)
        second = serialize_frontmatter(_fm_of(first))
        assert first == second

    def test_repair_is_idempotent_on_already_fixed_text(self):
        # 已修好的 md 再过一遍契约不应改变值
        fixed = serialize_frontmatter({"id": "x", "tags": ["书签栏"], "topic": None})
        assert _fm_of(fixed)["tags"] == ["书签栏"]
        assert _fm_of(fixed)["topic"] is None


class TestFlowSequenceKeepsListType:
    """回归锁: 回填脚本首版把解码后的数组包上引号 → list 退化成 str,
    而 knowledge_sync.py:171 对非 list 的 tags 静默置 [] (4055 个条目标签会丢)。
    """

    def test_legacy_quoted_array_decodes_as_list(self):
        text = '---\nid: x\ntags: ["\\u5199\\u4f5c", "\\u9605\\u8bfb"]\n---\nbody'
        assert _fm_of(text)["tags"] == ["写作", "阅读"]

    def test_script_keeps_flow_sequence_unquoted(self):
        import sys
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from fix_wiki_frontmatter_escape import _fix_value

        new, category = _fix_value('["\\u5199\\u4f5c", "\\u9605\\u8bfb"]')
        assert new == '["写作", "阅读"]' and category == "escape"
        assert _fix_value(new) == (new, None)  # 幂等

    def test_serialize_keeps_tags_as_block_sequence(self):
        text = serialize_frontmatter({"id": "x", "tags": ["写作", "阅读"]})
        assert text.splitlines()[2] == "tags:"  # 不是被引号包住的 JSON 串
        assert _fm_of(text)["tags"] == ["写作", "阅读"]
