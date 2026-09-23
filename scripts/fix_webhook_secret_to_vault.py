#!/usr/bin/env python3
"""fix_webhook_secret_to_vault.py — webhook.secret 迁移到加密存储 (安全修复)

背景 (2026-09-22 设置重构 P3 Task 15, 设计稿 §5):
  settings kv 明文键 ``webhook.secret`` 迁入 llm_secrets 加密存储 (Fernet,
  主密钥派生)。原 webhook 触发器读点 import 不存在的 ``settings_kv`` 模块,
  异常被吞 → 签名校验生产默认从未生效; 迁移后读点走
  ``SecretsService.find_internal_by_name("webhook.secret")`` (unlock 窗口语义)。

用法:
  python scripts/fix_webhook_secret_to_vault.py              # dry-run (默认), 只预览
  python scripts/fix_webhook_secret_to_vault.py --dry-run    # 同上 (显式)
  python scripts/fix_webhook_secret_to_vault.py --execute    # 真实迁移 (交互输入主密钥)

流程:
  1. 读 settings kv ``webhook.secret`` — 不存在则无需迁移, 退出
  2. (execute) getpass 输入主密钥 → SecretsService.create_secret 写入加密存储
     (repo 层要求 base_url 非空, 用 "internal://webhook" 占位标记)
  3. (execute) 删除 settings kv 明文行 → 打印摘要

安全:
  - --dry-run 默认 True, 不写任何 DB (scripts/AGENTS.md 破坏性脚本纪律)
  - 主密钥经 getpass 输入, 不落日志/不回显; secret 摘要打码
  - 回滚 = 主密钥 reveal 后 re-set settings kv; 不落明文备份文件
  - vault 已有同名条目时跳过 create, 仅清理 kv 残留 (幂等)
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

KV_KEY = "webhook.secret"
PLACEHOLDER_BASE_URL = "internal://webhook"  # repo 层要求非空; webhook.secret 无 base_url 语义


def _masked(value: str) -> str:
    """secret 打码 — 长度不足时全遮。"""
    if len(value) <= 8:
        return "***"
    return value[:4] + "..." + value[-2:]


def _read_kv() -> str | None:
    from backend.repository.settings_repo import SettingsRepository

    value = SettingsRepository().get(KV_KEY)
    if value is None:
        return None
    return str(value)


def _vault_has_entry() -> bool:
    from backend.repository.secrets_repo import SecretRepository

    items, _total = SecretRepository().list()
    return any(i.name == KV_KEY for i in items)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="webhook.secret 迁移到加密存储 (llm_secrets vault)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(默认) 只预览将执行的动作, 不写 DB",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真实执行迁移 (交互输入主密钥); 缺省一律 dry-run",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    # 1. 读旧明文 kv
    secret = _read_kv()
    if secret is None:
        print(f"[OK] settings kv 无 '{KV_KEY}' — 无需迁移。")
        return 0

    already_in_vault = _vault_has_entry()
    print(f"[{'DRY-RUN' if dry_run else 'EXECUTE'}] 目标: settings kv '{KV_KEY}' → llm_secrets vault")
    print(f"  旧 kv 明文值: {_masked(secret)}")
    if already_in_vault:
        print("  vault 已存在 'webhook.secret' 条目 → 跳过 create, 仅清理 kv 残留")
    else:
        print("  将执行: SecretsService.create_secret(name='webhook.secret', model='hmac',")
        print(f"            base_url='{PLACEHOLDER_BASE_URL}', api_key=<kv 明文>)")
    print(f"  将执行: SettingsRepository.delete('{KV_KEY}')")

    if dry_run:
        print("\n[dry-run] 未写任何 DB。加 --execute 真实迁移 (需交互输入主密钥)。")
        return 0

    # 2. 写 vault (已有条目则跳过)
    if not already_in_vault:
        master_key = getpass.getpass("输入主密钥 (master_key, 输入不回显): ")
        from backend.services.secrets_service import SecretsService

        svc = SecretsService()
        if not svc.is_master_key_setup():
            print("[ERROR] 主密钥未初始化 — 先在 /settings 完成主密钥 setup。")
            return 1
        try:
            svc.create_secret(
                name=KV_KEY,
                model="hmac",
                base_url=PLACEHOLDER_BASE_URL,
                api_key=secret,
                master_key=master_key,
            )
        except Exception as e:
            print(f"[ERROR] 写入 vault 失败: {type(e).__name__}: {e}")
            print("        settings kv 旧键未删除 (迁移原子性: create 成功才删 kv)。")
            return 1

    # 3. 删 kv 明文行
    from backend.repository.settings_repo import SettingsRepository

    removed = SettingsRepository().delete(KV_KEY)
    print()
    print("[OK] 迁移完成:")
    print(f"  - vault 条目 'webhook.secret': {'已存在(跳过)' if already_in_vault else '已创建'}")
    print(f"  - settings kv '{KV_KEY}': {'已删除' if removed else '不存在(跳过)'}")
    print("  - 回滚方法: /settings 主密钥 reveal 'webhook.secret' 后 re-set settings kv")
    print("  - 重启后端后 webhook 触发器从 vault 读 secret (需主密钥已 unlock)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
