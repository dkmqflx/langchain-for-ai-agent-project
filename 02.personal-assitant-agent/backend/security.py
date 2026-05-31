"""
refresh_token 암호화/복호화 — Fernet (cryptography 공식)

왜 암호화하는가:
  refresh_token은 사실상 "영구 출입증"이다. DB가 유출돼도 이 값이 평문이면
  공격자가 사용자의 Gmail에 무기한 접근할 수 있다. 그래서 DB에는 반드시 암호화해 저장.

Fernet:
  대칭키 암호화. 같은 키(TOKEN_ENCRYPTION_KEY)로 암호화/복호화.
  키 생성: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from cryptography.fernet import Fernet

from config import get_settings


def _fernet() -> Fernet:
    # 키는 .env의 TOKEN_ENCRYPTION_KEY (44자 base64 문자열)
    return Fernet(get_settings().token_encryption_key.encode())


def encrypt(plaintext: str) -> str:
    """평문 → 암호문(문자열). DB 저장 직전에 사용."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """암호문 → 평문. DB에서 꺼내 실제 API 호출에 쓰기 직전에 사용."""
    return _fernet().decrypt(ciphertext.encode()).decode()
