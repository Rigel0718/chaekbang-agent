"""운영 에이전트 대화 API. 관리자만 쓴다(키오스크 403). 로직은 services/admin_chat.py에 있다.

프로필은 `app/main.py`가 `app.state.admin_profiles`에 운영 방식별로 둔다. LLM 클라이언트는 AI 사서와
같은 것을 쓴다. 분석 REST API는 아직 없다(화면은 `add-web-ui`).
"""

import uuid

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse

from app.library.admin_agent import PROFILE_NAME
from app.library.api.librarian import Llm, QueryEncoder, encode_events
from app.library.deps import AdminStaff, Session
from app.library.models.chat import SessionKind
from app.library.schemas.admin_agent import AdminMessageRequest
from app.library.services import admin_chat, chat

router = APIRouter(prefix="/admin-agent", tags=["admin-agent"])


@router.post(
    "/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def post_message(
    data: AdminMessageRequest,
    staff: AdminStaff,
    session: Session,
    request: Request,
    llm: Llm,
    encoder: QueryEncoder,
) -> StreamingResponse:
    """SSE로 `session`, `status`, `answer`(`message`, `unsupported`), `done` 사건을 보낸다.

    세션 id가 없으면 새 대화다. AI 사서 세션 id는 404다.
    """
    prepared = await admin_chat.prepare_admin_turn(
        session, staff.library_id, data.session_id, data.message, profile_name=PROFILE_NAME
    )
    profile = request.app.state.admin_profiles[prepared.loan_mode]
    return StreamingResponse(
        encode_events(admin_chat.stream_admin_turn(session, llm, profile, prepared, encoder)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, staff: AdminStaff, session: Session) -> Response:
    await chat.end_session(session, staff.library_id, session_id, SessionKind.ADMIN)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
