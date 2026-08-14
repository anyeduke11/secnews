"""Phase 2a CodeGarden 项目扫描服务.

职责
----
- 3 种路径源 (local / git / archive) 归一化为一个本地根目录
- 在该根目录下递归扫描, 通过 marker 文件识别独立项目
- 推断项目元数据 (name / type / tech_stack)
- 不写 cg_projects 表 —— 只返回「检测到」列表, 由调用方决定是否导入

设计原则
--------
- 所有 I/O 通过 asyncio.to_thread 包装 (FastAPI async 兼容)
- 临时目录在 git clone / archive extract 后会保留到导入完成, 由调用方清理
- 检测是只读的, 不会修改用户文件系统
- Phase 1: 仅做「边界识别 + 轻量元数据推断」; 深度架构分析/内容解析留到 Phase 2
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field

from backend.logging_config import logger

# ---------------------------------------------------------------------------
# 项目边界 marker 文件 (相对项目根)
# ---------------------------------------------------------------------------
# 单文件 marker
_MARKER_FILES_SINGLE: dict[str, str] = {
    "package.json": "node",
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java_maven",
    "build.gradle": "java_gradle",
    "build.gradle.kts": "java_kotlin",
    "Gemfile": "ruby",
    "composer.json": "php",
    "mix.exs": "elixir",
    "pubspec.yaml": "dart",
}

# 通配符 marker (检查文件存在即可)
_MARKER_GLOBS: list[tuple[str, str]] = [
    ("*.csproj", "dotnet"),
    ("*.fsproj", "dotnet"),
    ("Package.swift", "swift"),
]


# 递归时跳过的目录
_SKIP_DIRS: set[str] = {
    "node_modules", ".git", ".svn", ".hg",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "venv", ".venv", "env", ".env",
    "dist", "build", "out", "target", "bin", "obj",
    ".next", ".nuxt", ".svelte-kit", ".cache",
    "vendor", "Pods",
    "ios/Pods", "android/build", "DerivedData",
}

# 最大扫描深度 (避免过深扫描)
_MAX_DEPTH: int = 6

# 单次扫描最多返回多少个项目 (防爆)
_MAX_PROJECTS: int = 200


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class DetectedProject:
    """扫描检测到的单个项目."""
    name: str
    absolute_path: str          # 项目的绝对路径
    relative_path: str          # 相对 scan_root 的路径
    marker_file: str            # 触发的 marker (e.g. "package.json")
    language: str               # python / node / go / ...
    inferred_type: str          # web_application / api_service / cli / library / experiment
    description: str = ""       # 从 manifest 抓的简短描述
    tech_stack: list[str] = field(default_factory=list)
    marker_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "absolute_path": self.absolute_path,
            "relative_path": self.relative_path,
            "marker_file": self.marker_file,
            "language": self.language,
            "inferred_type": self.inferred_type,
            "description": self.description,
            "tech_stack": self.tech_stack,
        }


# ---------------------------------------------------------------------------
# 核心: 扫描本地目录
# ---------------------------------------------------------------------------
def _walk_for_projects(scan_root: str) -> list[DetectedProject]:
    """递归扫描 scan_root, 返回所有检测到的项目 (按路径排序, 去重)."""
    if not os.path.isdir(scan_root):
        return []

    detected: dict[str, DetectedProject] = {}  # key = absolute_path, 防止重复标记
    scan_root_abs = os.path.abspath(scan_root)

    def _visit(current: str, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if len(detected) >= _MAX_PROJECTS:
            return

        try:
            entries = list(os.scandir(current))
        except (PermissionError, OSError) as e:
            logger.warning(f"scanner skip {current}: {e}")
            return

        # 先检查当前目录是否就是项目根
        marker = _detect_marker(entries)
        if marker is not None:
            proj = _build_project(scan_root_abs, current, marker)
            if proj is not None and proj.absolute_path not in detected:
                detected[proj.absolute_path] = proj
            return  # 不再下钻 (一个项目内部不再嵌套项目)

        # 当前目录不是项目根, 递归子目录
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in _SKIP_DIRS:
                continue
            if entry.name.startswith("."):
                # 跳过隐藏目录, 但保留 .github (CI 配置常见位置)
                if entry.name == ".github":
                    continue
            _visit(entry.path, depth + 1)

    _visit(scan_root_abs, 0)

    # 按相对路径排序
    return sorted(detected.values(), key=lambda p: p.relative_path)


def _detect_marker(entries: list[os.DirEntry]) -> tuple[str, str] | None:
    """检查一个目录的 entries, 返回第一个匹配的 (marker_filename, language)."""
    entry_names = {e.name: e for e in entries}
    # 单文件 marker 优先
    for filename, lang in _MARKER_FILES_SINGLE.items():
        if filename in entry_names:
            return (filename, lang)
    # glob marker
    for pattern, lang in _MARKER_GLOBS:
        for name in entry_names:
            if _match_glob(name, pattern):
                return (name, lang)
    return None


def _match_glob(name: str, pattern: str) -> bool:
    """简单 glob 匹配 (只支持 * 通配符)."""
    if "*" not in pattern:
        return name == pattern
    parts = pattern.split("*")
    if not name.startswith(parts[0]):
        return False
    if not name.endswith(parts[-1]):
        return False
    middle = name[len(parts[0]):len(name) - len(parts[-1]) if parts[-1] else len(name)]
    return all(p in middle for p in parts[1:-1])


def _build_project(scan_root: str, project_dir: str, marker: tuple[str, str]) -> DetectedProject | None:
    """从项目目录 + marker 构建 DetectedProject."""
    marker_file, language = marker
    project_name = os.path.basename(project_dir.rstrip("/")) or "unnamed"
    relative_path = os.path.relpath(project_dir, scan_root)

    description, tech_stack, inferred_type = _infer_metadata(project_dir, marker_file, language)

    return DetectedProject(
        name=project_name[:80],  # 与 cg_projects.name 长度限制对齐
        absolute_path=project_dir,
        relative_path=relative_path,
        marker_file=marker_file,
        language=language,
        inferred_type=inferred_type,
        description=description,
        tech_stack=tech_stack,
    )


# ---------------------------------------------------------------------------
# 元数据推断 (Phase 1 轻量版)
# ---------------------------------------------------------------------------
def _infer_metadata(project_dir: str, marker_file: str, language: str) -> tuple[str, list[str], str]:
    """从 manifest 文件读取 description / 依赖, 推断 type. 返回 (desc, tech_stack, type)."""
    marker_path = os.path.join(project_dir, marker_file)
    if not os.path.isfile(marker_path):
        return "", [], _default_type_for_language(language)

    try:
        with open(marker_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return "", [], _default_type_for_language(language)

    if marker_file == "package.json":
        return _infer_from_package_json(content)
    if marker_file in ("pyproject.toml", "setup.py", "requirements.txt"):
        return _infer_from_python(marker_file, content, project_dir)
    if marker_file in ("go.mod", "Cargo.toml", "Gemfile", "mix.exs", "pubspec.yaml"):
        return ("", [language], _default_type_for_language(language))
    if marker_file in ("pom.xml", "build.gradle", "build.gradle.kts"):
        return ("", [language, "jvm"], _default_type_for_language(language))

    return "", [language], _default_type_for_language(language)


def _infer_from_package_json(content: str) -> tuple[str, list[str], str]:
    """从 package.json 推断 description / dependencies / type."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return "", [], "library"

    desc = (data.get("description") or "").strip()[:200]
    deps: dict = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})

    tech_stack = sorted({k.split("/")[0] if "/" in k else k for k in deps})[:20]

    # type 推断
    scripts = data.get("scripts") or {}
    has_react = any(k in deps for k in ("react", "vue", "svelte", "@angular/core", "solid-js"))
    has_express = "express" in deps or "fastify" in deps or "koa" in deps
    has_cli = "bin" in data or "commander" in deps or "yargs" in deps

    if has_react and not has_express:
        inferred = "web_application"
    elif has_express or "hapi" in deps:
        inferred = "api_service"
    elif has_cli:
        inferred = "cli"
    else:
        inferred = "library"

    return desc, tech_stack, inferred


