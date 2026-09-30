"""HTTPS 게이트웨이.

모바일 브라우저의 카메라(getUserMedia)는 HTTPS에서만 동작하므로,
자체 서명 인증서를 자동 생성하고 별도 포트(기본 5443)에서 TLS를 종단한 뒤
로컬 waitress(HTTP)로 그대로 전달하는 경량 프록시를 제공한다.

- 인증서는 certs/ 폴더에 저장되며 현재 PC의 LAN IP를 SAN에 포함한다.
  IP가 바뀌어 SAN에 없는 IP가 생기면 다음 시작 때 자동 재발급된다.
- 자체 서명이므로 휴대폰 브라우저에서 최초 1회 보안 경고를 수락해야 한다.
"""
import datetime
import os
import socket
import ssl
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.join(BASE_DIR, "certs")
CERT_FILE = os.path.join(CERT_DIR, "server.crt")
KEY_FILE = os.path.join(CERT_DIR, "server.key")


def lan_ips():
    """현재 PC의 IPv4 주소 목록(루프백 포함)."""
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            ips.add(probe.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("169.254."))


def _certificate_covers(ips):
    """기존 인증서가 현재 IP를 모두 포함하고 유효기간이 넉넉하면 True."""
    from cryptography import x509

    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        return False
    try:
        with open(CERT_FILE, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        covered = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
        expires = cert.not_valid_after_utc
        soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
        return set(ips) <= covered and expires > soon
    except Exception:
        return False


def ensure_certificate():
    """자체 서명 인증서를 생성한다(현재 IP가 SAN에 없거나 만료 임박 시 재발급)."""
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    ips = lan_ips()
    if _certificate_covers(ips):
        return

    os.makedirs(CERT_DIR, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "inventory-server")])
    san = x509.SubjectAlternativeName(
        [x509.DNSName("localhost"), x509.DNSName(socket.gethostname())]
        + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(KEY_FILE, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def _pump(src, dst):
    """한 방향으로 바이트를 그대로 복사한다."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client, ctx, target_port):
    tls = upstream = None
    try:
        tls = ctx.wrap_socket(client, server_side=True)
        upstream = socket.create_connection(("127.0.0.1", target_port), timeout=10)
    except (ssl.SSLError, OSError):
        for sock in (tls or client, upstream):
            try:
                sock and sock.close()
            except OSError:
                pass
        return
    threading.Thread(target=_pump, args=(tls, upstream), daemon=True).start()
    _pump(upstream, tls)
    for sock in (tls, upstream):
        try:
            sock.close()
        except OSError:
            pass


def start(port=5443, target_port=5000):
    """HTTPS 게이트웨이를 백그라운드 스레드로 시작한다."""
    ensure_certificate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(100)

    def accept_loop():
        while True:
            try:
                client, _ = server.accept()
            except OSError:
                break
            threading.Thread(target=_handle, args=(client, ctx, target_port), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return server


if __name__ == "__main__":
    import sys

    https_port = int(sys.argv[1]) if len(sys.argv) > 1 else 5443
    http_port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    start(https_port, http_port)
    print(f"HTTPS gateway: https://0.0.0.0:{https_port} -> http://127.0.0.1:{http_port}")
    threading.Event().wait()
