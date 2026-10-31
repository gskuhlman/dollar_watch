import pytest


@pytest.fixture(autouse=True)
def _isolated_policy_cache(tmp_path, monkeypatch):
    """Keep tests off the real data/official_policy_cache.json.

    Tests that mock official pages would otherwise write fake text into the live cache, and
    tests of the packaged seed would depend on whether a real run had cached that URL.
    """
    monkeypatch.setenv("DOLLAR_POLICY_CACHE", str(tmp_path / "official_policy_cache.json"))
