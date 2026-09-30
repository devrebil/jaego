# PRO·PRO_Ins 입출고 수정·삭제 시 재고 재계산과 단가 열 노출을 검증하는 테스트
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ("PRO", "PRO_Ins")


def load_app(edition: str, workdir: Path):
    target = workdir / edition
    shutil.copytree(ROOT / edition, target, ignore=shutil.ignore_patterns(".venv", "db", "uploads", "dist", "Output"))
    sys.path.insert(0, str(target))
    for name in ("db", "app"):
        sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location("app", target / "app.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["app"] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(target))
    module.bootstrap()
    return module


class InoutEditTest(unittest.TestCase):
    def test_edit_and_delete_reconcile_stock(self):
        for edition in EDITIONS:
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as tmp:
                module = load_app(edition, Path(tmp))
                client = module.app.test_client()
                with client.session_transaction() as sess:
                    sess["user"], sess["role"] = "tester", "admin"

                def stock(sku):
                    rows = client.get("/api/inventory").get_json()
                    return next((r["stock"] for r in rows if r["sku"] == sku), None)

                res = client.post("/api/tx/batch", json={"items": [{
                    "date": "2026-10-01", "type": "매입", "contact": "테스트거래처", "sku": "T-1",
                    "item_name": "테스트", "buy_qty": 10, "buy_price": 500}]})
                self.assertTrue(res.get_json()["ok"], (res.status_code, res.data[:200]))
                tid = res.get_json()["ids"][0]
                self.assertEqual(stock("T-1"), 10)

                tx = next(t for t in client.get("/api/tx").get_json() if t["id"] == tid)
                self.assertEqual(tx["contact"], "테스트거래처")
                tx.update(buy_qty=4, buy_price=700, contact="수정거래처")
                self.assertTrue(client.post("/api/tx/save", json=tx).get_json()["ok"])
                self.assertEqual(stock("T-1"), 4)
                saved = next(t for t in client.get("/api/tx").get_json() if t["id"] == tid)
                self.assertEqual((saved["contact"], saved["total"]), ("수정거래처", 2800))

                self.assertTrue(client.post("/api/tx/delete", json={"id": tid}).get_json()["ok"])
                self.assertNotIn(tid, [t["id"] for t in client.get("/api/tx").get_json()])
                self.assertIn(stock("T-1"), (None, 0))

    def test_inout_table_has_price_column(self):
        for edition in EDITIONS:
            html = (ROOT / edition / "templates" / "index.html").read_text(encoding="utf-8")
            self.assertIn("['price','단가']", html, edition)
            self.assertIn("k==='price'", html, edition)


if __name__ == "__main__":
    unittest.main()
