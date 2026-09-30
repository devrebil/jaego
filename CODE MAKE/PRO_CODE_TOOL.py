# 판매자 비밀키로 고객별 Pro 라이선스 코드를 발급하는 전용 도구
from __future__ import annotations

import argparse
import base64
import json
import re
import secrets
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
PRIVATE_KEY_FILE = ROOT / "pro_license_private_key.pem"
LICENSE_VERIFY_FILE = PROJECT_ROOT / "FREE" / "license_verify.py"
ISSUED_LICENSE_DIR = ROOT / "issued_licenses"
PUBLIC_KEY_PATTERN = re.compile(r'^(LICENSE_PUBLIC_KEY_B64\s*=\s*)"[^"]*"', re.MULTILINE)
LICENSE_PREFIX = "PRO1"
CUSTOMER_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _load_private_key() -> Ed25519PrivateKey:
    if not PRIVATE_KEY_FILE.exists():
        raise SystemExit(
            "판매자 비밀키가 없습니다. 먼저 `python PRO_CODE_TOOL.py --setup`을 실행하세요."
        )
    key = serialization.load_pem_private_key(PRIVATE_KEY_FILE.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("판매자 비밀키 형식이 올바르지 않습니다.")
    return key


def _public_key_text(private_key: Ed25519PrivateKey) -> str:
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64url_encode(public_key)


def setup_signing_key() -> None:
    if PRIVATE_KEY_FILE.exists():
        private_key = _load_private_key()
        created = False
    else:
        private_key = Ed25519PrivateKey.generate()
        PRIVATE_KEY_FILE.write_bytes(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        created = True

    source = LICENSE_VERIFY_FILE.read_text(encoding="utf-8")
    public_key_text = _public_key_text(private_key)
    updated, replacements = PUBLIC_KEY_PATTERN.subn(
        rf'\1"{public_key_text}"', source, count=1
    )
    if replacements != 1:
        raise SystemExit(f"공개키 입력 위치를 찾지 못했습니다: {LICENSE_VERIFY_FILE}")
    LICENSE_VERIFY_FILE.write_text(updated, encoding="utf-8")

    print("판매자 비밀키를 새로 만들었습니다." if created else "기존 판매자 비밀키를 사용합니다.")
    print(f"비밀키 위치: {PRIVATE_KEY_FILE}")
    print(f"고객용 공개키 적용: {LICENSE_VERIFY_FILE}")
    print("비밀키는 고객용 Free 폴더나 ZIP에 절대 넣지 말고 별도로 백업하세요.")


def _assert_public_key_matches(private_key: Ed25519PrivateKey) -> None:
    source = LICENSE_VERIFY_FILE.read_text(encoding="utf-8")
    match = PUBLIC_KEY_PATTERN.search(source)
    if not match or _public_key_text(private_key) not in match.group(0):
        raise SystemExit(
            "Free 배포본의 공개키가 판매자 비밀키와 다릅니다. "
            "확인 후 `python PRO_CODE_TOOL.py --setup`을 실행하세요."
        )


def create_license_code(
    private_key: Ed25519PrivateKey,
    customer: str,
    license_id: str,
    expires_at: str = "",
) -> str:
    payload = {
        "v": 1,
        "edition": "pro",
        "license_id": license_id,
        "customer": customer,
        "issued_at": date.today().isoformat(),
        "expires_at": expires_at,
    }
    payload_text = _b64url_encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signed_text = f"{LICENSE_PREFIX}.{payload_text}"
    signature = _b64url_encode(private_key.sign(signed_text.encode("ascii")))
    return f"{signed_text}.{signature}"


def save_license_record(
    customer: str,
    license_id: str,
    expires_at: str,
    code: str,
) -> Path:
    ISSUED_LICENSE_DIR.mkdir(exist_ok=True)
    record_path = ISSUED_LICENSE_DIR / f"{license_id}.txt"
    if record_path.exists():
        raise SystemExit(f"같은 라이선스 번호의 발급 파일이 이미 있습니다: {record_path}")
    record_path.write_text(
        "\n".join((
            f"고객: {customer}",
            f"라이선스 번호: {license_id}",
            f"발급일: {date.today().isoformat()}",
            f"사용 기간: {expires_at or '영구'}",
            "",
            f"PRO CODE: {code}",
            "",
        )),
        encoding="utf-8",
    )
    return record_path


def main() -> int:
    parser = argparse.ArgumentParser(description="고객별 Pro 라이선스 코드를 발급합니다.")
    parser.add_argument("--setup", action="store_true", help="판매자 키를 준비하고 Free에 공개키를 적용합니다.")
    parser.add_argument("--customer-code", help="TXT 파일명으로 사용할 고객코드입니다.")
    parser.add_argument("--customer", help="코드에 별도로 표시할 고객명입니다.")
    parser.add_argument("--license-id", help="직접 지정할 라이선스 번호입니다.")
    parser.add_argument("--expires", default="", help="만료일 YYYY-MM-DD입니다. 생략하면 영구 라이선스입니다.")
    args = parser.parse_args()

    if args.setup:
        setup_signing_key()
        return 0

    private_key = _load_private_key()
    _assert_public_key_matches(private_key)
    customer_code = (args.customer_code or "").strip()
    if not customer_code and not args.customer:
        customer_code = input("고객코드: ").strip()
    if customer_code and (
        not CUSTOMER_CODE_PATTERN.fullmatch(customer_code)
        or customer_code.upper() in WINDOWS_RESERVED_NAMES
    ):
        parser.error("고객코드는 영문 또는 숫자로 시작하고 영문, 숫자, 밑줄, 하이픈만 1~64자로 입력하세요.")

    customer = (args.customer or customer_code).strip()
    if not customer or len(customer) > 120:
        parser.error("고객 식별값은 1~120자로 입력하세요.")

    license_id = (
        args.license_id
        or customer_code
        or f"LIC-{secrets.token_hex(6).upper()}"
    ).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", license_id):
        parser.error("라이선스 번호는 영문, 숫자, 밑줄, 하이픈 1~64자로 입력하세요.")

    expires_at = args.expires.strip()
    if expires_at:
        try:
            expiry = date.fromisoformat(expires_at)
        except ValueError:
            parser.error("만료일은 YYYY-MM-DD 형식으로 입력하세요.")
        if expiry < date.today():
            parser.error("만료일은 오늘 이후여야 합니다.")

    code = create_license_code(private_key, customer, license_id, expires_at)
    record_path = save_license_record(customer, license_id, expires_at, code)
    print()
    print(f"고객코드: {customer_code or license_id}")
    print(f"라이선스 번호: {license_id}")
    print(f"사용 기간: {expires_at or '영구'}")
    print(f"PRO CODE: {code}")
    print()
    print(f"발급 파일: {record_path}")
    print("PRO CODE 전체를 고객에게 보내세요. 같은 코드는 재설치 후에도 다시 사용할 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
