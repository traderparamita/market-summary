"""CSV I/O utilities shared across data collectors.

Common pattern used in collect_macro.py, collect_sector_etfs.py:
  1. load_csv_dedup  — read existing CSV and return (DataFrame, existing_keys set)
  2. append_save_csv — concat new rows, sort, write back to CSV
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv_dedup(
    csv_path: Path,
    columns: list[str],
    date_col: str = "DATE",
    key_cols: tuple[str, str] = ("DATE", "INDICATOR_CODE"),
    parse_dates: bool = False,
) -> tuple[pd.DataFrame, set]:
    """Load existing CSV and return (df, existing_keys).

    Args:
        csv_path:    Path to the CSV file.
        columns:     Column names used to create an empty DataFrame if the file
                     does not exist yet.
        date_col:    Column to parse as dates when parse_dates=True.
        key_cols:    Two-column tuple that forms the dedup key.
        parse_dates: Pass True when callers need datetime objects (sector ETFs).

    Returns:
        (df, existing_keys)
        existing_keys is a set of (date_str, indicator_code) tuples.
    """
    if not csv_path.exists():
        return pd.DataFrame(columns=columns), set()

    df = pd.read_csv(csv_path, parse_dates=[date_col] if parse_dates else False)
    df.columns = df.columns.str.upper()

    c0, c1 = key_cols
    if parse_dates:
        keys = set(zip(df[c0].dt.strftime("%Y-%m-%d"), df[c1]))
    else:
        keys = set(zip(df[c0].astype(str), df[c1]))

    return df, keys


def append_save_csv(
    csv_path: Path,
    existing: pd.DataFrame,
    new_rows: list[dict] | pd.DataFrame,
    sort_cols: list[str] = ("DATE", "INDICATOR_CODE"),
    date_col: str = "DATE",
    date_format: str = "%Y-%m-%d",
) -> int:
    """Concat new_rows onto existing, sort, and overwrite csv_path.

    Args:
        csv_path:    Destination CSV path.
        existing:    DataFrame already loaded from csv_path.
        new_rows:    New data as a list of dicts or a DataFrame.
        sort_cols:   Columns to sort by before writing.
        date_col:    Column to coerce to datetime before sorting.
        date_format: strftime format used when writing the date column.

    Returns:
        Number of new rows written.
    """
    if isinstance(new_rows, list):
        if not new_rows:
            return 0
        df_new = pd.DataFrame(new_rows)
    else:
        df_new = new_rows
        if df_new.empty:
            return 0

    n = len(df_new)
    df_all = pd.concat([existing, df_new], ignore_index=True)
    df_all[date_col] = pd.to_datetime(df_all[date_col])
    df_all = df_all.sort_values(list(sort_cols)).reset_index(drop=True)
    df_all.to_csv(csv_path, index=False, date_format=date_format)
    return n
