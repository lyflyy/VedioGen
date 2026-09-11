import ipaddress
import socket
from time import monotonic
from urllib.parse import urljoin, urlsplit

import httpx


class PublicMediaError(RuntimeError):
    pass


def public_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password
                and parts.port in (None, 443) and len(url) <= 2048)
    except ValueError:
        return False


def fetch_public_image(url: str) -> bytes:
    deadline = monotonic() + 45
    for _ in range(4):
        if not public_url(url):
            raise PublicMediaError("素材地址必须是公开 HTTPS 地址")
        host = urlsplit(url).hostname
        try:
            addresses = [item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
            if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                raise PublicMediaError("素材地址指向非公开网络")
            # Pin the validated IP while preserving TLS hostname verification and Host.
            target = httpx.URL(url).copy_with(host=addresses[0])
            with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                with client.stream("GET", target, headers={"Host": host, "User-Agent": "VedioGen/0.1"},
                                   extensions={"sni_hostname": host}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200:
                        raise PublicMediaError(f"素材站点暂时无法下载（HTTP {response.status_code}）")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() > deadline or len(content) + len(chunk) > 10 * 1024 * 1024:
                            raise PublicMediaError("素材下载超时或超过 10 MB")
                        content.extend(chunk)
                    return bytes(content)
        except (OSError, httpx.HTTPError, ValueError) as error:
            raise PublicMediaError("无法连接素材来源，请选择其他候选") from error
    raise PublicMediaError("素材来源重定向过多")
