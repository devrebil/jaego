"""PRO 재고관리 - 트레이 상주형 실행기.

기존 ONE_CLICK_START.bat + 콘솔창 방식 대신, 설치 후에는 이 프로그램 하나가
백그라운드(시스템 트레이)에 계속 떠서 서버를 관리한다.

- 트레이 아이콘 좌클릭/더블클릭 또는 "웹 화면 열기": 브라우저로 접속
- "Windows 시작 시 자동 실행": 체크박스로 켬/끔 (레지스트리 HKCU\\Run, 관리자 권한 불필요)
- "서버 종료": 트레이 아이콘과 서버를 함께 종료 (종료 전 전체 DB 자동 백업)
"""
import ctypes
from ctypes import wintypes
import os
import sys
import socket
import threading
import time
import traceback
import webbrowser
import winreg

import pystray
from PIL import Image, ImageDraw

HOST = "0.0.0.0"
LOCAL_HOST = "127.0.0.1"
PORT = int(os.environ.get("PRO_TEST_PORT", 5000))
HTTPS_PORT = int(os.environ.get("PRO_TEST_HTTPS_PORT", 5443))
URL = f"http://{LOCAL_HOST}:{PORT}"

BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
LOG_FILE = os.path.join(BASE_DIR, "server.log")
PID_FILE = os.path.join(BASE_DIR, "server.pid")

APP_NAME = "PRO재고관리"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

AUTO_BACKUP_INTERVAL_SEC = 600  # 10분


def write_log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


try:
    from waitress import serve
    import db

    # PyInstaller로 얼린 실행 파일에서는 db.py 자체가 앱과 함께 묶인 내부 폴더
    # (_internal 등)에서 로드되므로, db.py가 __file__ 기준으로 계산한 기본 DB_DIR은
    # 실행 파일이 있는 설치 폴더가 아니라 그 내부 폴더를 가리킨다. 이 상태로 두면
    # 실제 업무 데이터(db/, uploads/)가 "앱 내부 코드" 취급을 받는 _internal 아래에
    # 섞여 들어가, 이후 업데이트/재설치 때 함께 지워질 위험이 있다. app.py를
    # 임포트하기 전에 여기서 먼저 실행 파일 옆의 경로로 고정한다.
    db.DB_DIR = os.path.join(BASE_DIR, "db")
    db.UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    db.AUTO_BACKUP_DIR = os.path.join(db.DB_DIR, "auto_backups")

    from app import app, bootstrap
except Exception:
    write_log("Tray app import failed.")
    write_log(traceback.format_exc())
    raise


# ── Windows 시작 시 자동 실행 (레지스트리 HKCU\\Run, 관리자 권한 불필요) ──
def _startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = os.path.abspath(__file__)
    return f'"{pythonw}" "{script}"'


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command())
            write_log("Windows 시작 시 자동 실행: 켜짐")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            write_log("Windows 시작 시 자동 실행: 꺼짐")


# ── 서버 / 자동 백업 ──
def safe_backup(tag):
    try:
        dest_dir, copied = db.backup_all(tag=tag)
        write_log(f"Auto-backup ({tag}) saved {len(copied)} DB file(s) to {os.path.basename(dest_dir)}.")
    except Exception:
        write_log(f"Auto-backup ({tag}) failed.")
        write_log(traceback.format_exc())


def periodic_backup_loop():
    while True:
        time.sleep(AUTO_BACKUP_INTERVAL_SEC)
        safe_backup("auto")


# ── Windows 종료/로그오프 시 안전 종료 ──
# Stop-Process -Force(강제 종료)와 달리, 실제 Windows 종료·로그오프는 모든 최상위
# 창에 WM_QUERYENDSESSION을 먼저 방송한다. 이 메시지를 받는 숨김 창을 하나 만들어
# 두면, Windows가 우리 프로세스를 정리하기 전에 마지막으로 한 번 더 백업할 시간을
# 벌 수 있다. 트레이 아이콘의 "서버 종료"와는 별개의, 사용자가 직접 끄지 않는
# 상시 안전장치이므로 별도 설정 토글은 두지 않는다.
_WM_QUERYENDSESSION = 0x0011
_WM_ENDSESSION = 0x0016
_WM_DESTROY = 0x0002
_shutdown_backup_done = False


