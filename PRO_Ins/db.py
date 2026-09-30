"""도메인별로 물리 분리된 SQLite DB 관리 + 감사 로그(히스토리).

위급 상황에서 특정 DB만 따로 복원할 수 있도록 도메인마다 .db 파일을 나눈다.
"""
import os
import shutil
import sqlite3
import json
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# 도메인 -> 파일명
DOMAINS = {
    "users": "users.db",
    "contacts": "contacts.db",
    "items": "items.db",
    "transactions": "transactions.db",
    "inventory": "inventory.db",
    "calendar": "calendar.db",
    "projects": "projects.db",
    "memo": "memo.db",
    "attendance": "attendance.db",
    "notice": "notice.db",
    "vouchers": "vouchers.db",
    "audit": "audit.db",
}

# 백업/복원 UI 노출용 한글 라벨
DOMAIN_LABELS = {
    "users": "사용자/권한/회사설정",
    "contacts": "거래처",
    "items": "품목(품목코드)",
    "transactions": "매입/매출 전표",
    "inventory": "재고 현황",
    "calendar": "일정/공휴일",
    "projects": "프로젝트/댓글",
    "memo": "개인 메모",
    "attendance": "출퇴근",
    "notice": "공지사항",
    "vouchers": "전표(판매/구매/견적)",
    "audit": "전체 히스토리(감사로그)",
}


def db_path(domain):
    return os.path.join(DB_DIR, DOMAINS[domain])


def get_db(domain):
    conn = sqlite3.connect(db_path(domain))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _exec(domain, sql):
    conn = get_db(domain)
    conn.executescript(sql)
    conn.commit()
    conn.close()


def init_all():
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    _exec("users", """
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT, birthday TEXT, dept TEXT,
        role TEXT DEFAULT 'member',
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT
    );
    """)

    _exec("contacts", """
    CREATE TABLE IF NOT EXISTS contacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, biz_no TEXT, ceo TEXT,
        phone TEXT, email TEXT, address TEXT, memo TEXT,
        photo TEXT, biz_cert TEXT, created_at TEXT
    );
    """)

    _exec("items", """
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        spec TEXT, unit TEXT,
        buy_price REAL DEFAULT 0, sell_price REAL DEFAULT 0,
        distributor TEXT, manufacturer TEXT,
        photo TEXT, created_at TEXT
    );
    """)

    _exec("transactions", """
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, type TEXT,
        contact TEXT, sku TEXT, item_name TEXT, spec TEXT, unit TEXT,
        buy_qty REAL DEFAULT 0, buy_price REAL DEFAULT 0,
        sell_qty REAL DEFAULT 0, sell_price REAL DEFAULT 0,
        return_qty REAL DEFAULT 0, return_price REAL DEFAULT 0,
        total REAL DEFAULT 0, note TEXT,
        channel TEXT, order_no TEXT, shipment_no TEXT, project_ref TEXT,
        author TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tx_types(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE
    );
    """)
    # 기본 구분값
    conn = get_db("transactions")
    for t in ("매입", "매출", "반품", "폐기", "실사재고변경"):
        conn.execute("INSERT OR IGNORE INTO tx_types(name) VALUES(?)", (t,))
    conn.commit(); conn.close()

    _exec("calendar", """
    CREATE TABLE IF NOT EXISTS schedules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, start_date TEXT, end_date TEXT,
        memo TEXT, status TEXT DEFAULT 'open',
        author TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS holidays(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, name TEXT
    );
    CREATE TABLE IF NOT EXISTS daily_todos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, date TEXT, content TEXT,
        done INTEGER DEFAULT 0, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS week_plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, year INTEGER, month INTEGER, week_no INTEGER,
        content TEXT, updated_at TEXT,
        UNIQUE(user,year,month,week_no)
    );
    """)

    _exec("projects", """
    CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, emoji TEXT DEFAULT '📁', start_date TEXT, end_date TEXT,
        status TEXT DEFAULT 'open', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS cards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER, author TEXT, content TEXT,
        images TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER, parent_id INTEGER,
        author TEXT, content TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL, actor TEXT, project_id INTEGER,
        source_type TEXT, source_id INTEGER, message TEXT,
        dismissed INTEGER DEFAULT 0, created_at TEXT
    );
    """)

    _exec("memo", """
    CREATE TABLE IF NOT EXISTS memos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author TEXT, tag TEXT, content TEXT,
        status TEXT DEFAULT 'open', sort_order INTEGER DEFAULT 0,
        created_at TEXT, done_at TEXT
    );
    CREATE TABLE IF NOT EXISTS memo_tags(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author TEXT NOT NULL,
        label TEXT NOT NULL,
        color TEXT NOT NULL DEFAULT '#4a90e2',
        priority INTEGER NOT NULL DEFAULT 0,
        UNIQUE(author, label)
    );
    """)

    _exec("attendance", """
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, type TEXT, ts TEXT
    );
    """)

    _exec("notice", """
    CREATE TABLE IF NOT EXISTS notices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author TEXT, title TEXT, content TEXT,
        level TEXT DEFAULT 'normal', created_at TEXT
    );
    """)

    _exec("vouchers", """
    CREATE TABLE IF NOT EXISTS vouchers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,                -- sale | purchase | quote
        date TEXT, seq INTEGER,   -- 일자-No
        warehouse TEXT, contact TEXT, dept TEXT,
        vat_mode TEXT,            -- excl(별도) | incl(포함) | none(미적용)
        memo TEXT, valid_until TEXT,
        status TEXT DEFAULT '미확인',
        posted INTEGER DEFAULT 0, printed INTEGER DEFAULT 0,
        supply REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL DEFAULT 0,
        author TEXT, created_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS voucher_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id INTEGER,
        sku TEXT, name TEXT, spec TEXT, unit TEXT,
        qty REAL DEFAULT 0, price REAL DEFAULT 0,
        supply REAL DEFAULT 0, tax REAL DEFAULT 0,
        note TEXT, sort INTEGER DEFAULT 0
    );
    """)

    _exec("audit", """
    CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, user TEXT, domain TEXT, action TEXT,
        target_id TEXT, before_json TEXT, after_json TEXT, detail TEXT, ip TEXT
    );
    """)

    # 기존 DB 호환 마이그레이션 (없는 컬럼만 안전하게 추가)
    _add_col("projects", "cards", "images", "TEXT")
    _add_col("projects", "cards", "blocks_json", "TEXT")
    _add_col("projects", "projects", "emoji", "TEXT DEFAULT '📁'")
    _add_col("items", "items", "location", "TEXT")
    _add_col("items", "items", "distributor", "TEXT")
    _add_col("items", "items", "manufacturer", "TEXT")
    _add_col("calendar", "schedules", "start_time", "TEXT")
    _add_col("calendar", "schedules", "end_time", "TEXT")
    _add_col("calendar", "schedules", "color", "TEXT DEFAULT '#2d7dd2'")
    _add_col("notice", "notices", "status", "TEXT DEFAULT 'open'")
    _add_col("notice", "notices", "completed_at", "TEXT")
    _add_col("users", "users", "email", "TEXT")
    _add_col("users", "users", "security_question", "TEXT")
    _add_col("users", "users", "security_answer_hash", "TEXT")
    _add_col("transactions", "transactions", "channel", "TEXT")
    _add_col("transactions", "transactions", "order_no", "TEXT")
    _add_col("transactions", "transactions", "shipment_no", "TEXT")
    _add_col("transactions", "transactions", "project_ref", "TEXT")
    _add_col("transactions", "transactions", "source_voucher_id", "INTEGER")
    _add_col("transactions", "transactions", "source_voucher_item_id", "INTEGER")
    _exec("transactions", """
    CREATE INDEX IF NOT EXISTS idx_transactions_source_voucher
        ON transactions(source_voucher_id);
    """)
    _add_col("audit", "audit", "ip", "TEXT")


