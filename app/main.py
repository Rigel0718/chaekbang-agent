import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.db import get_engine, get_sessionmaker
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    LimitExceededError,
    NotFoundError,
)
from app.features.children.api import router as children_router
from app.features.children.hook import ChildrenHook
from app.features.children.tools import children_extension
from app.library.api import (
    auth,
    book_enrichment,
    catalog,
    holding_imports,
    holdings,
    librarian,
    library,
    library_books,
    loans,
    members,
    staff,
)
from app.library.hooks import register_hook
from app.library.librarian import build_librarian_profiles
from app.library.services.chat import purge_forever

# 기관 개별 기능을 조립한다. 기능을 빼려면 이 줄들과 라우터를 지우면 된다.
register_hook(ChildrenHook())
LIBRARIAN_EXTENSIONS = (children_extension(),)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 끝난 AI 사서 대화를 1분마다 지운다. 도서관이 문을 닫아도 마지막 대화가 남지 않게 한다.
    purge = asyncio.create_task(purge_forever(get_sessionmaker()))
    yield
    purge.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await purge
    await get_engine().dispose()


app = FastAPI(title="chaekbang-agent", lifespan=lifespan)
# AI 사서 프로필은 운영 방식별로 하나씩이다. 라우터가 기관의 loan_mode로 고른다.
app.state.librarian_profiles = build_librarian_profiles(LIBRARIAN_EXTENSIONS)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(staff.router)
app.include_router(library_books.router)
app.include_router(catalog.router)
app.include_router(children_router)
app.include_router(book_enrichment.router)
app.include_router(holdings.router)
app.include_router(holding_imports.router)
app.include_router(members.router)
app.include_router(loans.router)
app.include_router(librarian.router)


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


@app.exception_handler(LimitExceededError)
async def limit_exceeded_handler(request: Request, exc: LimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": exc.message})
