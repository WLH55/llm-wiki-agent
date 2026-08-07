"""使用 Playwright 抓取 JavaScript 渲染后的网页。"""

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.sync_api import Page, Request, Route, TimeoutError, sync_playwright

logger = logging.getLogger(__name__)

_GOTO_TIMEOUT_MS = 30_000
_NETWORK_IDLE_TIMEOUT_MS = 10_000
_CONTENT_WAIT_TIMEOUT_MS = 15_000
_MIN_RENDERED_TEXT_LENGTH = 80
_MAX_HTML_CHARACTERS = 10_000_000


def _chromium_launch_args() -> list[str]:
    """容器内非 root 用户运行 Chromium 需要禁用 SUID sandbox。

    由环境变量 PLAYWRIGHT_NO_SANDBOX 控制（Docker 镜像内默认开启），
    本地开发保持默认关闭，行为不变。
    """
    if os.getenv("PLAYWRIGHT_NO_SANDBOX", "").strip().lower() in ("1", "true", "yes"):
        return ["--no-sandbox"]
    return []


@dataclass(frozen=True)
class ScrapeResult:
    """一次网页抓取的完整结果。"""

    url: str
    final_url: str
    html: str
    visible_text: str
    page_title: str


def _is_unsafe_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断目标地址是否不应由网页抓取器访问。"""

    return not address.is_global


def validate_public_url(url: str) -> None:
    """校验 URL 只能指向公开的 HTTP(S) 地址。

    域名的所有解析结果都必须是公网地址；只要混入一个内网地址就拒绝，
    避免攻击者用多条 DNS 记录绕过 SSRF 校验。
    """

    try:
        parsed = urlsplit(url.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("unsafe_url: invalid_url") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("unsafe_url: unsupported_scheme")
    if not parsed.hostname:
        raise ValueError("unsafe_url: missing_host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("unsafe_url: credentials_not_allowed")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("unsafe_url: local_host")

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        literal_address = None

    if literal_address is not None:
        if _is_unsafe_ip(literal_address):
            raise ValueError("unsafe_url: non_public_address")
        return

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        address_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("unsafe_url: dns_resolution_failed") from exc

    addresses = {item[4][0] for item in address_info}
    if not addresses:
        raise ValueError("unsafe_url: dns_resolution_failed")
    if any(_is_unsafe_ip(ipaddress.ip_address(address)) for address in addresses):
        raise ValueError("unsafe_url: non_public_address")


def _wait_for_rendered_content(page: Page) -> None:
    """等待网络趋于空闲，并给 SPA 正文一次渲染机会。"""

    try:
        page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
    except TimeoutError:
        logger.info("等待 networkidle 超时，继续读取当前 DOM")

    try:
        page.wait_for_function(
            """(minLength) => {
                const root = document.querySelector('#js_content')
                    || document.querySelector('#app')
                    || document.querySelector('main')
                    || document.querySelector('[role="main"]')
                    || document.body;
                return ((root?.innerText || '').trim().length >= minLength);
            }""",
            arg=_MIN_RENDERED_TEXT_LENGTH,
            timeout=_CONTENT_WAIT_TIMEOUT_MS,
        )
    except TimeoutError:
        logger.info("等待网页正文长度达标超时，使用当前 DOM")


def _read_visible_text(page: Page) -> str:
    """优先读取正文容器，最后回退到整个 body。"""

    return page.evaluate(
        """() => {
            const root = document.querySelector('#js_content')
                || document.querySelector('#app')
                || document.querySelector('main')
                || document.querySelector('[role="main"]')
                || document.body;
            return (root?.innerText || '').trim();
        }"""
    )


def _guard_request(route: Route, request: Request) -> None:
    """在浏览器发出请求前阻止内网 HTTP(S) 目标。"""

    scheme = urlsplit(request.url).scheme.lower()
    if scheme not in {"http", "https"}:
        route.continue_()
        return
    try:
        validate_public_url(request.url)
    except ValueError:
        logger.warning("已阻止不安全的网页请求：%s", request.url)
        route.abort("blockedbyclient")
        return
    route.continue_()


def scrape_url(url: str) -> ScrapeResult:
    """用无头 Chromium 抓取 URL，返回渲染后的 HTML 与可见文本。"""

    source_url = url.strip()
    validate_public_url(source_url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=_chromium_launch_args())
        try:
            page = browser.new_page()
            page.route("**/*", _guard_request)
            page.goto(
                source_url,
                timeout=_GOTO_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
            _wait_for_rendered_content(page)

            final_url = page.url
            validate_public_url(final_url)
            html = page.content()
            if len(html) > _MAX_HTML_CHARACTERS:
                raise ValueError("web_page_too_large")

            return ScrapeResult(
                url=source_url,
                final_url=final_url,
                html=html,
                visible_text=_read_visible_text(page),
                page_title=page.title().strip(),
            )
        finally:
            browser.close()
