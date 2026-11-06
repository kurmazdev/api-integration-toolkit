import csv
import io
import json
import time
import httpx
import pytest
from openpyxl import load_workbook
from conftest import HEADERS, server, start, wait_run


def test_preview_is_read_only_and_sync_is_idempotent(client):
    preview = client.post("/api/preview", json={}).json()
    assert len(preview["items"]) == 5
    assert preview["items"][0]["status"] == "paid"
    assert client.get("/api/records").json()["total"] == 0
    first = wait_run(client, start(client), "completed")
    assert (first["inserted"], first["pages"], first["seen"]) == (23, 5, 23)
    second = wait_run(client, start(client, full=True), "completed")
    assert (second["inserted"], second["unchanged"]) == (0, 23)
    assert client.get("/api/records").json()["total"] == 23

@pytest.mark.parametrize("pagination", ["cursor", "page", "offset"])
def test_pagination_styles(client, pagination):
    config = client.get("/api/settings").json()["config"]
    config["pagination"] = pagination
    assert client.put("/api/settings", json={"config": config}).status_code == 200
    run = wait_run(client, start(client), "completed")
    assert run["seen"] == 23

@pytest.mark.parametrize("scenario,code,pages", [("malformed", "invalid_json", 1), ("incomplete", "schema", 1), ("pagination", "pagination", 1), ("expired_auth", "authentication", 0)])
def test_bad_pages_rollback_then_resume(client, scenario, code, pages):
    run_id = start(client, scenario)
    broken = wait_run(client, run_id, "failed")
    assert broken["error"] == code
    assert broken["pages"] == pages
    assert broken["retries"] == 0
    assert client.get("/api/records").json()["total"] == 5 * pages
    assert client.get("/api/settings").json()["watermark"] is None
    assert client.post(f"/api/runs/{run_id}/resume", json={"scenario": "healthy"}).status_code == 202
    fixed = wait_run(client, run_id, "completed")
    assert fixed["inserted"] == 23
    assert fixed["pages"] == 5
    assert client.get("/api/records").json()["total"] == 23
    assert client.get("/api/settings").json()["watermark"] is not None
    assert any(e["code"] == code for e in fixed["events"])

@pytest.mark.parametrize("scenario,retries", [("server_error", 8), ("rate_limit", 4), ("timeout", 4)])
def test_transient_failures_use_real_http_retries(client, scenario, retries):
    config = client.get("/api/settings").json()["config"]
    config["timeout"] = .15
    client.put("/api/settings", json={"config": config})
    run = wait_run(client, start(client, scenario), "completed")
    assert run["retries"] == retries
    assert run["inserted"] == 23
    assert len([e for e in run["events"] if e["code"] == "retry"]) == retries


def test_retry_exhaustion_is_resumable(client):
    config = client.get("/api/settings").json()["config"]
    config["retries"] = 1
    client.put("/api/settings", json={"config": config})
    run_id = start(client, "server_error")
    failed = wait_run(client, run_id, "failed")
    assert failed["error"] == "server_error"
    assert failed["pages"] == 1
    client.post(f"/api/runs/{run_id}/resume", json={"scenario": "healthy"})
    assert wait_run(client, run_id, "completed")["inserted"] == 23


def test_duplicates_inside_and_between_pages(client):
    run = wait_run(client, start(client, "duplicates"), "completed")
    assert (run["seen"], run["inserted"], run["unchanged"]) == (25, 23, 2)
    assert client.get("/api/records").json()["total"] == 23


def test_incremental_updates_inclusive_boundary(client, upstream):
    wait_run(client, start(client), "completed")
    replay = wait_run(client, start(client), "completed")
    assert replay["seen"] == 1 and replay["unchanged"] == 1
    assert client.post("/api/demo/revision").status_code == 200
    run = wait_run(client, start(client), "completed")
    assert (run["seen"], run["inserted"], run["updated"], run["unchanged"]) == (3, 1, 1, 1)
    assert client.get("/api/records").json()["total"] == 24
    assert client.get("/api/records").json()["items"][0]["amount"] == 199.95


