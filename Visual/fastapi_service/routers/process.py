

from fastapi import APIRouter, UploadFile, File, HTTPException ,status
from fastapi.responses import JSONResponse

from fastapi_service.services.ingest   import ingest_file
from fastapi_service.services.clean    import clean_dataframe
from fastapi_service.services.analytics import generate_analytics

# APIRouter is like Django's include() — a group of related endpoints
router = APIRouter( tags=["processing"])

@router.post("/process/")
async def process_file(file: UploadFile = File(...)):
    """
    Main endpoint: receive a file, process it, return analytics JSON.
    
    FLOW:
      1. Read the uploaded bytes
      2. Ingest into DataFrames (handles all formats)
      3. Clean each DataFrame
      4. Generate analytics for each
      5. Return everything as JSON.
    """
    # ── Guard: check file type ────────────────────────────────────────────────
    ALLOWED = {"csv", "xlsx", "xls", "xml", "sql", "db", "sqlite", "sqlite3"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '.{ext}' not supported. Allowed: {', '.join(sorted(ALLOWED))}"
        )

    # ── Read file bytes ────────────────────────────────────────────────────────
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Could not read file: {e}"
            )

    # ── Ingest → Clean → Analyse ───────────────────────────────────────────────
    try:
        raw_tables = ingest_file(content, file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, 
            detail=f"Ingestion failed: {e}"
            )

    results = {}
    for table_name, raw_df in raw_tables.items():
        if raw_df.empty:
            continue
        try:
            clean_df, cleaning_report = clean_dataframe(raw_df)
            analytics = generate_analytics(clean_df)
            results[table_name] = {
                "cleaning_report": cleaning_report,
                "analytics":       analytics,
            }
        except Exception as e:
            # Don't crash the whole request if one table fails
            # Report it so the user knows
            results[table_name] = {"error": str(e)}

    if not results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No usable data found in file"
              )

    return JSONResponse({
        "success":   True,
        "filename":  file.filename,
        "file_type": ext,
        "tables":    list(results.keys()),
        "results":   results,
    })


@router.get("/health/")
async def health_check():
    """Simple health check — Django pings this to verify FastAPI is running."""
    return {
        "status": "ok",
        "service": "DataFlow FastAPI",
        'version':'v2.0',
        }