def _shutdown_wnd_proc(hwnd, msg, wparam, lparam):
    global _shutdown_backup_done
    if msg in (_WM_QUERYENDSESSION, _WM_ENDSESSION):
        if not _shutdown_backup_done:
            _shutdown_backup_done = True
            write_log("Windows 종료/로그오프 감지: 종료 전 백업을 실행합니다.")
            safe_backup("shutdown")
        return 1
    if msg == _WM_DESTROY:
        ctypes.windll.user32.PostQuitMessage(0)
        return 0
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def start_shutdown_watcher():
    def run():
        try:
            user32 = ctypes.windll.user32
            wnd_proc_type = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            wnd_proc = wnd_proc_type(_shutdown_wnd_proc)

            class WNDCLASS(ctypes.Structure):
                _fields_ = [
                    ("style", ctypes.c_uint), ("lpfnWndProc", wnd_proc_type), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ]

            wc = WNDCLASS()
            wc.lpfnWndProc = wnd_proc
            wc.lpszClassName = "PRO재고관리_ShutdownWatcher"
            if not user32.RegisterClassW(ctypes.byref(wc)):
                write_log("Shutdown watcher: RegisterClassW failed.")
                return
            hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "PRO재고관리 종료 감시", 0, 0, 0, 0, 0, None, None, None, None)
            if not hwnd:
                write_log("Shutdown watcher: CreateWindowExW failed.")
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            write_log("Shutdown watcher crashed.")
            write_log(traceback.format_exc())

    threading.Thread(target=run, daemon=True).start()


def server_is_running():
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((LOCAL_HOST, PORT)) == 0


def start_server_thread():
    def run():
        write_log("Bootstrapping database and starting server.")
        bootstrap()
        try:
            import https_gateway
            # db와 같은 이유로 인증서 저장 위치도 실행 파일 옆으로 고정한다.
            https_gateway.CERT_DIR = os.path.join(BASE_DIR, "certs")
            https_gateway.CERT_FILE = os.path.join(https_gateway.CERT_DIR, "server.crt")
            https_gateway.KEY_FILE = os.path.join(https_gateway.CERT_DIR, "server.key")
            https_gateway.start(port=HTTPS_PORT, target_port=PORT)
            write_log(f"HTTPS gateway started on port {HTTPS_PORT}.")
        except Exception:
            write_log("HTTPS gateway failed. HTTP server will continue.")
            write_log(traceback.format_exc())
        threading.Thread(target=periodic_backup_loop, daemon=True).start()
        write_log(f"HTTP server starting on {HOST}:{PORT}.")
        serve(app, host=HOST, port=PORT, threads=8)

    threading.Thread(target=run, daemon=True).start()


# ── 트레이 아이콘 ──
def make_icon_image():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=14, fill=(74, 144, 226, 255))
    draw.text((size / 2 - 10, size / 2 - 16), "P", fill=(255, 255, 255, 255))
    return img


def open_browser(icon=None, item=None):
    webbrowser.open(URL)


def toggle_autostart(icon, item):
    set_autostart(not is_autostart_enabled())


def quit_app(icon, item):
    write_log("Quit requested from tray menu.")
    safe_backup("exit")
    icon.stop()
    os._exit(0)


def wait_then_open_browser():
    for _ in range(50):
        if server_is_running():
            webbrowser.open(URL)
            return
        time.sleep(0.2)


def main():
    if server_is_running():
        write_log("Server is already running. Opening browser only.")
        webbrowser.open(URL)
        return

    try:
        with open(PID_FILE, "w", encoding="ascii") as pid_file:
            pid_file.write(str(os.getpid()))
    except Exception:
        pass

    start_server_thread()
    threading.Thread(target=wait_then_open_browser, daemon=True).start()
    start_shutdown_watcher()

    icon = pystray.Icon(
        APP_NAME,
        icon=make_icon_image(),
        title=f"{APP_NAME} (실행 중)",
        menu=pystray.Menu(
            pystray.MenuItem("웹 화면 열기", open_browser, default=True),
            pystray.MenuItem(
                "Windows 시작 시 자동 실행",
                toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("서버 종료", quit_app),
        ),
    )
    icon.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        write_log("Tray app crashed.")
        write_log(traceback.format_exc())
        raise
