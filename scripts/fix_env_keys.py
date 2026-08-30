#!/usr/bin/env python3
"""fix_env_keys.py — 轮换泄露的 API 密钥到本地 .env（安全助手）

背景 (2026-08-30 安全审计):
  archives/dsh-secs-news-2026-08-27.tar.zst 曾推送到 GitHub, 内含 3 个明文 API key:
    DEEPSEEK_API_KEY / MODELSCOPE_API_KEY / SENSENOVA_API_KEY
  已用 filter-repo 清除远程历史, 但这些 key 视为已泄露 — 必须在服务商后台
  撤销旧 key 并生成新 key, 然后用本脚本写入本地 .env。

用法:
  python scripts/fix_env_keys.py --dry-run                          # 预览变更
  python scripts/fix_env_keys.py --deepseek sk-xxx --modelscope ms-xxx \
      --sensenova sk-xxx                                            # 更新指定 key
  python scripts/fix_env_keys.py --rotate-all                       # 交互式逐个输入

特性:
  - 自动备份 .env 到 .env.bak-<timestamp>
  - 只更新传入的变量, 不动的保留原值
  - 不提交任何值到 git (本脚本只写 gitignored 的 .env)
  - --dry-run 只打印将做什么, 不写文件
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import sys

# 允许轮换的变量白名单 (与 config/llm.yaml api_key_env 对齐)
ROTATABLE_KEYS = {
    "DEEPSEEK_API_KEY",
    "MODELSCOPE_API_KEY",
    "SENSENOVA_API_KEY",
}

DEFAULT_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _backup(env_path: str) -> str:
    """备份 .env, 返回备份路径。"""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{env_path}.bak-{ts}"
    shutil.copy2(env_path, backup)
    return backup


def _load_env(env_path: str) -> list[str]:
    if not os.path.exists(env_path):
        raise FileNotFoundError(f"{env_path} 不存在 — 先创建 .env (参考 .env.example)")
    with open(env_path, "r", encoding="utf-8") as f:
        return f.readlines()


def _upsert_env(lines: list[str], key: str, value: str) -> list[str]:
    """在 lines 中更新或追加 KEY=value。返回新行列表。"""
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        # 追加到文件末尾 (若末尾无换行先补)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{key}={value}\n")
    return new_lines


def main() -> int:
    parser = argparse.ArgumentParser(description="轮换泄露的 API 密钥到本地 .env")
    parser.add_argument("--env", default=DEFAULT_ENV_PATH, help=".env 路径 (默认仓库根)")
    parser.add_argument("--dry-run", action="store_true", help="只打印将做什么, 不写文件")
    parser.add_argument("--rotate-all", action="store_true", help="交互式逐个输入 3 个 key")
    parser.add_argument("--deepseek", metavar="KEY", help="新的 DEEPSEEK_API_KEY")
    parser.add_argument("--modelscope", metavar="KEY", help="新的 MODELSCOPE_API_KEY")
    parser.add_argument("--sensenova", metavar="KEY", help="新的 SENSENOVA_API_KEY")
    args = parser.parse_args()

    # 收集要更新的变量
    updates: dict[str, str] = {}
    if args.rotate_all:
        for key in sorted(ROTATABLE_KEYS):
            val = input(f"  输入新的 {key} (留空跳过): ").strip()
            if val:
                updates[key] = val
    else:
        for flag, key in (("deepseek", "DEEPSEEK_API_KEY"),
                          ("modelscope", "MODELSCOPE_API_KEY"),
                          ("sensenova", "SENSENOVA_API_KEY")):
            val = getattr(args, flag)
            if val:
                updates[key] = val

    if not updates:
        print("未提供任何 key。用法见 --help。")
        return 1

    # 读取现有 .env
    try:
        lines = _load_env(args.env)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 1

    # 预览
    print(f"[{'DRY-RUN' if args.dry_run else 'UPDATE'}] 目标: {args.env}")
    print(f"  现有行数: {len(lines)}")
    for key, val in updates.items():
        masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "***"
        print(f"  {'↻' if any(l.startswith(key + '=') for l in lines) else '+'} {key} = {masked}")
    if any(l.startswith(key + "=") for l in lines):
        print("  (已存在 → 替换)")
    else:
        print("  (不存在 → 追加)")

    if args.dry_run:
        print("\n[dry-run] 未写入任何文件。加 --dry-run 去掉后执行真实更新。")
        return 0

    # 备份 + 写入
    backup = _backup(args.env)
    new_lines = lines
    for key, val in updates.items():
        new_lines = _upsert_env(new_lines, key, val)
    with open(args.env, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\n[OK] .env 已更新, 备份: {backup}")
    print("提醒: 旧 key 必须在服务商后台已撤销; 重启后端后 ai_hub 将读取新 key。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
