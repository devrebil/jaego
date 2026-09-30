# PRO·FREE 배포 폴더와 ZIP에서 런타임·민감 파일이 제외됐는지 검증하는 테스트
from __future__ import annotations

import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ("PRO", "FREE")
COMMON_FILES = {
    "app.py",
    "db.py",
    "https_gateway.py",
    "launcher.py",
    "ONE_CLICK_START.bat",
    "README.md",
    "requirements.txt",
    "restart_server.ps1",
    "SERVER_RESTART.bat",
    "SERVER_STOP.bat",
    "setup_and_start.ps1",
    "start_hidden.vbs",
    "static/vendor/ZXING-LICENSE.txt",
    "static/vendor/zxing-browser-0.1.4.min.js",
    "stop_server.ps1",
    "templates/index.html",
}
MANUAL_FILES = {"static/manual.html"} | {
    path.relative_to(ROOT / "PRO").as_posix() for path in (ROOT / "PRO" / "static" / "manual_images").glob("*") if path.is_file()
}
EXPECTED_FILES = {
    "PRO": COMMON_FILES | MANUAL_FILES,
    "FREE": COMMON_FILES | {"license_verify.py"},
}
FORBIDDEN_NAMES = {
    ".venv",
    "__pycache__",
    ".session_secret",
    "install-start.log",
    "server.log",
    "server.pid",
    "server.key",
    "pro_license_private_key.pem",
}


class DistributionLayoutTest(unittest.TestCase):
    def test_distribution_source_files_exist(self):
        for edition in EDITIONS:
            folder = ROOT / edition
            self.assertTrue(folder.is_dir())
            for relative_path in EXPECTED_FILES[edition]:
                self.assertTrue((folder / relative_path).is_file(), relative_path)

    def test_distribution_zips_are_exact_clean_copies(self):
        for edition in EDITIONS:
            archive_path = ROOT / f"{edition}.zip"
            self.assertTrue(archive_path.is_file())
            with zipfile.ZipFile(archive_path) as archive:
                entries = {
                    info.filename.replace("\\", "/").lstrip("./"): info.filename
                    for info in archive.infolist()
                    if not info.is_dir()
                }
                self.assertEqual(set(entries), EXPECTED_FILES[edition])
                self.assertEqual(len(entries), len(archive.infolist()))
                for relative_path, stored_name in entries.items():
                    self.assertEqual(
                        archive.read(stored_name),
                        (ROOT / edition / relative_path).read_bytes(),
                        relative_path,
                    )
                    parts = Path(relative_path).parts
                    self.assertFalse(any(part in FORBIDDEN_NAMES for part in parts))
                    self.assertFalse(relative_path.lower().endswith((".db", ".pyc", ".log", ".key")))

    def test_code_maker_stays_outside_customer_archives(self):
        self.assertTrue((ROOT / "CODE MAKE" / "pro_license_private_key.pem").is_file())
        for edition in EDITIONS:
            with zipfile.ZipFile(ROOT / f"{edition}.zip") as archive:
                names = {Path(name).name for name in archive.namelist()}
            self.assertNotIn("PRO_CODE_TOOL.py", names)
            self.assertNotIn("pro_license_private_key.pem", names)


if __name__ == "__main__":
    unittest.main()
