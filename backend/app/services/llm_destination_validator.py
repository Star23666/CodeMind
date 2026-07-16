import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import settings


PROVIDER_HOSTS = {
    "siliconflow": "api.siliconflow.cn",
    "openai": "api.openai.com",
}
PROXY_FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)


class LlmDestinationError(RuntimeError):
    pass


def _allowed_compatible_hosts() -> set[str]:
    return {
        host.strip().casefold().rstrip(".")
        for host in settings.llm_openai_compatible_allowed_hosts.split(",")
        if host.strip()
    }


def _validate_provider_host(*, provider: str, hostname: str, source: str) -> None:
    if source != "personal":
        return

    normalized_provider = str(getattr(provider, "value", provider)).casefold()
    expected_host = PROVIDER_HOSTS.get(normalized_provider)
    if expected_host is not None:
        if hostname != expected_host:
            raise LlmDestinationError(
                f"{normalized_provider} 仅允许使用 https://{expected_host}/v1。"
            )
        return

    if normalized_provider != "openai_compatible":
        raise LlmDestinationError("不支持的模型服务类型。")
    if hostname not in _allowed_compatible_hosts():
        raise LlmDestinationError(
            "该 OpenAI 兼容服务未被服务器管理员加入允许列表。"
        )


def _is_allowed_resolved_address(address: str, *, allow_proxy_fake_ip: bool) -> bool:
    parsed_address = ipaddress.ip_address(address)
    if parsed_address.is_global:
        return True
    return allow_proxy_fake_ip and any(
        parsed_address in network for network in PROXY_FAKE_IP_NETWORKS
    )


async def validate_llm_destination(
    *,
    base_url: str,
    provider: str,
    source: str,
) -> None:
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not hostname:
        raise LlmDestinationError("API Base URL 必须是有效的 HTTPS 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LlmDestinationError("API Base URL 不能包含账号、密码、查询参数或锚点。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise LlmDestinationError("API Base URL 端口无效。") from exc
    if port not in (None, 443):
        raise LlmDestinationError("模型 API 仅允许使用 HTTPS 默认端口 443。")

    _validate_provider_host(provider=provider, hostname=hostname, source=source)

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise LlmDestinationError("模型 API 地址不能指向本机、内网或保留地址。")
        return

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise LlmDestinationError("无法解析模型服务域名，请检查 API Base URL。") from exc

    resolved_ips = {item[4][0].split("%", 1)[0] for item in addresses}
    allow_proxy_fake_ip = bool(settings.llm_allow_proxy_fake_ip)
    if not resolved_ips or any(
        not _is_allowed_resolved_address(
            address,
            allow_proxy_fake_ip=allow_proxy_fake_ip,
        )
        for address in resolved_ips
    ):
        raise LlmDestinationError("模型 API 域名解析到了本机、内网或保留地址。")
