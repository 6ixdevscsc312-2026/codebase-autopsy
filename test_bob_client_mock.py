"""
Unit tests for BobClient mock mode (AUTOPSY_MOCK_BOB=1 / mock=True).

Focus: confirm that _mock_run correctly detects the docstring-vs-behavior
drift present in sample_repo/app/math_utils.py — a module that declares
"no side effects" in its docstring but writes files and logs at runtime.

Tests are grouped into three classes:
  - TestMockModeActivation      – how mock mode is enabled/disabled
  - TestDriftDetectionMathUtils – drift detected when math_utils.py is a file_ref
  - TestNoDriftFallback         – non-drifted source returns the low-score response
"""

from __future__ import annotations

import json
import os

import pytest

from autopsy.bob_client import BobClient, BobError, BobResult


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SAMPLE_REPO = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "sample_repo")
)
MATH_UTILS = os.path.join(SAMPLE_REPO, "app", "math_utils.py")


# ---------------------------------------------------------------------------
# TestMockModeActivation
# ---------------------------------------------------------------------------

class TestMockModeActivation:
    def test_explicit_mock_true_enables_mock(self):
        client = BobClient(mock=True)
        assert client.mock is True

    def test_env_var_enables_mock(self, monkeypatch):
        monkeypatch.setenv("AUTOPSY_MOCK_BOB", "1")
        client = BobClient()
        assert client.mock is True

    def test_env_var_absent_and_no_key_raises(self, monkeypatch):
        monkeypatch.delenv("AUTOPSY_MOCK_BOB", raising=False)
        monkeypatch.delenv("BOB_API_KEY", raising=False)
        with pytest.raises(BobError, match="BOB_API_KEY"):
            BobClient()

    def test_mock_run_returns_bob_result(self):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[MATH_UTILS])
        assert isinstance(result, BobResult)

    def test_mock_run_status_is_success(self):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[MATH_UTILS])
        assert result.status == "success"

    def test_mock_run_sets_total_tokens(self):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[MATH_UTILS])
        assert result.total_tokens is not None
        assert result.total_tokens > 0

    def test_mock_run_sets_session_cost(self):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[MATH_UTILS])
        assert result.session_cost is not None
        assert result.session_cost >= 0.0

    def test_mock_raw_contains_mock_flag(self):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[MATH_UTILS])
        assert result.raw == {"mock": True}


# ---------------------------------------------------------------------------
# TestDriftDetectionMathUtils
# ---------------------------------------------------------------------------

class TestDriftDetectionMathUtils:
    """math_utils.py claims 'No side effects, no I/O' but writes files and
    calls log_event — the mock heuristic must detect this as drift."""

    @pytest.fixture(autouse=True)
    def client(self):
        self._client = BobClient(mock=True)

    @pytest.fixture(autouse=True)
    def result(self, client):
        r = self._client.run(
            "Does this module's behavior match its docstring?",
            file_refs=[MATH_UTILS],
        )
        self._result = r
        self._verdict = json.loads(r.last_message)

    # --- last_message is valid JSON ----------------------------------------

    def test_last_message_is_valid_json(self):
        # json.loads would raise in the fixture if not; this makes the intent explicit
        assert isinstance(self._verdict, dict)

    # --- verdict shape -----------------------------------------------------

    def test_verdict_has_declared_purpose(self):
        assert "declared_purpose" in self._verdict

    def test_verdict_has_observed_behavior(self):
        assert "observed_behavior" in self._verdict

    def test_verdict_has_drift_score(self):
        assert "drift_score" in self._verdict

    def test_verdict_has_evidence(self):
        assert "evidence" in self._verdict

    # --- drift detection ---------------------------------------------------

    def test_drift_score_is_high(self):
        """Drift score must be > 5 for a clearly drifted module."""
        assert self._verdict["drift_score"] > 5

    def test_drift_score_in_valid_range(self):
        score = self._verdict["drift_score"]
        assert 0 <= score <= 10

    def test_declared_purpose_mentions_pure_or_no_side_effects(self):
        declared = self._verdict["declared_purpose"].lower()
        assert "pure" in declared or "no side effect" in declared or "side effect" in declared

    def test_observed_behavior_mentions_io(self):
        observed = self._verdict["observed_behavior"].lower()
        assert any(term in observed for term in ("i/o", "file", "write", "log", "disk"))

    def test_evidence_is_nonempty(self):
        assert len(self._verdict["evidence"]) > 0

    def test_evidence_mentions_file_write(self):
        evidence_text = " ".join(self._verdict["evidence"]).lower()
        assert any(
            term in evidence_text
            for term in ("open(", "write", "disk", "file", "json")
        )

    def test_evidence_mentions_logging(self):
        evidence_text = " ".join(self._verdict["evidence"]).lower()
        assert any(
            term in evidence_text
            for term in ("log", "logger", "log_event")
        )

    # --- idempotency -------------------------------------------------------

    def test_same_input_gives_same_drift_score(self):
        """Mock must be deterministic — same file_ref yields same verdict."""
        result2 = self._client.run(
            "Does this module's behavior match its docstring?",
            file_refs=[MATH_UTILS],
        )
        verdict2 = json.loads(result2.last_message)
        assert verdict2["drift_score"] == self._verdict["drift_score"]


# ---------------------------------------------------------------------------
# TestNoDriftFallback
# ---------------------------------------------------------------------------

class TestNoDriftFallback:
    """A file with no 'pure'/'no side effect' claim should produce the
    low-score non-drift response."""

    @pytest.fixture()
    def clean_file(self, tmp_path) -> str:
        """A module that makes no purity claims and performs no I/O."""
        p = tmp_path / "clean.py"
        p.write_text(
            "def add(a, b):\n"
            "    \"\"\"Return the sum.\"\"\"\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        return str(p)

    def test_no_drift_score_is_low(self, clean_file):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[clean_file])
        verdict = json.loads(result.last_message)
        assert verdict["drift_score"] <= 5

    def test_no_drift_evidence_is_empty(self, clean_file):
        client = BobClient(mock=True)
        result = client.run("analyze this", file_refs=[clean_file])
        verdict = json.loads(result.last_message)
        assert verdict["evidence"] == []

    def test_no_file_refs_gives_no_drift(self):
        """When no file_refs are passed there is no source to inspect — no drift."""
        client = BobClient(mock=True)
        result = client.run("analyze something")
        verdict = json.loads(result.last_message)
        assert verdict["drift_score"] <= 5

    def test_missing_file_ref_does_not_raise(self, tmp_path):
        """OSError on an unreadable ref is swallowed — result is still returned."""
        client = BobClient(mock=True)
        missing = str(tmp_path / "nonexistent.py")
        result = client.run("analyze this", file_refs=[missing])
        assert isinstance(result, BobResult)
        assert result.status == "success"