def _infer_from_python(marker_file: str, content: str, project_dir: str) -> tuple[str, list[str], str]:
    """从 Python manifest 推断. 轻量: 关键字匹配."""
    lower = content.lower()
    tech_stack = ["python"]

    if "fastapi" in lower or "flask" in lower or "django" in lower or "starlette" in lower:
        inferred = "api_service"
    elif "click" in lower or "typer" in lower or "argparse" in lower:
        inferred = "cli"
    elif "scrapy" in lower or "beautifulsoup" in lower or "selenium" in lower or "playwright" in lower:
        inferred = "crawler"
    elif "jupyter" in lower or "notebook" in lower:
        inferred = "experiment"
    else:
        inferred = "library"

    # 尝试从 pyproject.toml 的 [project] description 提取
    desc = ""
    if marker_file == "pyproject.toml":
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("description"):
                # description = "..." 或 description = '...' 或 description = ..."
                _, _, value = stripped.partition("=")
                desc = value.strip().strip('"\' ')
                if desc:
                    break
    return desc[:200], tech_stack, inferred


def _default_type_for_language(language: str) -> str:
    """无 manifest 时的默认 type 推断."""
    if language in ("node",):
        return "library"
    if language in ("python",):
        return "library"
    if language in ("go", "rust", "ruby", "elixir", "dart"):
        return "cli"
    if language in ("java_maven", "java_gradle", "java_kotlin", "dotnet", "swift"):
        return "library"
    return "library"


