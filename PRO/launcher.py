"""Start the inventory server without a console and open the browser."""
import os
import socket
import threading
import time
import traceback
import webbrowser


HOST = "127.0.0.1"
PORT = 5000
HTTPS_PORT = 5443
URL = f"http://{HOST}:{PORT}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "server.pid")
LOG_FILE = os.path.join(BASE_DIR, "server.log")


def write_log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{stamp}] {message}\n")


try:
    from waitress import serve
    from app import app, bootstrap
    import db
except Exception:
    write_log("Launcher import failed.")
    write_log(traceback.format_exc())
    raise


AUTO_BACKUP_INTERVAL_SEC = 600  # 10분


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


def server_is_running():
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, PORT)) == 0


def open_browser_when_ready():
    for _ in range(50):
        if server_is_running():
            webbrowser.open(URL)
            return
        time.sleep(0.1)


if __name__ == "__main__":
    try:
        if server_is_running():
            write_log("Server is already running. Opening browser.")
            webbrowser.open(URL)
        else:
            with open(PID_FILE, "w", encoding="ascii") as pid_file:
                pid_file.write(str(os.getpid()))
            try:
                write_log("Bootstrapping database and starting server.")
                bootstrap()
                try:
                    # Mobile camera scanning needs HTTPS. HTTP still works if this fails.
                    import https_gateway
                    https_gateway.start(port=HTTPS_PORT, target_port=PORT)
                    write_log(f"HTTPS gateway started on port {HTTPS_PORT}.")
                except Exception:
                    write_log("HTTPS gateway failed. HTTP server will continue.")
                    write_log(traceback.format_exc())
                threading.Thread(target=open_browser_when_ready, daemon=True).start()
                threading.Thread(target=periodic_backup_loop, daemon=True).start()
                write_log(f"HTTP server starting on 0.0.0.0:{PORT}.")
                serve(app, host="0.0.0.0", port=PORT, threads=8)
            finally:
                # 강제 종료(Stop-Process -Force)는 이 지점에 도달하지 못하므로
                # 정상 종료 시 대비 백업이며, 실제 종료 백업은 stop_server.ps1이
                # /api/system/backup-all 호출로 보장한다.
                safe_backup("exit")
                try:
                    os.remove(PID_FILE)
                except FileNotFoundError:
                    pass
    except Exception:
        write_log("Server startup failed.")
        write_log(traceback.format_exc())
        raise
