"""Phase 2a CodeGarden 项目扫描服务单测.

覆盖:
- 本地目录扫描 (单层 / 嵌套 / 跳过的目录 / 深度限制)
- marker 文件识别 (Python / Node / Go 等)
- 元数据推断 (package.json / pyproject.toml)
- archive 解压扫描 (.zip)
- 临时目录清理
- 错误处理 (路径不存在 / 不支持的格式)
"""
from __future__ import annotations

import os
import tarfile
import tempfile
import textwrap
import zipfile
from pathlib import Path

import pytest

from backend.services.codegarden_scanner_service import (
    _detect_marker,
    _infer_from_package_json,
    _infer_from_python,
    _walk_for_projects,
    cleanup_temp,
    scan_archive,
    scan_local_dir,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_projects_dir(tmp_path: Path) -> Path:
    """构造一个典型多项目工作区, 包含 Python / Node / Go 各一, 嵌套 + 跳过目录."""
    root = tmp_path / "workspace"
    root.mkdir()

    # 1. Python API 服务 (顶层)
    py_api = root / "py-api"
    py_api.mkdir()
    (py_api / "pyproject.toml").write_text(textwrap.dedent("""

import pytest

pytestmark = pytest.mark.integration

        [project]
        name = "py-api"
        description = "FastAPI example service"
        dependencies = ["fastapi", "uvicorn", "pydantic"]
    """).strip())

    # 2. Node React app (顶层)
    node_app = root / "node-app"
    node_app.mkdir()
    (node_app / "package.json").write_text(textwrap.dedent("""
        {
          "name": "node-app",
          "description": "React + Vite SPA",
          "dependencies": { "react": "^18", "react-dom": "^18" },
          "devDependencies": { "vite": "^5" }
        }
    """).strip())

    # 3. Go CLI (顶层)
    go_cli = root / "go-cli"
    go_cli.mkdir()
    (go_cli / "go.mod").write_text("module example.com/go-cli\n\ngo 1.22\n")

    # 4. Node Express API (嵌套在 services/ 子目录)
    services = root / "services" / "node-express"
    services.mkdir(parents=True)
    (services / "package.json").write_text(textwrap.dedent("""
        {
          "name": "node-express",
          "dependencies": { "express": "^4" },
          "scripts": { "start": "node index.js" }
        }
    """).strip())

    # 5. 应被跳过的目录
    (root / "node_modules").mkdir()
    (root / "node_modules" / "some-pkg").mkdir()
    (root / "node_modules" / "some-pkg" / "package.json").write_text('{"name":"should-skip"}')

    (root / ".venv").mkdir()
    (root / ".venv" / "pyproject.toml").write_text("[project]\nname = 'venv'\n")

    (root / "build").mkdir()
    (root / "build" / "package.json").write_text('{"name":"build-output"}')

    # 6. 隐藏的非项目目录 (.github) — 跳过
    (root / ".github").mkdir()
    (root / ".github" / "workflows").mkdir()

    # 7. 无 marker 的普通目录 (应被忽略)
    docs = root / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("# docs")

    return root


# ---------------------------------------------------------------------------
# _walk_for_projects: 核心扫描逻辑
# ---------------------------------------------------------------------------
class TestWalkForProjects:
    def test_finds_all_top_level_projects(self, fake_projects_dir: Path) -> None:
        projects = _walk_for_projects(str(fake_projects_dir))
        names = {p.name for p in projects}
        # 顶层 3 个 + 嵌套 1 个 = 4
        assert names == {"py-api", "node-app", "go-cli", "node-express"}

    def test_skips_node_modules_venv_build(self, fake_projects_dir: Path) -> None:
        projects = _walk_for_projects(str(fake_projects_dir))
        abs_paths = {p.absolute_path for p in projects}
        # 检查每个 path 的 path components, 而非 substring — 避免误匹配 (test 目录名包含 "node_modules")
        def has_path_component(p: str, component: str) -> bool:
            return component in p.split(os.sep)

        assert not any(has_path_component(p, "node_modules") for p in abs_paths)
        assert not any(has_path_component(p, ".venv") for p in abs_paths)
        assert not any(has_path_component(p, "build") for p in abs_paths)

    def test_no_nesting_inside_project(self, fake_projects_dir: Path) -> None:
        """如果父目录已是项目根, 不应再下钻找子项目."""
        # 在 py-api 内放一个 package.json (应该被忽略, 因为 py-api 已被识别)
        (fake_projects_dir / "py-api" / "frontend" / "package.json").parent.mkdir(parents=True)
        (fake_projects_dir / "py-api" / "frontend" / "package.json").write_text('{"name":"frontend"}')

        projects = _walk_for_projects(str(fake_projects_dir))
        names = {p.name for p in projects}
        # 不应出现 "frontend"
        assert "frontend" not in names
        # py-api 仍存在
        assert "py-api" in names

    def test_returns_empty_for_no_projects(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        (empty / "README.md").write_text("nothing here")
        assert _walk_for_projects(str(empty)) == []

    def test_returns_empty_for_nonexistent(self, tmp_path: Path) -> None:
        # 路径不存在时, _walk_for_projects 返回空 list (scan_local_dir 会先 raise)
        result = _walk_for_projects(str(tmp_path / "missing"))
        assert result == []

    def test_relative_path_is_relative_to_scan_root(self, fake_projects_dir: Path) -> None:
        projects = _walk_for_projects(str(fake_projects_dir))
        rel = {p.relative_path for p in projects}
        # 嵌套项目应保留相对路径
        assert any("services/node-express" in r for r in rel)

    def test_sorted_by_relative_path(self, fake_projects_dir: Path) -> None:
        projects = _walk_for_projects(str(fake_projects_dir))
        paths = [p.relative_path for p in projects]
        assert paths == sorted(paths)

    def test_max_depth_limit(self, tmp_path: Path) -> None:
        """嵌套深度超过 _MAX_DEPTH 时应停止下钻."""
        from backend.services.codegarden_scanner_service import _MAX_DEPTH
        # 构造一个深 10 层的目录, 每层都不放 marker
        deep = tmp_path / "deep"
        deep.mkdir()
        current = deep
        for i in range(_MAX_DEPTH + 5):
            current = current / f"level{i}"
            current.mkdir()
        # 在最深处放一个 package.json
        (current / "package.json").write_text('{"name":"deep-proj"}')

        projects = _walk_for_projects(str(deep))
        # 因为太深, 应找不到
        assert projects == []


# ---------------------------------------------------------------------------
# _detect_marker
# ---------------------------------------------------------------------------
class TestDetectMarker:
    def test_finds_package_json(self) -> None:
        entries = _mk_entries(["package.json", "index.js", "README.md"])
        marker = _detect_marker(entries)
        assert marker == ("package.json", "node")

    def test_finds_pyproject(self) -> None:
        entries = _mk_entries(["pyproject.toml", "src"])
        marker = _detect_marker(entries)
        assert marker == ("pyproject.toml", "python")

    def test_finds_go_mod(self) -> None:
        entries = _mk_entries(["go.mod", "main.go"])
        marker = _detect_marker(entries)
        assert marker == ("go.mod", "go")

    def test_no_marker_returns_none(self) -> None:
        entries = _mk_entries(["README.md", "src", "docs"])
        assert _detect_marker(entries) is None

    def test_csproj_glob(self) -> None:
        entries = _mk_entries(["MyApp.csproj", "Program.cs"])
        marker = _detect_marker(entries)
        assert marker is not None
        assert marker[1] == "dotnet"

    def test_priority_single_file_over_glob(self) -> None:
        """同时有 package.json 和 *.csproj 时, 单文件 marker 优先 (package.json)."""
        entries = _mk_entries(["package.json", "Foo.csproj"])
        marker = _detect_marker(entries)
        assert marker == ("package.json", "node")


def _mk_entries(names: list[str]):
    """构造假 os.DirEntry-like 对象, 只保留 .name 属性."""
    from unittest.mock import MagicMock
    out = []
    for n in names:
        e = MagicMock()
        e.name = n
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# _infer_from_package_json
# ---------------------------------------------------------------------------
class TestInferFromPackageJson:
    def test_web_application_with_react(self) -> None:
        content = '{"dependencies": {"react": "^18"}}'
        _desc, tech, ptype = _infer_from_package_json(content)
        assert ptype == "web_application"
        assert "react" in tech

    def test_api_service_with_express(self) -> None:
        content = '{"dependencies": {"express": "^4"}}'
        _, _, ptype = _infer_from_package_json(content)
        assert ptype == "api_service"

    def test_cli_with_commander(self) -> None:
        content = '{"dependencies": {"commander": "^11"}, "bin": {"x": "cli.js"}}'
        _, _, ptype = _infer_from_package_json(content)
        assert ptype == "cli"

    def test_library_default(self) -> None:
        content = '{"dependencies": {"lodash": "^4"}}'
        _, _, ptype = _infer_from_package_json(content)
        assert ptype == "library"

    def test_invalid_json_returns_library(self) -> None:
        desc, _tech, ptype = _infer_from_package_json("not json {{{")
        assert ptype == "library"
        assert desc == ""

    def test_description_truncated_to_200(self) -> None:
        long_desc = "x" * 500
        content = f'{{"description": "{long_desc}"}}'
        desc, _, _ = _infer_from_package_json(content)
        assert len(desc) == 200

    def test_tech_stack_dedup_and_scoped(self) -> None:
        """scoped 包 (e.g. @org/pkg) 只取 scope 前缀; 同名合并."""
        content = '{"dependencies": {"@org/pkg": "1", "@org/other": "2", "react": "18"}}'
        _, tech, _ = _infer_from_package_json(content)
        # @org/pkg 和 @org/other 应被合并为 @org
        assert "@org" in tech
        assert "react" in tech


# ---------------------------------------------------------------------------
# _infer_from_python
# ---------------------------------------------------------------------------
class TestInferFromPython:
    def test_fastapi_api_service(self, tmp_path: Path) -> None:
        p = tmp_path / "fake"
        p.mkdir()
        (p / "main.py").write_text("from fastapi import FastAPI")
        content = (p / "main.py").read_text()
        _, _, ptype = _infer_from_python("pyproject.toml", content, str(p))
        assert ptype == "api_service"

    def test_click_cli(self) -> None:
        content = 'import click\n\n@click.command()\ndef main(): pass'
        _, _, ptype = _infer_from_python("pyproject.toml", content, "/tmp")
        assert ptype == "cli"

    def test_scrapy_crawler(self) -> None:
        content = "import scrapy"
        _, _, ptype = _infer_from_python("pyproject.toml", content, "/tmp")
        assert ptype == "crawler"

    def test_jupyter_experiment(self) -> None:
        content = "jupyter notebook"
        _, _, ptype = _infer_from_python("requirements.txt", content, "/tmp")
        assert ptype == "experiment"

    def test_pyproject_description_extracted(self) -> None:
        content = textwrap.dedent("""
            [project]
            name = "demo"
            description = "A demo project"
        """).strip()
        desc, _, _ = _infer_from_python("pyproject.toml", content, "/tmp")
        assert desc == "A demo project"


# ---------------------------------------------------------------------------
# scan_local_dir: 顶层封装
# ---------------------------------------------------------------------------
class TestScanLocalDir:
    def test_basic_scan(self, fake_projects_dir: Path) -> None:
        result = scan_local_dir(str(fake_projects_dir))
        assert result.source_type == "local"
        assert result.scan_root == str(fake_projects_dir.resolve())
        assert not result.is_temporary
        assert result.temp_id is None
        assert len(result.detected) == 4
        assert "检测到 4 个项目" in result.message

    def test_to_dict_serializable(self, fake_projects_dir: Path) -> None:
        result = scan_local_dir(str(fake_projects_dir))
        d = result.to_dict()
        assert d["source_type"] == "local"
        assert isinstance(d["detected"], list)
        assert "absolute_path" in d["detected"][0]
        assert "inferred_type" in d["detected"][0]

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            scan_local_dir(str(tmp_path / "nope"))

    def test_file_path_raises_not_a_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            scan_local_dir(str(f))

    def test_no_projects_returns_empty_list(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = scan_local_dir(str(empty))
        assert result.detected == []
        assert "检测到 0 个项目" in result.message


# ---------------------------------------------------------------------------
# scan_archive: 压缩包解压
# ---------------------------------------------------------------------------
def _make_zip_with_projects(archive_path: Path, projects: dict[str, str]) -> None:
    """projects: { archive_root_path: file_content }"""
    with zipfile.ZipFile(archive_path, "w") as zf:
        for path, content in projects.items():
            zf.writestr(path, content)


def _make_tar_gz_with_projects(archive_path: Path, projects: dict[str, str]) -> None:
    with tarfile.open(archive_path, "w:gz") as tf:
        for path, content in projects.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tf.addfile(info, __import__("io").BytesIO(data))


class TestScanArchive:
    def test_zip_with_projects(self, tmp_path: Path) -> None:
        archive = tmp_path / "src.zip"
        _make_zip_with_projects(archive, {
            "proj-a/package.json": '{"name": "proj-a", "dependencies": {"react": "^18"}}',
            "proj-b/pyproject.toml": '[project]\nname = "proj-b"',
        })

        result = scan_archive(str(archive))
        assert result.source_type == "archive"
        assert result.is_temporary
        assert result.temp_id is not None
        names = {p.name for p in result.detected}
        assert names == {"proj-a", "proj-b"}

    def test_zip_with_single_root_dir_drilled_down(self, tmp_path: Path) -> None:
        """压缩包内单层目录应自动下钻一层."""
        archive = tmp_path / "single.zip"
        _make_zip_with_projects(archive, {
            "repo-root/package.json": '{"name": "x", "dependencies": {"react": "^18"}}',
        })

        result = scan_archive(str(archive))
        assert len(result.detected) == 1
        # 扫描到的项目名 = 目录名 (basename), 不是 package.json 里的 name 字段
        assert result.detected[0].name == "repo-root"
        assert result.detected[0].relative_path == "."  # 钻到这层后, 项目本身成了根

    def test_targz_supported(self, tmp_path: Path) -> None:
        archive = tmp_path / "src.tar.gz"
        _make_tar_gz_with_projects(archive, {
            "pkg-c/package.json": '{"name":"pkg-c","dependencies":{"express":"^4"}}',
        })

        result = scan_archive(str(archive))
        assert len(result.detected) == 1
        assert result.detected[0].language == "node"

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        archive = tmp_path / "src.rar"
        archive.write_bytes(b"fake rar")
        with pytest.raises(RuntimeError, match="不支持的压缩格式"):
            scan_archive(str(archive))

    def test_nonexistent_archive_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            scan_archive(str(tmp_path / "missing.zip"))

    def test_cleanup_temp(self, tmp_path: Path) -> None:
        archive = tmp_path / "src.zip"
        _make_zip_with_projects(archive, {
            "p/package.json": '{"name":"p"}',
        })
        result = scan_archive(str(archive))
        assert result.temp_id is not None
        # 临时目录应存在
        from backend.services.codegarden_scanner_service import cleanup_temp
        target = os.path.join(tempfile.gettempdir(), f"cg-scan-{result.temp_id}")
        assert os.path.exists(target)
        # 清理
        assert cleanup_temp(result.temp_id) is True
        assert not os.path.exists(target)

    def test_cleanup_nonexistent_temp(self) -> None:
        # 不存在的 temp_id 应返回 False (no-op)
        assert cleanup_temp("never-existed-12345") is False

    def test_corrupted_zip_raises(self, tmp_path: Path) -> None:
        archive = tmp_path / "broken.zip"
        archive.write_bytes(b"not a zip file at all")
        with pytest.raises(RuntimeError, match="解压失败"):
            scan_archive(str(archive))


# ---------------------------------------------------------------------------
# 集成: 完整 batch 流程
# ---------------------------------------------------------------------------
class TestEndToEndBatch:
    """模拟前端 batch 流程: scan → modify overrides → batch import 风格的数据形态."""

    def test_scan_then_build_batch_payload(self, fake_projects_dir: Path) -> None:
        """扫描结果可直接转换为 batch-import 请求格式."""
        result = scan_local_dir(str(fake_projects_dir))
        assert result.is_temporary is False
        assert len(result.detected) == 4

        # 模拟前端选 2 个, 覆盖 name + type
        selected = [result.detected[0], result.detected[1]]
        payload = []
        for i, d in enumerate(selected):
            payload.append({
                "name": d.name,
                "absolute_path": d.absolute_path,
                "marker_file": d.marker_file,
                "language": d.language,
                "inferred_type": d.inferred_type,
                "tech_stack": d.tech_stack,
                "override_type": "api_service" if i == 0 else None,
            })

        assert len(payload) == 2
        assert payload[0]["override_type"] == "api_service"
        assert payload[1]["override_type"] is None

    def test_archive_then_cleanup_idempotent(self, tmp_path: Path) -> None:
        """多次调用 cleanup 同一个 temp_id 不会抛错."""
        archive = tmp_path / "src.zip"
        _make_zip_with_projects(archive, {
            "a/package.json": '{"name":"a"}',
            "b/pyproject.toml": '[project]\nname = "b"',
        })
        result = scan_archive(str(archive))
        tid = result.temp_id
        assert tid is not None
        assert cleanup_temp(tid) is True
        # 第二次清理 → False (no-op, 不抛错)
        assert cleanup_temp(tid) is False


# ---------------------------------------------------------------------------
# 二级目录合并 (Phase 1 增强): scan_root 直接子目录下的多个子项目
# 自动合并为 1 个父级项目
# ---------------------------------------------------------------------------
class TestMergeBySecondaryRoot:
    """_merge_by_secondary_root 函数 + 集成到 scan_local_dir / scan_archive."""

    @pytest.fixture
    def merged_fixture(self, tmp_path: Path) -> Path:
        """构造类似 ThreatMapper 的多子模块目录.

        顶级 layout (3 个一级子目录, 其中 1 个被合并):
            <tmp>/a-top/  (顶层独立项目)
            <tmp>/b-merged/  (无自身 marker, 含 3 个子项目 → 应合并)
                b-merged/pkg1/package.json
                b-merged/pkg2/go.mod
                b-merged/pkg3/pyproject.toml
            <tmp>/c-also-merged/  (无自身 marker, 含 2 个子项目)
                c-also-merged/inner1/package.json
                c-also-merged/inner2/package.json
            <tmp>/d-self-project/  (自身有 marker, 含 1 个子项目 → 不合并)
                d-self-project/pyproject.toml
                d-self-project/services/svc/package.json
        """
        root = tmp_path / "root"
        root.mkdir()

        # 1) a-top: 顶层独立项目
        a = root / "a-top"
        a.mkdir()
        (a / "package.json").write_text('{"name":"a-top","dependencies":{"react":"^18"}}')

        # 2) b-merged: 3 个子项目, b-merged 本身无 marker → 合并
        b = root / "b-merged"
        b.mkdir()
        (b / "pkg1").mkdir()
        (b / "pkg1" / "package.json").write_text('{"name":"pkg1","dependencies":{"express":"^4"}}')
        (b / "pkg2").mkdir()
        (b / "pkg2" / "go.mod").write_text("module example.com/pkg2\n")
        (b / "pkg3").mkdir()
        (b / "pkg3" / "pyproject.toml").write_text('[project]\nname="pkg3"')

        # 3) c-also-merged: 2 个子项目, c-also-merged 本身无 marker → 合并
        c = root / "c-also-merged"
        c.mkdir()
        (c / "inner1").mkdir()
        (c / "inner1" / "package.json").write_text('{"name":"inner1","dependencies":{"react":"^18"}}')
        (c / "inner2").mkdir()
        (c / "inner2" / "package.json").write_text('{"name":"inner2","dependencies":{"vue":"^3"}}')

        # 4) d-self-project: 自身有 marker, 含 1 个子项目 → 自身独立, 子项目独立
        d = root / "d-self-project"
        d.mkdir()
        (d / "pyproject.toml").write_text('[project]\nname="d-self-project"')
        (d / "services" / "svc").mkdir(parents=True)
        (d / "services" / "svc" / "package.json").write_text('{"name":"svc","dependencies":{"express":"^4"}}')

        return root

    def test_secondary_dirs_merged_into_one(self, merged_fixture: Path) -> None:
        """b-merged 的 3 个子项目应合并为 1 个 b-merged 项目."""
        result = scan_local_dir(str(merged_fixture))
        names = {p.name for p in result.detected}
        # b-merged 出现 1 次 (合并), 不应出现 pkg1/pkg2/pkg3
        assert "b-merged" in names
        assert "pkg1" not in names
        assert "pkg2" not in names
        assert "pkg3" not in names

    def test_secondary_dir_itself_is_a_project_kept(self, merged_fixture: Path) -> None:
        """d-self-project 自身是项目 → 保留; 其子项目因 _walk_for_projects 的
        "项目内不再下钻" 规则被跳过 (这是设计: 项目是叶子节点)."""
        result = scan_local_dir(str(merged_fixture))
        names = {p.name for p in result.detected}
        assert "d-self-project" in names
        # d-self-project 自己有 marker, 内部 svc 不会被识别 (无 nested marker 设计)
        # 这是预期行为, 不需要修复

    def test_top_level_project_untouched(self, merged_fixture: Path) -> None:
        """直接位于 scan_root 下的项目不参与合并."""
        result = scan_local_dir(str(merged_fixture))
        a_top = [p for p in result.detected if p.name == "a-top"]
        assert len(a_top) == 1
        assert a_top[0].marker_file == "package.json"

    def test_merged_marker_file_indicates_merge(self, merged_fixture: Path) -> None:
        """合并项目的 marker_file 应包含 'merged (N sub-projects)'."""
        result = scan_local_dir(str(merged_fixture))
        b = [p for p in result.detected if p.name == "b-merged"]
        assert len(b) == 1
        assert "merged" in b[0].marker_file
        assert "3 sub-projects" in b[0].marker_file

    def test_merged_language_is_most_common(self, merged_fixture: Path) -> None:
        """合并项目的 language = 子项目出现最多的 (本 fixture 各 1 个, 任意其一)."""
        result = scan_local_dir(str(merged_fixture))
        b = next(p for p in result.detected if p.name == "b-merged")
        # pkg1=node, pkg2=go, pkg3=python → 各 1 个, set 顺序非确定, 但必须三者之一
        assert b.language in ("node", "go", "python")

    def test_merged_tech_stack_is_union(self, merged_fixture: Path) -> None:
        """tech_stack 应是子项目 tech_stack 的并集."""
        result = scan_local_dir(str(merged_fixture))
        b = next(p for p in result.detected if p.name == "b-merged")
        # pkg1 tech=express, pkg2 tech=[], pkg3 tech=[]
        assert "express" in b.tech_stack
        assert len(b.tech_stack) == len(set(b.tech_stack))  # 去重

    def test_total_count_reduction(self, merged_fixture: Path) -> None:
        """无合并: a-top + 3+2+(d+svc=1) = 7 个, 合并后 b/c 各变 1, d 内 svc 不计入 → 4."""
        result = scan_local_dir(str(merged_fixture))
        # a-top(1) + b-merged(1, 合并 3) + c-also-merged(1, 合并 2) + d-self-project(1) = 4
        assert len(result.detected) == 4
        # 验证合并后子项目消失
        all_names = {p.name for p in result.detected}
        assert "pkg1" not in all_names
        assert "pkg2" not in all_names
        assert "pkg3" not in all_names
        assert "inner1" not in all_names
        assert "inner2" not in all_names

    def test_empty_projects_returns_empty(self) -> None:
        """空列表直接返回."""
        from backend.services.codegarden_scanner_service import _merge_by_secondary_root
        assert _merge_by_secondary_root([], "/some/root") == []

    def test_archive_also_merges(self, tmp_path: Path) -> None:
        """压缩包扫描也应应用合并."""
        archive = tmp_path / "monorepo.zip"
        _make_zip_with_projects(archive, {
            "ThreatMapper/deepfence_bootstrapper/go.mod": "module example.com/bootstrapper\n",
            "ThreatMapper/deepfence_ctl/go.mod": "module example.com/ctl\n",
            "ThreatMapper/deepfence_server/go.mod": "module example.com/server\n",
            "docs/README.md": "# readme",
            "tools/cli.py": "print('x')",  # 无 marker
        })
        result = scan_archive(str(archive))
        names = {p.name for p in result.detected}
        # ThreatMapper 合并为 1 个
        assert "ThreatMapper" in names
        assert "deepfence_bootstrapper" not in names
        assert "deepfence_ctl" not in names
        assert "deepfence_server" not in names
        # merged 标记
        threat = next(p for p in result.detected if p.name == "ThreatMapper")
        assert "3 sub-projects" in threat.marker_file
        assert threat.language == "go"

    def test_real_threatmapper_scenario(self) -> None:
        """模拟用户截图: /Users/duke/Documents 下 ThreatMapper 含 6 个 Go 子项目 + 1 个 Node 前端.
        期望: ThreatMapper 合并为 1 个项目 (7 子项目 → 1 合并项目)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Documents"
            root.mkdir()
            tm = root / "ThreatMapper"
            tm.mkdir()
            for name in ["deepfence_bootstrapper", "deepfence_ctl", "deepfence_installer",
                         "deepfence_server", "deepfence_utils", "deepfence_worker"]:
                d = tm / name
                d.mkdir()
                (d / "go.mod").write_text(f"module example.com/{name}\n")
            frontend = tm / "deepfence_frontend"
            frontend.mkdir()
            (frontend / "package.json").write_text('{"name":"deepfence_frontend","dependencies":{"react":"^18"}}')

            result = scan_local_dir(str(root))
            # ThreatMapper 合并 → 1 个项目
            threatmap = [p for p in result.detected if p.name == "ThreatMapper"]
            assert len(threatmap) == 1, f"应合并为 1 个, 实际 {len(threatmap)}"
            # marker_file 应是 "merged (7 sub-projects)"
            assert "7 sub-projects" in threatmap[0].marker_file
            # 子项目全消失
            for name in ["deepfence_bootstrapper", "deepfence_ctl", "deepfence_installer",
                         "deepfence_server", "deepfence_utils", "deepfence_worker", "deepfence_frontend"]:
                assert name not in {p.name for p in result.detected}, f"{name} 应被合并掉"