# ---------------------------------------------------------------------------
# 二级目录合并: 一个 scan_root 下的所有子项目, 若属于同一二级目录 (即
# scan_root 的直接子目录), 且该二级目录本身不是项目, 则合并为 1 个项目
# ---------------------------------------------------------------------------
def _merge_by_secondary_root(
    projects: list[DetectedProject], scan_root: str
) -> list[DetectedProject]:
    """合并 scan_root 二级目录下的多个子项目为 1 个项目.

    规则
    ----
    - 二级目录 = scan_root 的直接子目录 (一级子目录)
    - 如果二级目录本身就是 1 个项目 (children 中有 absolute_path == 二级目录的项目):
        - 二级目录保留为 1 个项目, 其子项目保持独立
    - 如果二级目录本身不是项目, 但其子树内有 ≥ 1 个子项目:
        - 所有子项目合并为 1 个项目, 根为该二级目录
        - name = 二级目录 basename
        - marker_file = "merged (N sub-projects)"
        - language = 子项目出现最多的 language
        - inferred_type = 第一个子项目的类型
        - tech_stack = 所有子项目 tech_stack 并集 (保序去重)
        - description = 子项目 descriptions 拼接 (去重, 上限 300 字)
    - 直接位于 scan_root 下的项目 (不嵌套) 不参与合并
    """
    if not projects:
        return projects

    scan_root_abs = os.path.abspath(scan_root)

    # 1) 分桶: 按二级目录 (scan_root 的直接子目录)
    buckets: dict[str, list[DetectedProject]] = {}
    for p in projects:
        try:
            rel = os.path.relpath(p.absolute_path, scan_root_abs)
        except ValueError:
            # 不同盘 (Windows), 不合并
            continue
        parts = rel.split(os.sep)
        if len(parts) < 2 or parts[0] in (".", ""):
            # 项目直接位于 scan_root, 不参与合并
            continue
        sec_dir_abs = os.path.join(scan_root_abs, parts[0])
        buckets.setdefault(sec_dir_abs, []).append(p)

    # 2) 检查每个二级目录是否本身就是项目
    secondary_is_project: dict[str, bool] = {}
    for sec_dir, children in buckets.items():
        secondary_is_project[sec_dir] = any(
            os.path.normpath(c.absolute_path) == os.path.normpath(sec_dir) for c in children
        )

    # 3) 合并
    merged: list[DetectedProject] = []
    consumed: set[str] = set()
    for sec_dir, children in buckets.items():
        if secondary_is_project[sec_dir]:
            # 二级目录是项目, 保留自己, 不动子项目
            for c in children:
                if c.absolute_path == sec_dir:
                    merged.append(c)
                    consumed.add(c.absolute_path)
                # 子项目也保留, 但标记在 consumed 集合里防止重复
                # (因为是同一个 bucket, 不会有另一个 sec_dir 把它们收走)
            # 实际上, 这种情况比较少见, 但保留所有 children 即可
            for c in children:
                if c.absolute_path not in consumed:
                    merged.append(c)
                    consumed.add(c.absolute_path)
            continue

        # 二级目录不是项目, 合并子项目
        # 决定合并项目的属性
        languages = [c.language for c in children if c.language]
        most_common_lang = max(set(languages), key=languages.count) if languages else ""

        # tech_stack 并集 (保序去重)
        tech_seen: set[str] = set()
        tech_union: list[str] = []
        for c in children:
            for ts in c.tech_stack:
                if ts and ts not in tech_seen:
                    tech_seen.add(ts)
                    tech_union.append(ts)

        # descriptions 拼接 (去重)
        desc_seen: set[str] = set()
        desc_parts: list[str] = []
        for c in children:
            d = (c.description or "").strip()
            if d and d not in desc_seen:
                desc_seen.add(d)
                desc_parts.append(d)
        merged_desc = " / ".join(desc_parts)[:300]

        # 推断类型: 优先 library (聚合), 否则取第一个
        inferred_type = "library"
        for c in children:
            if c.inferred_type and c.inferred_type != "library":
                inferred_type = c.inferred_type
                break
        if not any(c.inferred_type and c.inferred_type != "library" for c in children):
            inferred_type = children[0].inferred_type if children else "library"

        rel = os.path.relpath(sec_dir, scan_root_abs)
        merged_proj = DetectedProject(
            name=os.path.basename(sec_dir) or "unnamed",
            absolute_path=sec_dir,
            relative_path=rel,
            marker_file=f"merged ({len(children)} sub-projects)",
            language=most_common_lang,
            inferred_type=inferred_type,
            description=merged_desc,
            tech_stack=tech_union,
        )
        merged.append(merged_proj)
        for c in children:
            consumed.add(c.absolute_path)

    # 4) 加入未被消费的 (直接位于 scan_root 下的项目)
    for p in projects:
        if p.absolute_path not in consumed:
            merged.append(p)
            consumed.add(p.absolute_path)

    # 5) 按 relative_path 排序 (与 _walk_for_projects 行为一致)
    merged.sort(key=lambda x: x.relative_path)
    return merged


