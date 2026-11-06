"""Exercise actual TLS with a pinned IP, original SNI/Host and session authentication."""
import asyncio
import json
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx
import pytest
import toolkit.connector as module
from toolkit.models import Config, IntegrationError

@pytest.fixture
def tls_origin(tmp_path, monkeypatch):
    cert, key = tmp_path / 'test.crt', tmp_path / 'test.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=api.example.test', '-addext', 'subjectAltName=DNS:api.example.test'], check=True, capture_output=True)
    received, server_names = [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            received.append(dict(self.headers))
            body = json.dumps({'items': [], 'next_cursor': None}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    context.set_servername_callback(lambda sock, name, ctx: server_names.append(name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    async def pinned(url):
        assert url == 'https://api.example.test/orders'
        return f'https://127.0.0.1:{server.server_port}/orders', 'api.example.test'
    monkeypatch.setattr(module, 'public_destination', pinned)
    real_client = httpx.AsyncClient
    trust = ssl.create_default_context(cafile=str(cert))
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: real_client(verify=trust, **kwargs))
    try:
        yield received, server_names
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

@pytest.mark.parametrize('auth,header,value', [('none',None,None), ('bearer','Authorization','Bearer session-only-secret'), ('api_key','X-API-Key','session-only-secret')])
def test_custom_https_auth_preserves_hostname_validation(tls_origin, auth, header, value):
    received, names = tls_origin
    connector = module.RestConnector(Config(source='custom', url='https://api.example.test/orders', auth=auth), 'session-only-secret', '', 'healthy', 'tls')
    page = asyncio.run(connector.fetch())
    assert page.records == [] and page.next_token is None
    assert names == ['api.example.test']
    assert received[0]['Host'] == 'api.example.test'
    if header:
        assert received[0][header] == value
    else:
        assert 'Authorization' not in received[0] and 'X-API-Key' not in received[0]


def test_missing_session_credentials_never_reach_upstream(tls_origin):
    received, _ = tls_origin
    connector = module.RestConnector(Config(source='custom', url='https://api.example.test/orders', auth='bearer'), None, '', 'healthy', 'tls')
    with pytest.raises(IntegrationError) as error:
        asyncio.run(connector.fetch())
    assert error.value.code == 'credentials'
    assert received == []
