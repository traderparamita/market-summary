"""
Snowflake DDL Migration Script

Executes FND.sql and MKT.sql to create/update Snowflake schema.

Usage:
    python db/migrate.py               # Execute both FND and MKT DDL
    python db/migrate.py --schema FND  # Execute FND only
    python db/migrate.py --schema MKT  # Execute MKT only
    python db/migrate.py --dry-run     # Show DDL without executing
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("migrate")


def get_snowflake_conn():
    """Create Snowflake connection."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        database=os.environ.get("SNOWFLAKE_DATABASE", "FDE_DB"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "FDE_WH"),
    )


def execute_ddl(sql_file: Path, *, dry_run: bool = False) -> int:
    """Execute DDL from SQL file.

    Args:
        sql_file: Path to SQL file
        dry_run: If True, print SQL without executing

    Returns:
        Number of statements executed
    """
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    logger.info(f"Reading {sql_file.name}...")
    sql = sql_file.read_text(encoding="utf-8")

    def _strip_leading_comments(stmt: str) -> str:
        """Remove leading `--` comment lines and blank lines from a SQL statement.

        MKT.sql 는 각 섹션 앞에 '-- ===' 주석 블록을 두기 때문에, ';' 로 split 하면
        다음 DDL/DML 이 `--` 로 시작하는 문자열이 된다. 그대로 skip 하면 CREATE/INSERT
        가 누락되므로 주석·공백 줄만 제거하고 실제 SQL body 로 판단한다.
        """
        lines = stmt.splitlines()
        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()
            if not line or line.startswith("--"):
                idx += 1
                continue
            break
        return "\n".join(lines[idx:]).strip()

    # Split by semicolon (simple approach)
    raw_statements = [s.strip() for s in sql.split(";") if s.strip()]
    statements = [_strip_leading_comments(s) for s in raw_statements]
    statements = [s for s in statements if s]  # drop pure-comment blocks

    if dry_run:
        logger.info(f"[DRY-RUN] Would execute {len(statements)} statements:")
        for i, stmt in enumerate(statements, 1):
            first_line = stmt.split("\n")[0][:80]
            logger.info(f"  {i}. {first_line}...")
        return len(statements)

    conn = get_snowflake_conn()
    try:
        cur = conn.cursor()
        for i, stmt in enumerate(statements, 1):
            try:
                logger.info(f"Executing statement {i}/{len(statements)}: {stmt.splitlines()[0][:80]}")
                cur.execute(stmt)
            except Exception as e:
                logger.error(f"Statement {i} failed: {e}")
                logger.debug(f"Statement:\n{stmt[:200]}")
                raise
        conn.commit()
        logger.info(f"✓ {sql_file.name}: {len(statements)} statements executed")
        return len(statements)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Snowflake DDL Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--schema",
        choices=["FND", "MKT"],
        help="Execute specific schema DDL only (default: both)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show DDL without executing",
    )
    args = parser.parse_args()

    db_dir = Path(__file__).parent

    schemas = ["FND", "MKT"] if args.schema is None else [args.schema]

    total = 0
    for schema in schemas:
        sql_file = db_dir / f"{schema}.sql"
        n = execute_ddl(sql_file, dry_run=args.dry_run)
        total += n

    status = "(dry-run)" if args.dry_run else "executed"
    logger.info(f"\n=== Migration complete: {total} statements {status} ===")


if __name__ == "__main__":
    main()
