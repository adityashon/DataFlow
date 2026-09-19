

import io
import sqlite3
import xml.etree.ElementTree as ET
from typing import Dict
import pandas as pd



def ingest_file(content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
    """
    Read raw file bytes → return dict of {table_name: DataFrame}.

      
      This is the "uniform interface" principle — make all outputs look the
      same regardless of what went in. Consistency reduces bugs.
    """
    ext = filename.rsplit(".", 1)[-1].lower() # extension

    if ext == "csv":
        df = _read_csv(content)
        return {"main": df}

    elif ext in ("xlsx", "xls"):
        return _read_excel(content)

    elif ext == "xml":
        df = _read_xml(content)
        return {"main": df}

    elif ext == "sql":
        return _read_sql_script(content)

    elif ext in ("db", "sqlite", "sqlite3"):
        return _read_sqlite(content)

    else:
        raise ValueError(f"Unsupported file type: .{ext}")




def _read_csv(content: bytes) -> pd.DataFrame:
    """
    Robust CSV reader.
    
    WHY TRY MULTIPLE ENCODINGS?
      Files created on Windows often use cp1252 (a Microsoft encoding).
      Files from Linux/Mac use utf-8.
      If you only try one, half your users get errors.
      Try the most common ones in order, fall through if it fails.
    """
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            # sep=None + engine="python" tells pandas to auto-detect the delimiter
            # (could be comma, semicolon, tab — we don't assume)
            return pd.read_csv(
                io.BytesIO(content),
                encoding=encoding,
                sep=None,
                engine="python",
                on_bad_lines="skip"    # skip malformed rows instead of crashing
            )
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("Could not decode CSV — try saving as UTF-8")


def _read_excel(content: bytes) -> Dict[str, pd.DataFrame]:
    """
    Read all sheets from an Excel workbook.
    
    WHY READ ALL SHEETS?
      An analyst's spreadsheet often has 'Data', 'Summary', 'Lookup' sheets.
      Reading only the first sheet silently drops potentially critical data.
      Let the user choose which table to analyse.
    """
    xl = pd.ExcelFile(io.BytesIO(content))
    sheets = {}
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        if not df.empty:
            # Sanitise sheet name for use as a dict key
            clean_name = sheet_name.strip().replace(" ", "_").lower()
            sheets[clean_name] = df
    return sheets if sheets else {"main": pd.DataFrame()}


def _read_xml(content: bytes) -> pd.DataFrame:
    """
    Parse XML into a flat DataFrame.
    
    XML IS A TREE. DataFrames are tables.
    Strategy: try pandas built-in first (works for simple XML),
    then fall back to manual flattening for nested structures.
    
    WHY TWO `APPROACHES`?
      pandas.read_xml() assumes a very regular structure.
      Real-world XML is often messier. The fallback handles the mess.
    """
    try:
        return pd.read_xml(io.BytesIO(content))
    except Exception:
        pass  # Try manual approach

    # Manual approach: walk the tree, flatten each child element into a row
    root = ET.fromstring(content.decode("utf-8", errors="ignore"))
    records = []
    for child in root:
        record = {**child.attrib}          # element attributes become columns
        for elem in child:
            record[elem.tag] = elem.text   # child text becomes column value
        if record:
            records.append(record)

    if not records:
        raise ValueError("Could not extract tabular data from XML structure")

    return pd.DataFrame(records)


def _read_sql_script(content: bytes) -> Dict[str, pd.DataFrame]:
    """
    Execute a .sql script in an in-memory SQLite database.
    
    WHY IN-MEMORY?
      We don't want to save anything to disk — process it, extract the tables,
      then throw the database away. Clean, ephemeral, no cleanup needed.
      
    WHAT TYPES OF SQL WORK?
      CREATE TABLE + INSERT statements. Standard DDL/DML.
      Stored procedures and vendor-specific syntax won't work.
    """
    script = content.decode("utf-8", errors="ignore")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(script)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in cursor.fetchall()]

        if not table_names:
            raise ValueError("SQL script created no tables")

        tables = {}
        for name in table_names:
            df = pd.read_sql_query(f'SELECT * FROM "{name}"', conn)
            tables[name.lower()] = df

        return tables
    finally:
        conn.close()   # always close — even if an error occurred above


def _read_sqlite(content: bytes) -> Dict[str, pd.DataFrame]:
    """
    Read all tables from a SQLite database file.
    
    WHY WRITE TO A TEMP FILE?
      sqlite3 can only open files on disk, not bytes in memory.
      We write it to a temp file, read it, then delete it.
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in cursor.fetchall()]

        tables = {}
        for name in table_names:
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{name}"', conn)
                tables[name.lower()] = df
            except Exception:
                pass
        conn.close()
        return tables or {"main": pd.DataFrame()}
    finally:
        os.unlink(tmp_path)  # always clean up temp file