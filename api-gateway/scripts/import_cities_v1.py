"""
scripts/import_cities_v1.py — Import ua_cities from Aetherion v1 Postgres DB.

Runs on the HOST machine (not inside Docker container) so it can reach the local v1 DB.

Usage (from monorepo root):
    python api-gateway/scripts/import_cities_v1.py
    python api-gateway/scripts/import_cities_v1.py --dry-run
    python api-gateway/scripts/import_cities_v1.py \\
        --source-url "postgresql://user:pass@localhost:5432/v1dbname" \\
        --target-url "postgresql://aetherion:aetherion@localhost:5432/aetherion"

ENV variables (loaded from .env.seed if present, or from shell environment):
    V1_POSTGRES_URL  — connection string for the v1 Aetherion Agent DB
    POSTGRES_URL     — connection string for the new Aetherion 2.0 DB
                       (asyncpg:// prefix auto-converted to plain postgresql://)
"""

import argparse
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# Load optional .env.seed file from monorepo root
_env_seed = os.path.join(os.path.dirname(__file__), "..", "..", ".env.seed")
if os.path.exists(_env_seed):
    with open(_env_seed) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

V1_DEFAULT_URL = os.getenv("V1_POSTGRES_URL", "")
TARGET_DEFAULT_URL = (
    os.getenv("POSTGRES_URL", "postgresql://aetherion:aetherion@localhost:5432/aetherion")
    .replace("postgresql+asyncpg://", "postgresql://")
)

COLUMNS = ("name_ua", "region_name", "lat", "lon", "lardi_town_id", "source", "created_at")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import ua_cities from Aetherion v1 Postgres DB"
    )
    parser.add_argument(
        "--source-url",
        default=V1_DEFAULT_URL,
        help="v1 DB connection URL (default: V1_POSTGRES_URL env var)",
    )
    parser.add_argument(
        "--target-url",
        default=TARGET_DEFAULT_URL,
        help="new DB connection URL (default: POSTGRES_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show row count without writing to DB",
    )
    args = parser.parse_args()

    if not args.source_url:
        print(
            "ERROR: --source-url is required.\n"
            "Set V1_POSTGRES_URL env var or pass --source-url explicitly.\n"
            "Example: V1_POSTGRES_URL=postgresql://user:pass@localhost:5432/v1db"
        )
        sys.exit(1)

    print(f"Source DB: {_mask_url(args.source_url)}")
    print(f"Target DB: {_mask_url(args.target_url)}")

    src = psycopg2.connect(args.source_url)
    tgt = psycopg2.connect(args.target_url)

    try:
        with src.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT {', '.join(COLUMNS)} FROM ua_cities ORDER BY id")
            rows = cur.fetchall()

        print(f"Found {len(rows)} rows in v1 ua_cities")

        if args.dry_run:
            print("DRY RUN — no data written. Remove --dry-run to import.")
            return

        cols = ", ".join(COLUMNS)
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        inserted = 0
        skipped = 0

        with tgt.cursor() as cur:
            for row in rows:
                values = tuple(row[c] for c in COLUMNS)
                try:
                    cur.execute(
                        f"INSERT INTO ua_cities ({cols}) VALUES ({placeholders}) "
                        f"ON CONFLICT (lardi_town_id) DO NOTHING",
                        values,
                    )
                    if cur.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    tgt.rollback()
                    print(
                        f"  WARN: skipped row "
                        f"lardi_town_id={row.get('lardi_town_id')}: {e}"
                    )
                    skipped += 1

        tgt.commit()
        print(f"Done: inserted={inserted}, skipped/conflict={skipped}")

    finally:
        src.close()
        tgt.close()


def _mask_url(url: str) -> str:
    """Hide password in connection URL for display."""
    import re
    return re.sub(r"(:)[^:@]+(@)", r"\1***\2", url)


if __name__ == "__main__":
    main()
