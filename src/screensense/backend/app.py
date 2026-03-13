from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException

from screensense.backend.service import BackendInferenceService
from screensense.inference.contracts import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="ScreenSense Backend", version="0.1.0")

_api_key = os.getenv("GEMINI_API_KEY", "").strip()
_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
_auth_token = os.getenv("BACKEND_AUTH_TOKEN", "").strip()
_service = BackendInferenceService(api_key=_api_key, model=_model) if _api_key else None


def _require_auth(authorization: str | None = Header(default=None)) -> None:
    if not _auth_token:
        return
    expected = f"Bearer {_auth_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "gemini_configured": str(bool(_api_key)).lower(),
        "model": _model,
    }


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(_require_auth)])
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    if _service is None:
        raise HTTPException(status_code=503, detail="Backend not configured: missing GEMINI_API_KEY")
    return _service.analyze(req)
