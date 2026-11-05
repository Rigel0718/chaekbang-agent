"""비밀번호 해시와 인증 토큰. 표준 라이브러리만 쓴다."""

import base64
import hashlib
import hmac
import secrets

from app.core.config import get_settings

_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_TOKEN_BYTES = 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=256 * n * r, dklen=_KEY_BYTES
    )


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$hash` 형식. 같은 비밀번호도 salt가 달라 해시가 매번 다르다."""
    n = get_settings().password_scrypt_n
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _scrypt(password, salt, n, _R, _P)
    return f"scrypt${n}${_R}${_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash: str | None = None


def verify_dummy(password: str) -> None:
    """없는 아이디에도 해시 검증 한 번만큼 시간을 쓴다.

    응답 시간으로 아이디가 있는지 드러나지 않게 하기 위해서다.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _dummy_hash)


def new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """DB에는 토큰 원문 대신 SHA-256 해시(hex)를 저장한다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
