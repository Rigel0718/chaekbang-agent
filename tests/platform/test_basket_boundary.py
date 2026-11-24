"""[circulation/member-basket] 담은 책은 어디에도 쓰지 않음: 소스 경계.

담은 책 테이블과 모델을 언급하는 앱 코드는 허용 목록뿐이다. 추천·AI 사서·분석·노출 기록이
이 테이블을 읽는 길이 생기면 이 테스트가 먼저 걸린다. 행 수 불변은 test_member_basket.py가 본다.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {
    "library/models/circulation.py",  # 모델
    "library/services/basket.py",  # 담기·불러오기·빼기·비우기·만료 정리
    "library/api/basket.py",  # REST (service만 부른다)
    "library/schemas/basket.py",
    "models.py",  # TENANT_TABLES 등록
}
NAMES = re.compile(r"BasketItem|basket_items")


def _mentions() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        if NAMES.search(path.read_text(encoding="utf-8")):
            found.add(path.relative_to(APP).as_posix())
    return found


def test_only_allowed_files_mention_the_basket_table() -> None:
    """[circulation/member-basket] 어디에도 쓰지 않음 / 테이블을 쓰는 파일"""
    assert _mentions() <= ALLOWED, _mentions() - ALLOWED


def test_basket_service_does_not_log() -> None:
    """[circulation/member-basket] 어디에도 쓰지 않음 / 로그"""
    source = (APP / "library/services/basket.py").read_text(encoding="utf-8")
    assert not re.search(r"\blogg(er|ing)\b|\bprint\(|\.(debug|info|warning|error)\(", source)


def test_basket_api_is_thin() -> None:
    """[circulation/member-basket] 어디에도 쓰지 않음 / 라우터는 service만 부른다"""
    source = (APP / "library/api/basket.py").read_text(encoding="utf-8")
    assert "BasketItem" not in source and "select(" not in source
