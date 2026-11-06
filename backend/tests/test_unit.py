import asyncio
import socket
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import pytest
from toolkit.connector import RestConnector
from toolkit.models import Config, Mapping, IntegrationError, normalize
from toolkit.security import public_destination

RAW = {"id": 42, "name": " Atlas ", "status": " PAID ", "amount": "12.345", "updated_at": "2026-01-01T14:00:00+02:00"}

def test_mapping_and_normalization():
    value = normalize({"order": RAW}, Mapping(**{f: "order." + f for f in RAW}))
    assert value == {"id": "42", "name": "Atlas", "status": "paid", "amount": 12.35, "updated_at": "2026-01-01T12:00:00+00:00"}

@pytest.mark.parametrize("field,value", [("id", None), ("id", True), ("name", {}), ("status", "  "), ("amount", "NaN"), ("amount", "inf"), ("amount", True), ("updated_at", "2026-01-01"), ("updated_at", "invalid")])
def test_bad_records_are_rejected(field, value):
    with pytest.raises(IntegrationError) as error:
        normalize({**RAW, field: value}, Mapping())
    assert error.value.code == "schema"

@pytest.mark.parametrize("url", ["http://example.com", "https://user:secret@example.com", "https://example.com:8443", "https://example.com/?token=secret", "https://example.com/#secret", "https://example.com\\@127.0.0.1"])
def test_url_shape_rejected(url):
    with pytest.raises(IntegrationError):
        asyncio.run(public_destination(url))

@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "0.0.0.0", "::1", "::ffff:127.0.0.1", "fc00::1", "224.0.0.1"])
def test_private_and_special_addresses_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])
    with pytest.raises(IntegrationError):
        asyncio.run(public_destination("https://api.example.com/orders"))


def test_dns_mixed_answers_blocked_and_public_address_pinned(monkeypatch):
    def answers(ips):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: answers(["8.8.8.8", "127.0.0.1"]))
    with pytest.raises(IntegrationError):
        asyncio.run(public_destination("https://api.example.com"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: answers(["8.8.8.8"]))
    assert asyncio.run(public_destination("https://api.example.com/orders")) == ("https://8.8.8.8/orders", "api.example.com")


def test_retry_after_and_long_wait():
    assert RestConnector.retry_delay("2", 0) == 2
    value = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=3))
    assert 1 <= RestConnector.retry_delay(value, 0) <= 3
    with pytest.raises(IntegrationError) as error:
        RestConnector.retry_delay("60", 0)
    assert error.value.code == "rate_limit_wait"
    assert .2 <= RestConnector.retry_delay("invalid", 0) <= .3

@pytest.mark.parametrize("payload,token", [({"items": [], "next_cursor": "next"}, None), ({"items": [RAW], "next_cursor": "a"}, "a"), ({"items": [RAW], "next_cursor": {}}, None), ({"items": {}}, None)])
def test_pagination_safeguards(payload, token):
    with pytest.raises(IntegrationError):
        RestConnector(Config(), None, "", "healthy", "unit").parse(payload, token)


def test_page_metadata_strict():
    with pytest.raises(IntegrationError):
        RestConnector(Config(pagination="page"), None, "", "healthy", "unit").parse({"items": [RAW], "has_more": "false"}, None)
