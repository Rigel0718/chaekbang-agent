"""service 계층의 도메인 예외. HTTP와 무관하며, REST에서는 main.py의 핸들러가 상태 코드로 바꾼다."""


class DomainError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """요청한 대상이 없다 (REST: 404)."""


class ConflictError(DomainError):
    """중복이거나 다른 데이터가 참조 중이라 처리할 수 없다 (REST: 409)."""


class AuthenticationError(DomainError):
    """아이디·비밀번호가 맞지 않거나 사용할 수 없는 계정이다 (REST: 401)."""


class InvalidRequestError(DomainError):
    """값의 형식은 맞지만 업무 규칙상 받을 수 없는 요청이다 (REST: 422)."""
