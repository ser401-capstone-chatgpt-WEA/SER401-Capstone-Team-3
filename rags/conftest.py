"""Pytest configuration for RAGS tests."""
def pytest_addoption(parser):
    parser.addoption(
        "--run-llm-tests",
        action="store_true",
        default=False,
        help="Run LLM / integration tests that require GEMINI_API_KEY and external calls",
    )
