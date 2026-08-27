"""One-off: migrate quality_check_logs_archive from hotspot.db to hotspot-warm.db.

This table is retention.json-marked COLD but physically lives in HOT.
Moving it to WARM immediately reduces HOT volume.
"""
import sqlite3
from pathlib import Path

REPO_ROOT = Path('/Users/duke/Documents/hotspot')
HOT_DB = REPO_ROOT / 'backend' / 'hotspot.db'
WARM_DB = REPO_ROOT / 'backend' / 'hotspot-warm.db'
TABLE = 'quality_check_logs_archive'


def main() -> int:
    print(f'HOT before: {HOT_DB.stat().st_size:,} B')
    print(f'WARM before: {WARM_DB.stat().st_size:,} B')

    hot = sqlite3.connect(str(HOT_DB))
    warm = sqlite3.connect(str(WARM_DB))

    try:
        count = hot.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]
        print(f'Rows in {TABLE}: {count:,}')

        if count == 0:
            print('Table empty, nothing to migrate')
            return 0

        create_sql = hot.execute(
            f'SELECT sql FROM sqlite_master WHERE type="table" AND name="{TABLE}"'
        ).fetchone()
        if create_sql and create_sql[0]:
            warm.execute(create_sql[0])
            print(f'Created table in WARM')

        BATCH = 5000
        copied = 0
        cols = [c[1] for c in hot.execute(f'PRAGMA table_info("{TABLE}")').fetchall()]
        cols_csv = ','.join(f'"{c}"' for c in cols)
        placeholders = ','.join('?' for _ in cols)

        hot.execute('BEGIN')
        warm.execute('BEGIN')
        try:
            while True:
                rows = hot.execute(
                    f'SELECT {cols_csv} FROM "{TABLE}" LIMIT {BATCH} OFFSET {copied}'
                ).fetchall()
                if not rows:
                    break
                warm.executemany(
                    f'INSERT INTO {TABLE} ({cols_csv}) VALUES ({placeholders})', rows
                )
                copied += len(rows)
                print(f'  copied {copied:,}/{count:,}')
        finally:
            hot.execute('ROLLBACK')
            warm.execute('COMMIT')

        print(f'Copied {copied:,} rows to WARM')

        hot.execute('BEGIN')
        hot.execute(f'DROP TABLE {TABLE}')
        hot.execute('COMMIT')
        print(f'Dropped {TABLE} from HOT')

        hot.execute('VACUUM')
        print('VACUUMed HOT')

    finally:
        hot.close()
        warm.close()

    hot_size = HOT_DB.stat().st_size
    warm_size = WARM_DB.stat().st_size
    print(f'\nAfter:')
    print(f'  HOT: {hot_size:,} B ({hot_size / 1024 / 1024:.1f} MB)')
    print(f'  WARM: {warm_size:,} B ({warm_size / 1024 / 1024:.1f} MB)')
    print(f'  Saved: {(HOT_DB.stat().st_size - hot_size):,} B')

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