def _add_col(domain, table, col, decl):
    conn = get_db(domain)
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            conn.commit()
        except Exception:
            pass
    conn.close()


def write_audit(user, domain, action, target_id=None, before=None, after=None, detail="", ip=None):
    """모든 쓰기 액션은 이 함수를 통해 audit.db 에 히스토리를 남긴다."""
    conn = get_db("audit")
    conn.execute(
        "INSERT INTO audit(ts,user,domain,action,target_id,before_json,after_json,detail,ip) VALUES(?,?,?,?,?,?,?,?,?)",
        (now_str(), user or "-", domain, action,
         str(target_id) if target_id is not None else None,
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False) if after is not None else None,
         detail, ip),
    )
    conn.commit()
    conn.close()


def now_str():
    # 초/밀리초까지 기록
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"


def get_setting(key, default=None):
    conn = get_db("users")
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db("users")
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
    conn.close()


AUTO_BACKUP_DIR = os.path.join(DB_DIR, "auto_backups")
AUTO_BACKUP_KEEP = 200  # 10분 주기 기준 약 33시간치 보관


def backup_all(tag="auto"):
    """모든 도메인 DB를 db/auto_backups/<시각>_<tag>/ 아래로 복사하고 오래된 백업을 정리한다.

    운영 중 다른 요청이 같은 DB에 동시에 쓰기를 하고 있어도 일관된 스냅샷이 되도록
    파일을 그냥 복사하지 않고 SQLite의 온라인 백업 API(Connection.backup)를 사용한다.
    """
    os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)
    # 초 단위만 쓰면 짧은 시간 안에 여러 번 백업할 때(수동 백업 연타 등) 폴더명이 겹칠 수 있어
    # 마이크로초까지 포함한다.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")
    dest_dir = os.path.join(AUTO_BACKUP_DIR, f"{stamp}_{tag}")
    os.makedirs(dest_dir, exist_ok=True)

    copied = []
    for domain, filename in DOMAINS.items():
        src = db_path(domain)
        if os.path.exists(src):
            src_conn = sqlite3.connect(src)
            dest_conn = sqlite3.connect(os.path.join(dest_dir, filename))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
                src_conn.close()
            copied.append(filename)

    entries = sorted(
        (e for e in os.listdir(AUTO_BACKUP_DIR) if os.path.isdir(os.path.join(AUTO_BACKUP_DIR, e))),
    )
    for stale in entries[:-AUTO_BACKUP_KEEP]:
        shutil.rmtree(os.path.join(AUTO_BACKUP_DIR, stale), ignore_errors=True)

    return dest_dir, copied
