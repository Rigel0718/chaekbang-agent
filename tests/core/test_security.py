"""비밀번호 해시와 토큰 (app/core/security.py)."""

from app.core.security import hash_password, hash_token, new_token, verify_password


def test_hash_does_not_contain_password() -> None:
    """[library/staff-auth] 직원 계정과 역할 / 비밀번호 원문 미저장 (해시 형식)"""
    hashed = hash_password("library-pass-1")
    assert "library-pass-1" not in hashed
    assert hashed.startswith("scrypt$")
    assert verify_password("library-pass-1", hashed)


def test_wrong_password_rejected() -> None:
    """틀린 비밀번호와 깨진 해시는 거부한다."""
    hashed = hash_password("library-pass-1")
    assert not verify_password("library-pass-2", hashed)
    assert not verify_password("library-pass-1", "not-a-hash")
    assert not verify_password("library-pass-1", "bcrypt$1$2$3$4$5")


def test_same_password_hashes_differ() -> None:
    """같은 비밀번호도 salt가 달라 해시가 다르다."""
    assert hash_password("same-password") != hash_password("same-password")


def test_token_hash_is_stable_and_not_token() -> None:
    token = new_token()
    assert hash_token(token) == hash_token(token)
    assert token not in hash_token(token)
    assert new_token() != token
