from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

docs_router = APIRouter(tags=["docs"])


@docs_router.get("/openapi.json", include_in_schema=False)
async def openapi_json():
    # Imported here (not at module top) to avoid a circular import with nexus.app.
    from nexus.app import app

    return JSONResponse(content=app.openapi(), media_type="application/json")
