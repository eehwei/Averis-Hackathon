import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_api: hits a real external API - exempt from the deterministic-classifier override",
    )


@pytest.fixture(autouse=True)
def _deterministic_classifier_by_default(request, monkeypatch):
    """Force sdoc_pipeline.classify_with_fallback() off the live LLM path.

    Full-inbox tests that don't inject their own classifier used to fall
    through to a real Groq API call per email whenever SDOC_CLASSIFIER=llm
    was set in .env, turning a sub-second test into a ~2 hour run. Tests that
    actually want the live API opt out with @pytest.mark.live_api.
    """
    if request.node.get_closest_marker("live_api") is not None:
        return
    monkeypatch.delenv("SDOC_CLASSIFIER", raising=False)
