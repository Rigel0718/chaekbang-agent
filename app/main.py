from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, books, holding_imports, holdings, library, loans, members, staff
from app.core.db import get_engine
from app.services.errors import (
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(title="chaekbang-agent", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(staff.router)
app.include_router(books.router)
app.include_router(holdings.router)
app.include_router(holding_imports.router)
app.include_router(members.router)
app.include_router(loans.router)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(AuthenticationError)
async def authentication_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401, content={"detail": exc.message}, headers={"WWW-Authenticate": "Bearer"}
    )


@app.exception_handler(InvalidRequestError)
async def invalid_request_handler(request: Request, exc: InvalidRequestError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.message, **exc.extra})
