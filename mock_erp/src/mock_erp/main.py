from fastapi import FastAPI

from mock_erp.api.mock_erp_api import router

app = FastAPI(title="Mock ERP API")
app.include_router(router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness/readiness endpoint used by the Docker Compose healthcheck."""
    return {"status": "ok"}