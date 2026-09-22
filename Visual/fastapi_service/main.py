
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_service.routers.process import router

# ── Create the FastAPI application 
app = FastAPI(
    title="DataFlow Processing API",
    description="Microservice for data ingestion, cleaning, and analytics",
    version="1.0.0",
    # These docs are auto-generated — visit http://localhost:8001/docs
    docs_url="/docs",
    redoc_url="/redoc",
)



# ── Register routers 
app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "DataFlow FastAPI",
        "docs":    "api/docs",
        "health":  "/api/health/",
    }