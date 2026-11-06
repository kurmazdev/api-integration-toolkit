import asyncio
import hashlib
import json
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Protocol
import httpx
from .models import Config, IntegrationError, get_path, normalize
from .security import public_destination

MAX_BYTES = 2 * 1024 * 1024

@dataclass
class Page:
    records: list
    next_token: object
    fingerprint: str

class Connector(Protocol):
    async def fetch(self, token=None, since=None) -> Page:
        """Return a fully validated page, opaque continuation and content fingerprint."""
        ...

class RestConnector:
    def __init__(self, config: Config, credential, demo_url, scenario, run_id, event=None):
        self.config, self.credential, self.demo_url = config, credential, demo_url
        self.scenario, self.run_id, self.event = scenario, run_id, event

    async def fetch(self, token=None, since=None):
        c = self.config
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        extensions = {}
        if c.source == "demo":
            url = self.demo_url + "/orders"
            headers.update({"X-Demo-Run": self.run_id, "Authorization": "Bearer local-demo-token"})
        else:
            url, host = await public_destination(c.url)
            headers["Host"] = host
            extensions["sni_hostname"] = host
            if c.auth != "none":
                if not self.credential:
                    raise IntegrationError("credentials", "Credentials are missing from this session.", "Enter a fresh credential in connection settings, save, then resume.")
                headers["Authorization" if c.auth == "bearer" else "X-API-Key"] = ("Bearer " if c.auth == "bearer" else "") + self.credential
        params = {"limit": c.page_size}
        if c.source == "demo":
            params.update(scenario=self.scenario, pagination=c.pagination)
        if since:
            params["updated_since"] = since
        key = {"cursor": "cursor", "page": "page", "offset": "offset"}[c.pagination]
        params[key] = token if token is not None else (1 if c.pagination == "page" else 0)
        async with httpx.AsyncClient(timeout=c.timeout, follow_redirects=False, trust_env=False) as client:
            for attempt in range(c.retries + 1):
                try:
                    # Wall deadline also bounds slow trickles, not just per-read inactivity.
                    status, response_headers, body = await asyncio.wait_for(self._request(client, url, headers, params, extensions), timeout=c.timeout + 0.1)
                    if status == 429 or status >= 500:
                        code = "rate_limit" if status == 429 else "server_error"
                        error = IntegrationError(code, f"Upstream returned HTTP {status}.", "Retry or resume later. Committed pages are safe.")
                        delay = self.retry_delay(response_headers.get("retry-after"), attempt)
                    elif status in (401, 403):
                        raise IntegrationError("authentication", f"Upstream rejected authentication (HTTP {status}).", "Refresh credentials, save them, then resume. Authentication failures are not retried.")
                    elif 300 <= status < 400:
                        raise IntegrationError("redirect", "Upstream returned a redirect, which was blocked.", "Configure the final public HTTPS endpoint directly.")
                    elif status != 200:
                        raise IntegrationError("http_error", f"Upstream returned HTTP {status}.", "Check endpoint, permissions and pagination parameters.")
                    else:
                        if "application/json" not in response_headers.get("content-type", "").lower():
                            raise IntegrationError("invalid_json", "Upstream did not return JSON content.", "Check the endpoint and API response format.")
                        try:
                            payload = json.loads(body)
                        except (ValueError, UnicodeError, RecursionError):
                            raise IntegrationError("invalid_json", "Upstream returned malformed JSON.", "Inspect the upstream serializer. Resume after the response is corrected.")
                        return self.parse(payload, token)
                except (httpx.TransportError, asyncio.TimeoutError):
                    error = IntegrationError("timeout", "The upstream request timed out or could not connect.", "Check connectivity and timeout settings. Resume to retry this page.")
                    delay = self.retry_delay(None, attempt)
                if attempt == c.retries:
                    raise error
                if self.event:
                    self.event("warning", "retry", f"{error.message} Retry {attempt + 1}/{c.retries} in {delay:.1f}s.")
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _request(self, client, url, headers, params, extensions):
        async with client.stream("GET", url, headers=headers, params=params, extensions=extensions) as response:
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise IntegrationError("content_encoding", "The API ignored the uncompressed response requirement.", "Configure the upstream to honor Accept-Encoding: identity. Compressed responses are refused to bound decoded memory use.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise IntegrationError("response_limit", "Response exceeded the 2 MiB limit.", "Reduce page size or choose a smaller response envelope.")
            return response.status_code, response.headers, bytes(body)

    @staticmethod
    def retry_delay(value, attempt):
        import random
        if value:
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = -1
            if delay > 10:
                raise IntegrationError("rate_limit_wait", "Upstream requested a retry wait longer than 10 seconds.", "Resume later; the server's Retry-After is not shortened.")
            if delay >= 0:
                return delay
        return min(0.2 * 2 ** attempt + random.uniform(0, 0.1), 5)

    def parse(self, payload, token):
        c = self.config
        raw = get_path(payload, c.items_path)
        if not isinstance(raw, list) or len(raw) > c.page_size:
            raise IntegrationError("schema", "The items field is not a bounded list.", "Check the items path and whether the API respects limit.")
        rows = [normalize(r, c.mapping) for r in raw]
        if c.pagination == "cursor":
            next_token = get_path(payload, c.cursor_path)
            if next_token is not None and (isinstance(next_token, bool) or not isinstance(next_token, (str, int)) or len(str(next_token)) > 500):
                raise IntegrationError("pagination", "The next cursor is invalid.", "Return a scalar cursor, or null at the end.")
            if next_token is not None and str(next_token) == str(token):
                raise IntegrationError("pagination", "The API repeated its current cursor.", "Pagination did not advance. Fix the upstream next_cursor implementation, then resume.")
        else:
            more = get_path(payload, c.more_path)
            if not isinstance(more, bool):
                raise IntegrationError("pagination", "has_more must be a boolean.", "Map the correct pagination metadata field.")
            next_token = ((token or 1) + 1 if c.pagination == "page" else (token or 0) + c.page_size) if more else None
        if not rows and next_token is not None:
            raise IntegrationError("pagination", "An empty page advertised more data.", "Fix upstream pagination metadata to prevent an infinite loop.")
        fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        return Page(rows, next_token, fingerprint)
