"""서버 접속 기록에서 요청 주소의 질의 문자열을 지운다.

회원 찾기(`/members?q=이름`)와 이용자 검색(`/catalog/search?q=검색어`)처럼 주소에 실린 값이
기록에 남지 않게 한다. 메서드·경로·응답 코드는 그대로 남긴다.
"""

import logging

ACCESS_LOGGER = "uvicorn.access"
# uvicorn 접속 기록의 인자: (client_addr, method, full_path, http_version, status_code)
_ARG_COUNT = 5
_PATH_INDEX = 2


class DropQueryString(logging.Filter):
    """기록 인자의 요청 주소를 `?` 앞까지로 바꾼다. 인자 모양이 다르면 손대지 않는다."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == _ARG_COUNT:
            path = args[_PATH_INDEX]
            if isinstance(path, str) and "?" in path:
                cleaned = list(args)
                cleaned[_PATH_INDEX] = path.split("?", 1)[0]
                record.args = tuple(cleaned)
        return True


def install_access_log_filter(logger_name: str = ACCESS_LOGGER) -> None:
    """접속 기록 로거에 필터를 한 번만 붙인다. 앱을 불러올 때 부른다.

    uvicorn은 앱을 불러오기 전에 기록 설정을 마치므로, 여기서 붙인 필터가 남는다.
    """
    logger = logging.getLogger(logger_name)
    if not any(isinstance(f, DropQueryString) for f in logger.filters):
        logger.addFilter(DropQueryString())
