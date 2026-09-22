

import json
import random
import httpx
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.conf import settings


THEMES = [
    {"id": "shopeers", "name": "Shopeers",  "mode": "light", "sidebar": "wide"},
    {"id": "donezo",   "name": "Donezo",    "mode": "light", "sidebar": "wide"},
    {"id": "stakent",  "name": "Stakent",   "mode": "dark",  "sidebar": "wide"},
    {"id": "finpoint", "name": "FinPoint",  "mode": "dark",  "sidebar": "wide"},
    {"id": "make",     "name": "Make",      "mode": "light", "sidebar": "rail"},
]



# VIEW 1: Home page — shows the upload form


def index(request):

    return render(request, "core/index.html", {
        "title": "DataFlow — Upload Your Data",
    })


# VIEW 2: Handle file upload — calls FastAPI, stores result

@require_http_methods(["POST"])  # Only accept POST requests (decorator = middleware on one view)
def upload(request):

    # ── Check file was actually submitted ─────────────────────────────────────
    if "file" not in request.FILES:
        return render(request, "core/index.html", {
            "error": "Please select a file to upload.",
            "title": "DataFlow — Upload Your Data",
        })

    uploaded_file = request.FILES["file"]

    # ── Forward the file to FastAPI ────────────────────────────────────────────
    try:
        with httpx.Client(timeout=120.0) as client:  # 2 min timeout for large files
            response = client.post(
                f"{settings.FASTAPI_BASE_URL}/api/process/",
                files={"file": (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)},
            )
    except httpx.ConnectError:
        return render(request, "core/index.html", {
            "error": "⚠️ Processing service is not running. Start FastAPI with: uvicorn fastapi_service.main:app --port 8001",
            "title": "DataFlow — Upload Your Data",
        })
    except httpx.TimeoutException:
        return render(request, "core/index.html", {
            "error": "Processing timed out — try a smaller file.",
            "title": "DataFlow — Upload Your Data",
        })

    # ── Handle FastAPI response ────────────────────────────────────────────────
    if response.status_code != 200:
        error_detail = response.json().get("detail", "Unknown processing error")
        return render(request, "core/index.html", {
            "error": f"Processing error: {error_detail}",
            "title": "DataFlow — Upload Your Data",
        })

    data = response.json()

    # ── Store result in session ────────────────────────────────────────────────
    request.session["analytics_data"] = data
    request.session["filename"] = uploaded_file.name
    # Picking a fresh random dashboard style for THIS upload — re-rolled every
    # time so re-uploading gives a visually different dashboard.
    request.session["theme"] = random.choice(THEMES)
    request.session.modified = True  # tell Django the session changed

    return redirect("dashboard")


# VIEW 3: Dashboard — renders analytics with D3 charts

def dashboard(request):
 
    data = request.session.get("analytics_data")
    filename = request.session.get("filename", "Unknown file")
    theme = request.session.get("theme") or random.choice(THEMES)

    if not data:
        return redirect("index")

    return render(request, "core/dashboard.html", {
        "title":         "DataFlow — Analytics Dashboard",
        "filename":      filename,
        "file_type":     data.get("file_type", ""),
        "tables":        data.get("tables", []),
        "theme":         theme,
        "analytics_json": json.dumps(data),
    })


# VIEW 4: Download — generate standalone HTML dashboard for download

def download_dashboard(request):

    data     = request.session.get("analytics_data")
    filename = request.session.get("filename", "data")
    theme    = request.session.get("theme") or random.choice(THEMES)

    if not data:
        return redirect("index")

    html_content = render_to_string("core/offline_dashboard.html", {
        "title":          "DataFlow — Analytics Dashboard",
        "filename":       filename,
        "file_type":      data.get("file_type", ""),
        "tables":         data.get("tables", []),
        "theme":          theme,
        "standalone":     True,
        "analytics_json": json.dumps(data),
    })

    safe_name = filename.rsplit(".", 1)[0].replace(" ", "_")
    response = HttpResponse(html_content, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{safe_name}_dashboard.html"'
    
    return response