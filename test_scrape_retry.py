"""Unit tests for scraper retry/backoff behavior."""

import json
import unittest
from unittest.mock import patch

import requests

from scrape_pbs_warn_api import fetch_alerts_api, RETRY_MAX_ATTEMPTS


class _FakeResponse:
    def __init__(self, status_code, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}
        self.text = json.dumps(self._json_data)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Error",
                response=self
            )


class TestScraperRetry(unittest.TestCase):
    @patch("scrape_pbs_warn_api.time.sleep", return_value=None)
    @patch("scrape_pbs_warn_api.random.uniform", return_value=0.0)
    @patch("scrape_pbs_warn_api.requests.get")
    def test_retry_after_backoff_used(self, mock_get, _mock_uniform, mock_sleep):
        mock_get.side_effect = [
            _FakeResponse(503, headers={"Retry-After": "3"}),
            _FakeResponse(
                200,
                json_data={"alerts": [], "pages": {"page": 1, "pages": 1}}
            ),
        ]

        with self.assertLogs(level="INFO") as log_ctx:
            fetch_alerts_api(fetch_all_pages=False)

        logs = "\n".join(log_ctx.output)
        self.assertIn("Attempt 1/5 fetching page 1", logs)
        self.assertIn("Retrying in 3.0s.", logs)
        self.assertIn("Attempt 2/5 succeeded for page 1", logs)
        mock_sleep.assert_called_once_with(3.0)

    @patch("scrape_pbs_warn_api.time.sleep", return_value=None)
    @patch("scrape_pbs_warn_api.random.uniform", return_value=0.0)
    @patch("scrape_pbs_warn_api.requests.get")
    def test_network_error_backoff(self, mock_get, _mock_uniform, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.Timeout("timeout"),
            _FakeResponse(
                200,
                json_data={"alerts": [], "pages": {"page": 1, "pages": 1}}
            ),
        ]

        with self.assertLogs(level="WARNING") as log_ctx:
            fetch_alerts_api(fetch_all_pages=False)

        logs = "\n".join(log_ctx.output)
        self.assertIn("Attempt 1 failed for page 1", logs)
        self.assertIn("Retrying in 1.0s.", logs)
        mock_sleep.assert_called_once_with(1.0)

    @patch("scrape_pbs_warn_api.time.sleep", return_value=None)
    @patch("scrape_pbs_warn_api.random.uniform", return_value=0.0)
    @patch("scrape_pbs_warn_api.requests.get")
    def test_final_attempt_logs_error(self, mock_get, _mock_uniform, mock_sleep):
        mock_get.side_effect = [
            _FakeResponse(503, headers={"Retry-After": "1"})
            for _ in range(RETRY_MAX_ATTEMPTS)
        ]

        with self.assertLogs(level="ERROR") as log_ctx:
            with self.assertRaises(requests.exceptions.HTTPError):
                fetch_alerts_api(fetch_all_pages=False)

        logs = "\n".join(log_ctx.output)
        self.assertIn("Final attempt failed for page 1 with status 503.", logs)
        self.assertEqual(mock_sleep.call_count, RETRY_MAX_ATTEMPTS - 1)


if __name__ == "__main__":
    unittest.main()
