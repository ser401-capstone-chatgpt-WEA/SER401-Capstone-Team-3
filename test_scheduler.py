"""Local tests for scheduler behavior without production runtime."""

import json
import subprocess
import time

import pytest

import scheduler


def _read_status(path):
    return json.loads(path.read_text())


def test_update_job_status_writes_json_structure(monkeypatch, tmp_path):
    status_path = tmp_path / "scheduler_status.json"
    monkeypatch.setattr(scheduler, "_get_status_path", lambda: status_path)

    start_time = time.time() - 1
    scheduler._update_job_status("scraper", "success", start_time)

    payload = _read_status(status_path)
    assert "jobs" in payload
    assert "last_updated" in payload
    assert payload["jobs"]["scraper"]["status"] == "success"


def test_run_scraper_success_updates_status(monkeypatch, tmp_path):
    status_path = tmp_path / "scheduler_status.json"
    monkeypatch.setattr(scheduler, "_get_status_path", lambda: status_path)

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(scheduler.subprocess, "run", lambda *args, **kwargs: Result())

    scheduler.run_scraper()

    payload = _read_status(status_path)
    assert payload["jobs"]["scraper"]["status"] == "success"


def test_run_scraper_timeout_updates_error(monkeypatch, tmp_path):
    status_path = tmp_path / "scheduler_status.json"
    monkeypatch.setattr(scheduler, "_get_status_path", lambda: status_path)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python3", timeout=300)

    monkeypatch.setattr(scheduler.subprocess, "run", raise_timeout)

    scheduler.run_scraper()

    payload = _read_status(status_path)
    assert payload["jobs"]["scraper"]["status"] == "error"
    assert payload["jobs"]["scraper"]["error"] == "Timeout expired"


def test_run_rag_ingestion_failure_updates_error(monkeypatch, tmp_path):
    status_path = tmp_path / "scheduler_status.json"
    monkeypatch.setattr(scheduler, "_get_status_path", lambda: status_path)

    class Result:
        returncode = 1
        stdout = ""
        stderr = "ingestion failed"

    monkeypatch.setattr(scheduler.subprocess, "run", lambda *args, **kwargs: Result())

    scheduler.run_rag_ingestion()

    payload = _read_status(status_path)
    assert payload["jobs"]["ingestion"]["status"] == "error"


def test_main_wiring_adds_jobs_and_graceful_shutdown(monkeypatch):
    state = {"ids": [], "shutdown_called": False}

    class FakeBlockingScheduler:
        def __init__(self, *args, **kwargs):
            pass

        def add_job(self, func, trigger, id, **kwargs):
            state["ids"].append(id)

        def start(self):
            raise KeyboardInterrupt()

        def shutdown(self, wait=True):
            state["shutdown_called"] = True

    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeBlockingScheduler)
    monkeypatch.setattr(scheduler, "run_scraper", lambda: None)
    monkeypatch.setattr(scheduler, "run_rag_ingestion", lambda: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    def fake_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(scheduler.sys, "exit", fake_exit)

    with pytest.raises(SystemExit):
        scheduler.main()

    assert {"scraper", "ingestion", "cleanup"}.issubset(set(state["ids"]))
    assert state["shutdown_called"] is True
