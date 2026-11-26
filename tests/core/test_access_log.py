"""[platform/request-logging] 접속 기록에서 질의 문자열 지우기."""

import logging

import app.main  # noqa: F401  앱을 불러오면 필터가 붙는다
from app.core.access_log import ACCESS_LOGGER, DropQueryString, install_access_log_filter

ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'  # uvicorn 접속 기록과 같은 모양


def _logged(path: str, status: int = 200) -> str:
    record = logging.LogRecord(
        ACCESS_LOGGER,
        logging.INFO,
        __file__,
        0,
        ACCESS_FORMAT,
        ("127.0.0.1:5000", "GET", path, "1.1", status),
        None,
    )
    assert DropQueryString().filter(record) is True
    return record.getMessage()


def test_member_search_query_is_dropped() -> None:
    """[platform/request-logging] 접속 기록에서 질의 문자열 지우기 / 회원 찾기 주소"""
    # uvicorn은 질의 문자열을 받은 그대로(퍼센트 인코딩) 남긴다. 두 모양 모두 지운다.
    for path in ("/members?q=김하늘", "/members?q=%EA%B9%80%ED%95%98%EB%8A%98&limit=20"):
        message = _logged(path)
        assert "GET /members HTTP/1.1" in message
        assert "200" in message
        assert "김하늘" not in message
        assert "q=" not in message
        assert "%EA" not in message


def test_path_without_query_is_kept() -> None:
    """[platform/request-logging] 접속 기록에서 질의 문자열 지우기 / 질의 문자열이 없는 주소"""
    assert '"GET /holdings HTTP/1.1" 200' in _logged("/holdings")


def test_other_records_pass_unchanged() -> None:
    """[platform/request-logging] 접속 기록에서 질의 문자열 지우기 / 인자 모양이 다른 기록"""
    record = logging.LogRecord(ACCESS_LOGGER, logging.INFO, __file__, 0, "%s", ("a?b",), None)
    assert DropQueryString().filter(record) is True
    assert record.getMessage() == "a?b"


def test_filter_installed_once_on_app_import() -> None:
    """[platform/request-logging] 접속 기록에서 질의 문자열 지우기 / 앱을 불러오면 적용됨"""
    install_access_log_filter()  # 다시 불러도 늘지 않는다
    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, DropQueryString) for f in filters) == 1