# ---------------------------------------------------------------------------
# 公开 API: 3 种路径源 → 归一化为 (scan_root, temp_holder)
# ---------------------------------------------------------------------------
@dataclass
class ScanResult:
    """一次扫描的完整结果."""
    scan_root: str              # 归一化后的本地根路径
    source_type: str            # "local" | "git" | "archive"
    source_path: str            # 原始输入 (本地路径 / git URL / 临时解压目录)
    detected: list[DetectedProject] = field(default_factory=list)
    is_temporary: bool = False  # True 表示调用方需要在用完后清理
    temp_id: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "scan_root": self.scan_root,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "is_temporary": self.is_temporary,
            "temp_id": self.temp_id,
            "message": self.message,
            "detected": [p.to_dict() for p in self.detected],
        }


def scan_local_dir(path: str) -> ScanResult:
    """扫描本地目录.

    自动应用二级目录合并: scan_root 的直接子目录下若聚集了多个子项目,
    且该子目录本身不是项目, 则合并为 1 个项目, 避免 monorepo 多子模块
    被拆成 N 个项目.

    Raises:
        FileNotFoundError: 路径不存在
        NotADirectoryError: 路径不是目录
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"路径不存在: {path}")
    if not os.path.isdir(abs_path):
        raise NotADirectoryError(f"不是目录: {path}")

    raw = _walk_for_projects(abs_path)
    detected = _merge_by_secondary_root(raw, abs_path)
    return ScanResult(
        scan_root=abs_path,
        source_type="local",
        source_path=abs_path,
        detected=detected,
        is_temporary=False,
        message=f"扫描完成, 检测到 {len(detected)} 个项目",
    )


def scan_git_url(url: str, github_token: str | None = None, depth: int = 1) -> ScanResult:
    """Clone git 仓库到临时目录, 扫描后返回结果.

    Phase 1: 浅克隆 (depth=1), 适合 monorepo. 不清理临时目录, 调用方负责.

    Args:
        url: git URL (https://github.com/owner/repo[.git])
        github_token: GitHub token (用于私有仓库或提升 rate limit)
        depth: 克隆深度, 默认 1 (浅克隆)

    Returns:
        ScanResult, is_temporary=True

    Raises:
        RuntimeError: git 命令失败
    """
    if not shutil.which("git"):
        raise RuntimeError("系统未安装 git 命令, 无法克隆")

    # 注入 token (私有仓库或加速)
    clone_url = url
    if github_token and "github.com" in url and url.startswith("https://"):
        # https://x-access-token:TOKEN@github.com/owner/repo.git
        clone_url = url.replace("https://", f"https://x-access-token:{github_token}@", 1)

    temp_id = uuid.uuid4().hex[:12]
    target = os.path.join(tempfile.gettempdir(), f"cg-scan-{temp_id}")

    cmd = ["git", "clone", "--depth", str(depth), "--single-branch", clone_url, target]
    logger.info(f"git clone: {url} -> {target}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        _safe_rmtree(target)
        raise RuntimeError(f"git clone 超时 (120s): {url}")

    if result.returncode != 0:
        _safe_rmtree(target)
        raise RuntimeError(f"git clone 失败: {result.stderr.strip()[:500]}")

    detected = _walk_for_projects(target)
    return ScanResult(
        scan_root=target,
        source_type="git",
        source_path=url,
        detected=detected,
        is_temporary=True,
        temp_id=temp_id,
        message=f"克隆完成, 检测到 {len(detected)} 个项目 (临时目录将在导入后清理)",
    )


def scan_archive(archive_path: str) -> ScanResult:
    """解压压缩包到临时目录, 扫描后返回结果.

    支持: .zip, .tar, .tar.gz, .tgz
    Phase 1: 不清理临时目录, 调用方负责.

    Raises:
        FileNotFoundError: 文件不存在
        RuntimeError: 不支持的格式 / 解压失败
    """
    import tarfile
    import zipfile

    abs_path = os.path.abspath(archive_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"文件不存在: {archive_path}")

    temp_id = uuid.uuid4().hex[:12]
    target = os.path.join(tempfile.gettempdir(), f"cg-scan-{temp_id}")
    os.makedirs(target, exist_ok=True)

    lower = abs_path.lower()
    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(abs_path, "r") as zf:
                zf.extractall(target)
        elif lower.endswith((".tar.gz", ".tgz")):
            with tarfile.open(abs_path, "r:gz") as tf:
                tf.extractall(target)
        elif lower.endswith(".tar"):
            with tarfile.open(abs_path, "r:") as tf:
                tf.extractall(target)
        else:
            _safe_rmtree(target)
            raise RuntimeError(f"不支持的压缩格式: {archive_path} (仅支持 .zip / .tar / .tar.gz / .tgz)")
    except (zipfile.BadZipFile, tarfile.TarError) as e:
        _safe_rmtree(target)
        raise RuntimeError(f"解压失败: {e}")

    # 如果压缩包内是单层目录, 自动下钻一层 (常见: repo-root-xxx/...)
    detected_root = target
    entries = [e for e in os.listdir(target) if not e.startswith(".")]
    if len(entries) == 1:
        sub = os.path.join(target, entries[0])
        if os.path.isdir(sub):
            detected_root = sub

    detected = _walk_for_projects(detected_root)
    detected = _merge_by_secondary_root(detected, detected_root)
    return ScanResult(
        scan_root=detected_root,
        source_type="archive",
        source_path=abs_path,
        detected=detected,
        is_temporary=True,
        temp_id=temp_id,
        message=f"解压完成, 检测到 {len(detected)} 个项目 (临时目录将在导入后清理)",
    )


def cleanup_temp(temp_id: str) -> bool:
    """清理临时扫描目录. 返回是否成功."""
    target = os.path.join(tempfile.gettempdir(), f"cg-scan-{temp_id}")
    return _safe_rmtree(target)


def _safe_rmtree(path: str) -> bool:
    """安全删除目录 (忽略不存在的错误)."""
    if not os.path.exists(path):
        return False
    try:
        shutil.rmtree(path, ignore_errors=True)
        return True
    except Exception as e:
        logger.warning(f"rmtree failed for {path}: {e}")
        return False
