"""Tests for :class:`backend.metrics.kl_metrics.KLMetrics` and the
``/api/kl/metrics`` HTTP endpoint.

Covers
------
- Default counter / gauge / histogram state is zero
- :meth:`KLMetrics.inc` increments known counters and ignores unknown ones
- :meth:`KLMetrics.set_stage_counts` populates the gauge with all 5 stages
- :meth:`KLMetrics.observe` appends samples to a bounded ring buffer
- :meth:`KLMetrics.snapshot` returns a JSON-serialisable dict with the
  expected shape (counters / gauges / histograms)
- The HTTP endpoint returns the same snapshot when no items are in the DB
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.kl_metrics_api import router as kl_router
from backend.config import config
from backend.metrics.kl_metrics import (
    ALL_STAGES,
    COUNTER_KEYS,
    HISTOGRAM_KEYS,
    KLMetrics,
    kl_metrics,
)
from backend.repository import db as db_module


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_kl_metrics.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    yield test_db
    db_module.close_db()


# ---------------------------------------------------------------------------
# Counter / gauge / histogram unit tests
# ---------------------------------------------------------------------------

class TestCounters:
    def test_defaults_all_zero(self):
        m = KLMetrics()
        snap = m.snapshot()
        for key in COUNTER_KEYS:
            assert snap["counters"][key] == 0

    def test_inc_increments_known_counter(self):
        m = KLMetrics()
        m.inc("t1_succeeded")
        m.inc("t1_succeeded", n=4)
        assert m.counter_value("t1_succeeded") == 5

    def test_inc_unknown_is_noop(self):
        m = KLMetrics()
        m.inc("not_a_counter")  # no exception
        snap = m.snapshot()
        assert "not_a_counter" not in snap["counters"]

    def test_reset_counters(self):
        m = KLMetrics()
        m.inc("t1_succeeded", n=10)
        m.reset_counters()
        assert m.counter_value("t1_succeeded") == 0


class TestStageGauge:
    def test_set_stage_counts_populates_all_stages(self):
        m = KLMetrics()
        m.set_stage_counts({
            "kl:raw": 7,
            "kl:refine": 3,
            "kl:link": 1,
            # kl:structure and kl:publish intentionally missing
        })
        snap = m.snapshot()
        counts = snap["gauges"]["by_stage_count"]
        assert counts["kl:raw"] == 7
        assert counts["kl:refine"] == 3
        assert counts["kl:link"] == 1
        assert counts["kl:structure"] == 0
        assert counts["kl:publish"] == 0

    def test_set_stage_counts_replaces_previous(self):
        m = KLMetrics()
        m.set_stage_counts({"kl:raw": 5})
        m.set_stage_counts({"kl:refine": 2})
        assert m.stage_count("kl:raw") == 0
        assert m.stage_count("kl:refine") == 2

    def test_set_stage_counts_ignores_unknown_stages(self):
        m = KLMetrics()
        m.set_stage_counts({"kl:raw": 1, "kl:bogus": 99})
        assert m.stage_count("kl:raw") == 1
        assert m.stage_count("kl:bogus") == 0  # not added to gauge


class TestHistograms:
    def test_default_empty(self):
        m = KLMetrics()
        snap = m.snapshot()
        for key in HISTOGRAM_KEYS:
            assert snap["histograms"][key]["count"] == 0
            assert snap["histograms"][key]["avg"] == 0.0

    def test_observe_appends(self):
        m = KLMetrics()
        m.observe("t1_latency_ms", 10.0)
        m.observe("t1_latency_ms", 20.0)
        m.observe("t1_latency_ms", 30.0)
        snap = m.snapshot()
        h = snap["histograms"]["t1_latency_ms"]
        assert h["count"] == 3
        assert h["avg"] == pytest.approx(20.0)
        assert h["p50"] == 20.0
        assert h["p99"] == 30.0  # only 3 samples → 3rd (last)

    def test_observe_unknown_noop(self):
        m = KLMetrics()
        m.observe("not_a_histogram", 1.0)  # no exception
        snap = m.snapshot()
        assert "not_a_histogram" not in snap["histograms"]

    def test_histogram_ring_buffer_bounded(self):
        m = KLMetrics()
        # Bounded at 100; the 101st value should evict the oldest.
        for i in range(150):
            m.observe("t1_latency_ms", float(i))
        snap = m.snapshot()
        # Only the most recent 100 samples are kept.
        assert snap["histograms"]["t1_latency_ms"]["count"] == 100


# ---------------------------------------------------------------------------
# HTTP endpoint smoke test
# ---------------------------------------------------------------------------

class TestKLMetricsEndpoint:
    @pytest.fixture
    def client(self, temp_db) -> TestClient:
        app = FastAPI()
        app.include_router(kl_router)
        return TestClient(app)

    def test_metrics_endpoint_returns_snapshot(self, client):
        resp = client.get("/api/kl/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "counters" in data
        assert "gauges" in data
        assert "histograms" in data
        # Default state: all 8 counters at 0, all 5 stage counts at 0
        for key in COUNTER_KEYS:
            assert data["counters"][key] == 0
        for stage in ALL_STAGES:
            assert data["gauges"]["by_stage_count"][stage] == 0

    def test_counters_endpoint(self, client):
        resp = client.get("/api/kl/metrics/counters")
        assert resp.status_code == 200
        data = resp.json()
        assert "t1_succeeded" in data
        assert "t2_dead_letter" in data

    def test_health_endpoint(self, client):
        resp = client.get("/api/kl/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "counters" in data
        assert "stages" in data


# ---------------------------------------------------------------------------
# Singleton — keep the shared instance usable.
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_module_singleton_is_usable(self):
        # Reset before checking
        kl_metrics.reset_counters()
        kl_metrics.inc("t1_succeeded", n=2)
        assert kl_metrics.counter_value("t1_succeeded") >= 2
