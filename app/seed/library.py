"""기관과 직원 계정 시드. 기관 이름과 로그인 아이디로 있으면 건너뛴다."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.library.models.library import Library, LibraryType, LoanMode, StaffRole, StaffUser


@dataclass(frozen=True)
class SeedLibrary:
    key: str  # 계정·등록번호 접두어
    name: str
    loan_mode: LoanMode
    default_loan_days: int = 14


SUNNY = SeedLibrary("sunny", "햇살 작은도서관", LoanMode.INTERNAL)
FOREST = SeedLibrary("forest", "푸른숲 작은도서관", LoanMode.IMPORTED)
LIBRARIES = (SUNNY, FOREST)


async def seed_libraries(
    session: AsyncSession, admin_password: str, kiosk_password: str
) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """({기관 key: library_id}, 보고)를 돌려준다."""
    rows = [
        {
            "name": lib.name,
            "type": LibraryType.SMALL_LIBRARY,
            "loan_mode": lib.loan_mode,
            "default_loan_days": lib.default_loan_days,
        }
        for lib in LIBRARIES
    ]
    created = await session.execute(
        insert(Library)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(Library.id)
    )
    created_libraries = len(created.all())
    ids = dict(
        (
            await session.execute(
                select(Library.name, Library.id).where(
                    Library.name.in_([lib.name for lib in LIBRARIES])
                )
            )
        ).all()
    )
    library_ids = {lib.key: ids[lib.name] for lib in LIBRARIES}

    staff_rows = []
    for lib in LIBRARIES:
        for role, password in (
            (StaffRole.ADMIN, admin_password),
            (StaffRole.KIOSK, kiosk_password),
        ):
            staff_rows.append(
                {
                    "library_id": library_ids[lib.key],
                    "login_id": f"{lib.key}-{role.value}",
                    "password_hash": hash_password(password),
                    "role": role,
                }
            )
    # 이미 있는 계정의 비밀번호는 바꾸지 않는다.
    created = await session.execute(
        insert(StaffUser)
        .values(staff_rows)
        .on_conflict_do_nothing(index_elements=["login_id"])
        .returning(StaffUser.id)
    )
    created_staff = len(created.all())
    return library_ids, {
        "libraries": (created_libraries, len(rows) - created_libraries),
        "staff_users": (created_staff, len(staff_rows) - created_staff),
    }
