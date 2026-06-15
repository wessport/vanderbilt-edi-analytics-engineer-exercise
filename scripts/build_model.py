"""Build the local DuckDB analytical model for the EDI exercise."""

from __future__ import annotations

from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = ROOT / "data" / "edi_analytics.duckdb"
SQL_DIR = ROOT / "sql"
SQL_FILES = [
    "00_raw_tables.sql",
    "02_staging_tables.sql",
    "03_dimensions.sql",
    "04_facts.sql",
    "05_marts.sql",
]


def main() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    with duckdb.connect(str(DATABASE_PATH)) as connection:
        for sql_file in SQL_FILES:
            sql_path = SQL_DIR / sql_file
            print(f"Running {sql_path.relative_to(ROOT)}")
            connection.execute(sql_path.read_text(encoding="utf-8"))

        tables = connection.execute(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'main'
                and table_type = 'BASE TABLE'
            order by table_name
            """
        ).fetchall()
        print(f"Built {DATABASE_PATH.relative_to(ROOT)}")
        for (table_name,) in tables:
            row_count = connection.execute(f"select count(*) from {table_name}").fetchone()[0]
            print(f"{table_name}: {row_count:,} rows")


if __name__ == "__main__":
    main()
