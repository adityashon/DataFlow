

from typing import Tuple, Dict, Any, List
import pandas as pd
import re


def clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    
    The cleaning_report is a structured record of every change made.
    It's like a doctor's operation notes — complete, auditable, transparent.
    """
    report: Dict[str, Any] = {
        "original_shape": {"rows": len(df), "cols": len(df.columns)},
        "steps": [],          # list of human-readable descriptions
        "step_details": [],   # list of dicts with machine-readable details
    }

    df = df.copy()  # never mutate the original — work on a copy

    # ── Step 1: Normalise column names ────────────────────────────────────────

    original_cols = list(df.columns)
    df.columns = (
        pd.Series(df.columns.astype(str))
        .str.strip()
        .str.lower()
        .str.replace(r"[^\w\s]", "", regex=True)  
        .str.replace(r"\s+", "_", regex=True)       
        .str.strip("_")
    )
    renamed = {o: n for o, n in zip(original_cols, df.columns) if str(o).strip() != n}
    if renamed:
        _record(report, f"Renamed {len(renamed)} columns to snake_case",
                {"type": "rename", "count": len(renamed), "mapping": renamed})

    # ── Step 2: Strip string whitespace ───────────────────────────────────────

    obj_cols = df.select_dtypes(include="object").columns.tolist()
    stripped_count = 0
    for col in obj_cols:
        before = df[col].copy()
        df[col] = df[col].str.strip() if hasattr(df[col], "str") else df[col]
        stripped_count += (before != df[col]).sum()
    if stripped_count:
        _record(report, f"Stripped whitespace from {stripped_count} cells across {len(obj_cols)} text columns",
                {"type": "strip_whitespace", "cells_changed": int(stripped_count)})

    # ── Step 3: Drop fully empty rows & columns ────────────────────────────────

    before_shape = df.shape
    df = df.dropna(how="all").dropna(axis=1, how="all")
    dropped_rows = before_shape[0] - df.shape[0]
    dropped_cols = before_shape[1] - df.shape[1]
    if dropped_rows or dropped_cols:
        _record(report, f"Removed {dropped_rows} fully-empty rows and {dropped_cols} empty columns",
                {"type": "drop_empty", "rows_dropped": dropped_rows, "cols_dropped": dropped_cols})

    # ── Step 4: Coerce numeric strings ────────────────────────────────────────
    # STRATEGY: only convert if 70%+ of the non-null values look numeric.
    # (If only 2 out of 100 values look numeric, it's probably not a number col)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        non_null   = df[col].notna().sum()
        successful = converted.notna().sum()
        if non_null > 0 and successful / non_null > 0.70:
            df[col] = converted
            _record(report, f"Converted '{col}' from text to numeric",
                    {"type": "coerce_numeric", "column": col, "success_rate": round(successful / non_null, 2)})

    # ── Step 5: Parse date columns ────────────────────────────────────────────

    for col in df.select_dtypes(include="object").columns:
        try:
            parsed   = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
            non_null = df[col].notna().sum()
            success  = parsed.notna().sum()
            if non_null > 0 and success / non_null > 0.70:
                df[col] = parsed
                _record(report, f"Parsed '{col}' as datetime",
                        {"type": "parse_datetime", "column": col})
        except Exception:
            pass

    # ── Step 6: Impute missing values ─────────────────────────────────────────

    # STRATEGY:
    #   - Numeric columns → fill with MEDIAN (robust to outliers, unlike mean)
    #   - Categorical columns → fill with MODE (most common value)
    total_missing = int(df.isnull().sum().sum())
    imputed_cols: List[str] = []

    for col in df.select_dtypes(include="number").columns:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].median())
            imputed_cols.append(col)

    for col in df.select_dtypes(include="object").columns:
        if df[col].isnull().any():
            mode_vals = df[col].mode()
            fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else "Unknown"
            df[col] = df[col].fillna(fill_val)
            imputed_cols.append(col)

    if total_missing > 0:
        _record(report, f"Imputed {total_missing} missing values (median for numbers, mode for text)",
                {"type": "impute", "total_missing": total_missing, "columns_affected": imputed_cols})

    # ── Step 7: Remove duplicates ─────────────────────────────────────────────
    dup_count = int(df.duplicated().sum())
    df = df.drop_duplicates()
    if dup_count:
        _record(report, f"Removed {dup_count} duplicate rows",
                {"type": "dedup", "duplicates_removed": dup_count})

    # ── Final report ──────────────────────────────────────────────────────────
    report["final_shape"] = {"rows": len(df), "cols": len(df.columns)}
    report["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}

    return df, report



# HELPER

def _record(report: dict, message: str, detail: dict) -> None:
    """Add a step to the cleaning report."""
    report["steps"].append(message)
    report["step_details"].append(detail)