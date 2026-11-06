"""A small real HTTP origin for hostile protocol/envelope edge cases."""
import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from toolkit.connector import RestConnector
from toolkit.models import Config, IntegrationError
from toolkit.storage import Store
from toolkit.sync import SyncService

@contextmanager
def origin(mode):
    class Handler(BaseHTTPRequestHandler):
        requests = 0
        def log_message(self, *args):
            pass
        def do_GET(self):
            Handler.requests += 1
            code, content_type = 200, "application/json"
            body = b'{"items": [], "next_cursor": null}'
            if mode == 'redirect':
                code = 302
            elif mode == 'oversized':
                body = b'x' * (2 * 1024 * 1024 + 1)
            elif mode == 'html':
                content_type, body = 'text/html', b'<html>Login page</html>'
            elif mode == 'loop':
                token = str(Handler.requests)
                body = json.dumps({"items": [{"id": "1", "name": "Same page", "status": "paid", "amount": 2, "updated_at": "2026-01-01T00:00:00Z"}], "next_cursor": token}).encode()
            elif mode == 'long_wait':
                code = 429
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            if mode == 'redirect':
                self.send_header('Location', 'http://169.254.169.254/latest/meta-data')
            if mode == 'long_wait':
                self.send_header('Retry-After', '60')
            if mode == 'compressed':
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

@pytest.mark.parametrize('mode,code', [('redirect','redirect'), ('oversized','response_limit'), ('html','invalid_json'), ('long_wait','rate_limit_wait'), ('compressed','content_encoding')])
def test_actual_http_boundary_errors_do_not_retry_or_follow(mode, code):
    with origin(mode) as (url, handler):
        connector = RestConnector(Config(), None, url, 'healthy', 'boundary')
        with pytest.raises(IntegrationError) as error:
            asyncio.run(connector.fetch())
        assert error.value.code == code
        assert handler.requests == 1


def test_changing_cursor_with_identical_page_is_rejected_before_commit(tmp_path):
    async def run(url):
        store = Store(tmp_path / 'loop.db')
        service = SyncService(store, url)
        run_id = service.start('healthy')
        await service.task
        result = store.run(run_id)
        assert result['status'] == 'failed'
        assert result['error'] == 'pagination'
        assert result['pages'] == 1
        assert store.records()['total'] == 1
        assert store.config()['watermark'] is None
    with origin('loop') as (url, _):
        asyncio.run(run(url))
