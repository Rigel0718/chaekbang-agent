from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import catalog, supply
from app.core.db import get_engine
from app.services.errors import ConflictError, NotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(title="chaekbang-agent", lifespan=lifespan)
app.include_router(catalog.router)
app.include_router(supply.router)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message})
