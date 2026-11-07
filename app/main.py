from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.db import get_engine
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from app.features.children.api import router as children_router
from app.features.children.hook import ChildrenHook
from app.library.api import (
    auth,
    book_enrichment,
    holding_imports,
    holdings,
    library,
    library_books,
    loans,
    members,
    staff,
)
from app.library.hooks import register_hook

# 기관 개별 기능을 조립한다. 기능을 빼려면 이 줄과 라우터를 지우면 된다.
register_hook(ChildrenHook())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(title="chaekbang-agent", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(staff.router)
app.include_router(library_books.router)
app.include_router(children_router)
app.include_router(book_enrichment.router)
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
