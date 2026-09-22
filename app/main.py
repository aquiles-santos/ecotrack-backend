from fastapi import FastAPI

from app.routers.alert_router import router as alert_router

app = FastAPI(
    title="EcoTrack API",
    description="API principal de monitoramento de qualidade do ar",
    version="0.1.0",
)

app.include_router(alert_router, prefix="/api/v1")
