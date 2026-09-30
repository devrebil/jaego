# 고객이 입력한 Pro 라이선스 코드의 Ed25519 서명을 검증하는 모듈
from __future__ import annotations

import base64
import binascii
import json
from datetime import date

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


LICENSE_PUBLIC_KEY_B64 = "fAL_4VnasmiUliOLZW6ZqccGRb1oMmeJcrAGAObGbtA"
LICENSE_PREFIX = "PRO1"


class LicenseValidationError(ValueError):
    pass


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_license_code(code: str) -> str:
    return "".join(str(code or "").split())


def verify_license_code(code: str, today: date | None = None) -> tuple[str, dict]:
    normalized = normalize_license_code(code)
    if not normalized or len(normalized) > 4096:
        raise LicenseValidationError("활성화 코드가 올바르지 않습니다.")

    parts = normalized.split(".")
    if len(parts) != 3 or parts[0] != LICENSE_PREFIX:
        raise LicenseValidationError("활성화 코드가 올바르지 않습니다.")

    try:
        public_key_bytes = _b64url_decode(LICENSE_PUBLIC_KEY_B64)
        payload_bytes = _b64url_decode(parts[1])
        signature = _b64url_decode(parts[2])
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError,
            binascii.Error, InvalidSignature):
        raise LicenseValidationError("활성화 코드가 올바르지 않습니다.") from None

    if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("edition") != "pro":
        raise LicenseValidationError("활성화 코드가 올바르지 않습니다.")

    for key in ("license_id", "customer", "issued_at"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise LicenseValidationError("활성화 코드가 올바르지 않습니다.")

    expires_at = str(payload.get("expires_at") or "")
    try:
        date.fromisoformat(payload["issued_at"])
        expiry = date.fromisoformat(expires_at) if expires_at else None
    except ValueError:
        raise LicenseValidationError("활성화 코드가 올바르지 않습니다.") from None
    if expiry and (today or date.today()) > expiry:
        raise LicenseValidationError("라이선스 사용 기간이 만료됐습니다.")

    return normalized, payload
