"""Resolve and pin outbound destinations. No proxy, redirect, userinfo or local-network bypass."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit
from .models import IntegrationError

async def public_destination(url):
    error = IntegrationError("unsafe_url", "The destination is not a public HTTPS endpoint.", "Use HTTPS on port 443 without credentials, query strings or fragments. Private and special-use addresses are blocked.")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query or parsed.fragment or "\\" in url:
            raise error
        host = parsed.hostname.encode("idna").decode("ascii")
        answers = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM), 5)
        addresses = {answer[4][0] for answer in answers}
        def unsafe(ip):
            address = ipaddress.ip_address(ip)
            return not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified
        if not addresses or any(unsafe(ip) for ip in addresses):
            raise error
        ip = sorted(addresses)[0]
        authority = f"[{ip}]" if ":" in ip else ip
        # The connection uses the vetted IP. Original Host and TLS SNI preserve certificate validation.
        return f"https://{authority}{parsed.path or '/'}", host
    except (ValueError, UnicodeError, OSError, asyncio.TimeoutError):
        raise error