def test_cancellation_preserves_checkpoint(client):
    run_id = start(client, "slow")
    for _ in range(100):
        if client.get("/api/runs/" + run_id).json()["pages"] >= 1:
            break
        time.sleep(.02)
    assert client.post("/api/runs", json={}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/stop").status_code == 200
    stopped = wait_run(client, run_id, "cancelled")
    assert 1 <= stopped["pages"] < 5
    assert client.get("/api/settings").json()["watermark"] is None
    client.post(f"/api/runs/{run_id}/resume", json={"scenario": "healthy"})
    finished = wait_run(client, run_id, "completed")
    assert finished["inserted"] == 23 and finished["pages"] == 5


def test_exports_only_mapped_fields_and_safe_spreadsheet_cells(client):
    wait_run(client, start(client), "completed")
    db = client.app.state.store
    with db.db() as connection:
        record = json.loads(connection.execute("SELECT data FROM records WHERE id='ORD-0001'").fetchone()[0])
        record["name"] = "  =HYPERLINK(\"https://example.com\")"
        connection.execute("UPDATE records SET data=? WHERE id='ORD-0001'", (json.dumps(record),))
    csv_response = client.get("/api/export/csv")
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert len(rows) == 23
    assert set(rows[0]) == {"id", "name", "status", "amount", "updated_at"}
    assert rows[0]["name"].startswith("'")
    xlsx = load_workbook(io.BytesIO(client.get("/api/export/xlsx").content))
    assert xlsx.active.max_row == 24
    assert xlsx.active["B2"].data_type == "s"
    assert xlsx.active["B2"].value.startswith("'")
    assert "local-demo-token" not in str(db.run(client.get('/api/runs').json()[0]['id']))
    with db.db() as connection:
        assert "internal_note" not in connection.execute("SELECT data FROM records LIMIT 1").fetchone()[0]
        assert "local-demo-token" not in str([tuple(r) for r in connection.execute("SELECT * FROM runs")])


def test_config_frozen_and_only_latest_run_resumes(client):
    first = start(client, "malformed")
    wait_run(client, first, "failed")
    config = client.get("/api/settings").json()["config"]
    config["page_size"] = 10
    assert client.put("/api/settings", json={"config": config}).status_code == 422
    wait_run(client, start(client), "completed")
    assert client.post(f"/api/runs/{first}/resume", json={}).status_code == 409
    assert client.post('/api/reset').status_code == 200
    assert client.get('/api/records').json()['total'] == 0
    assert client.put("/api/settings", json={"config": config}).status_code == 200


def test_security_boundaries_and_redaction(client):
    assert client.post('/api/reset', headers={"X-Toolkit-Request": ""}).status_code == 403
    assert client.post('/api/reset', headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get('/api/settings', headers={"Host": "evil.example"}).status_code == 400
    config = client.get('/api/settings').json()['config']
    response = client.put('/api/settings', json={"config": {**config, "page_size": -1}, "credential": "top-secret"})
    assert response.status_code == 422 and 'top-secret' not in response.text
    config.update(source="custom", url="http://169.254.169.254/latest")
    assert client.put('/api/settings', json={"config": config}).json()['code'] == 'unsafe_url'


def test_live_api_process_kill_restart_and_resume(tmp_path, upstream):
    env = {"TOOLKIT_DB": str(tmp_path / "restart.db"), "DEMO_URL": upstream}
    httpx.post(upstream + "/reset", trust_env=False)
    with server("toolkit.api:create_app", env) as (url, process):
        with httpx.Client(base_url=url, headers=HEADERS, trust_env=False) as c:
            run_id = start(c, "slow")
            for _ in range(100):
                run = c.get('/api/runs/' + run_id).json()
                if run['pages'] >= 1:
                    break
                time.sleep(.02)
            assert run['pages'] == 1 and run['status'] == 'running'
            process.kill()
            process.wait(timeout=5)
    with server("toolkit.api:create_app", env) as (url, _):
        with httpx.Client(base_url=url, headers=HEADERS, trust_env=False) as c:
            interrupted = c.get('/api/runs/' + run_id).json()
            assert interrupted['status'] == 'interrupted'
            assert interrupted['pages'] == 1
            assert c.get('/api/records').json()['total'] == 5
            c.post(f'/api/runs/{run_id}/resume', json={"scenario": "healthy"})
            result = wait_run(c, run_id, "completed")
            assert (result['inserted'], result['pages']) == (23, 5)
            assert len(list(csv.DictReader(io.StringIO(c.get('/api/export/csv').content.decode('utf-8-sig'))))) == 23
