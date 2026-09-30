# 고객별 Pro 라이선스의 발급, 재입력, 변조 거부 흐름을 검증하는 테스트
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
FREE_DIR = ROOT / "FREE"
CODE_MAKE_DIR = ROOT / "CODE MAKE"
FREE_SITE_PACKAGES = FREE_DIR / ".venv" / "Lib" / "site-packages"
os.environ.setdefault("INVENTORY_SESSION_SECRET", "license-test-session-secret")
try:
    import holidays  # noqa: F401
except ModuleNotFoundError:
    sys.modules["holidays"] = types.ModuleType("holidays")
sys.path.insert(0, str(ROOT))
if FREE_SITE_PACKAGES.exists():
    sys.path.insert(0, str(FREE_SITE_PACKAGES))
sys.path.insert(0, str(FREE_DIR))
sys.path.insert(0, str(CODE_MAKE_DIR))

import app as free_app
import license_verify
import PRO_CODE_TOOL as pro_code_tool
from PRO_CODE_TOOL import create_license_code


def public_key_text(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class ProLicenseTest(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key_patch = patch.object(
            license_verify, "LICENSE_PUBLIC_KEY_B64", public_key_text(self.private_key)
        )
        self.public_key_patch.start()

    def tearDown(self):
        self.public_key_patch.stop()

    def make_code(self, expires_at: str = "") -> str:
        return create_license_code(
            self.private_key, "테스트 고객", "LIC-TEST-0001", expires_at
        )

    def test_same_perpetual_code_can_be_verified_repeatedly(self):
        code = self.make_code()

        first_code, first_payload = license_verify.verify_license_code(code)
        second_code, second_payload = license_verify.verify_license_code(code)

        self.assertEqual(first_code, second_code)
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_payload["expires_at"], "")

    def test_one_distribution_accepts_different_customer_codes(self):
        first = create_license_code(
            self.private_key, "첫 번째 고객", "LIC-CUSTOMER-0001"
        )
        second = create_license_code(
            self.private_key, "두 번째 고객", "LIC-CUSTOMER-0002"
        )

        self.assertEqual(license_verify.verify_license_code(first)[1]["customer"], "첫 번째 고객")
        self.assertEqual(license_verify.verify_license_code(second)[1]["customer"], "두 번째 고객")

    def test_tampered_code_is_rejected(self):
        code = self.make_code()
        prefix, payload, signature = code.split(".")
        index = len(payload) // 2
        replacement = "A" if payload[index] != "A" else "B"
        tampered_payload = payload[:index] + replacement + payload[index + 1:]
        tampered_code = f"{prefix}.{tampered_payload}.{signature}"

        with self.assertRaises(license_verify.LicenseValidationError):
            license_verify.verify_license_code(tampered_code)

    def test_expired_code_is_rejected(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        code = self.make_code(yesterday)

        with self.assertRaisesRegex(license_verify.LicenseValidationError, "만료"):
            license_verify.verify_license_code(code)

    def test_activation_accepts_same_code_after_fresh_install_state(self):
        code = self.make_code()
        settings = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = str(value)

        with (
            patch.object(free_app, "get_setting", side_effect=get_setting),
            patch.object(free_app, "set_setting", side_effect=set_setting),
            patch.object(free_app, "write_audit"),
        ):
            free_app.app.config.update(TESTING=True, SECRET_KEY="license-test")
            client = free_app.app.test_client()
            with client.session_transaction() as session:
                session["user"] = "admin"
                session["role"] = "admin"

            first = client.post("/api/license/activate", json={"code": code})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(free_app.current_edition(), free_app.PRO_EDITION)

            settings.clear()
            self.assertEqual(free_app.current_edition(), free_app.FREE_EDITION)
            settings["edition"] = "pro"
            self.assertEqual(free_app.current_edition(), free_app.FREE_EDITION)
            settings.clear()

            second = client.post("/api/license/activate", json={"code": code})
            self.assertEqual(second.status_code, 200)
            self.assertEqual(free_app.current_edition(), free_app.PRO_EDITION)

    def test_customer_code_is_used_for_license_id_and_record_filename(self):
        customer_code = "CUST-2026-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(pro_code_tool, "ISSUED_LICENSE_DIR", Path(temp_dir)),
                patch.object(pro_code_tool, "_load_private_key", return_value=self.private_key),
                patch.object(pro_code_tool, "_assert_public_key_matches"),
                patch.object(sys, "argv", ["PRO_CODE_TOOL.py"]),
                patch("builtins.input", return_value=customer_code),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(pro_code_tool.main(), 0)

            record_path = Path(temp_dir) / f"{customer_code}.txt"
            self.assertTrue(record_path.is_file())
            record = record_path.read_text(encoding="utf-8")
            self.assertIn(f"고객: {customer_code}", record)
            self.assertIn(f"라이선스 번호: {customer_code}", record)

            with (
                patch.object(pro_code_tool, "ISSUED_LICENSE_DIR", Path(temp_dir)),
                patch.object(pro_code_tool, "_load_private_key", return_value=self.private_key),
                patch.object(pro_code_tool, "_assert_public_key_matches"),
                patch.object(sys, "argv", ["PRO_CODE_TOOL.py"]),
                patch("builtins.input", return_value=customer_code),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(SystemExit, "이미 있습니다"),
            ):
                pro_code_tool.main()


if __name__ == "__main__":
    unittest.main()
