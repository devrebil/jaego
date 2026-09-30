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

    def test_tx_list_paging_and_total_header(self):
        for edition in EDITIONS:
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as tmp:
                module = load_app(edition, Path(tmp))
                client = module.app.test_client()
                with client.session_transaction() as sess:
                    sess["user"], sess["role"] = "tester", "admin"
                base = int(client.get("/api/tx?limit=0").headers["X-Total-Count"])
                items = [{"date": "2026-10-01", "type": "매입", "sku": f"P-{i}", "item_name": "페이지", "buy_qty": 1,
                          "buy_price": 1} for i in range(1200)]
                for start in range(0, len(items), 500):  # 일괄 API는 한 번에 최대 500건
                    self.assertTrue(client.post("/api/tx/batch", json={"items": items[start:start + 500]}).get_json()["ok"])
                default = client.get("/api/tx")
                self.assertEqual(len(default.get_json()), 1000)
                self.assertEqual(int(default.headers["X-Total-Count"]), base + 1200)
                rest = client.get("/api/tx?offset=1000&limit=1000")
                self.assertEqual(len(rest.get_json()), base + 200)
                ids = {t["id"] for t in default.get_json()} | {t["id"] for t in rest.get_json()}
                self.assertEqual(len(ids), base + 1200)
                self.assertEqual(len(client.get("/api/tx?limit=0").get_json()), base + 1200)
                only = client.post("/api/tx/batch", json={"items": [{"date": "2026-10-02", "type": "매출", "contact": "명세표거래처",
                    "sku": "S-1", "item_name": "필터", "sell_qty": 1, "sell_price": 1}]}).get_json()["ok"]
                self.assertTrue(only)
                filtered = client.get("/api/tx?contact=명세표거래처&type=매출&start=2026-10-01&end=2026-10-31&limit=0")
                self.assertEqual([t["contact"] for t in filtered.get_json()], ["명세표거래처"])
                self.assertEqual(filtered.headers["X-Total-Count"], "1")
                self.assertEqual(client.get("/api/tx?contact=명세표거래처&type=매입&limit=0").get_json(), [])

    def test_sample_data_only_on_fresh_install(self):
        for edition in EDITIONS:
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as tmp:
                module = load_app(edition, Path(tmp))  # 새 설치: 예시 데이터 생성
                conn = module.get_db("contacts")
                self.assertGreater(conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
                conn.close()
                module.set_setting("seeded", "")  # 예전 버전 DB처럼 표식이 없고
                for domain, table in (("contacts", "contacts"), ("items", "items"), ("transactions", "transactions"),
                                      ("notice", "notices"), ("memo", "memos"), ("projects", "projects")):
                    c = module.get_db(domain); c.execute(f"DELETE FROM {table}"); c.commit(); c.close()
                c = module.get_db("contacts")
                c.execute("INSERT INTO contacts(name) VALUES('기존고객거래처')"); c.commit(); c.close()
                module.bootstrap()  # 업데이트 후 재시작: 실제 데이터가 있으니 예시를 추가하면 안 됨
                for domain, table, expect in (("contacts", "contacts", 1), ("items", "items", 0), ("transactions", "transactions", 0),
                                              ("notice", "notices", 0), ("memo", "memos", 0), ("projects", "projects", 0)):
                    c = module.get_db(domain)
                    self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], expect, (edition, table))
                    c.close()
                self.assertEqual(module.get_setting("seeded"), "1")

    def test_inout_table_has_price_column(self):
        for edition in EDITIONS:
            html = (ROOT / edition / "templates" / "index.html").read_text(encoding="utf-8")
            self.assertIn("['price','단가']", html, edition)
            self.assertIn("k==='price'", html, edition)

    def test_tables_have_sort_and_pager(self):
        for edition in EDITIONS:
            html = (ROOT / edition / "templates" / "index.html").read_text(encoding="utf-8")
            for token in ("hsortClick('inout'", "hsortClick('inventory'", "pagerDraw('inout'",
                          "pagerDraw('inventory'", "loadMoreInout", "async function stmtLoadRows", "불러오는 중", "function sortItems", "function drawItems"):
                self.assertIn(token, html, f"{edition}: {token}")


if __name__ == "__main__":
    unittest.main()
