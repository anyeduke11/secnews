"""SQL migration files, applied in lexicographic order.

Naming convention: NNN_short_name.sql  (e.g. 001_init.sql)
The numeric prefix is also used to compute the integer schema version
returned by apply_migrations().

``__all__`` 显式为空 — 这是 SQL 文件目录, 无 Python 模块符号。
"""
__all__: list[str] = []