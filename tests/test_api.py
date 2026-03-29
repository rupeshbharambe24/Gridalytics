"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    from src.api.main import app
    return TestClient(app)


class TestHealthEndpoints:
    def test_health_ready(self, client):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "models_loaded" in data
        assert data["database"] == "connected"


class TestAuthEndpoints:
    def test_register(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "test_api@gridalytics.com",
            "password": "testpass123",
            "full_name": "Test API User",
        })
        # May succeed or fail if user already exists
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            data = resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login(self, client):
        # Register first
        client.post("/api/v1/auth/register", json={
            "email": "test_login@gridalytics.com",
            "password": "testpass123",
        })

        resp = client.post("/api/v1/auth/login", json={
            "email": "test_login@gridalytics.com",
            "password": "testpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    def test_login_wrong_password(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "test_login@gridalytics.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestDashboardEndpoints:
    def test_live(self, client):
        resp = client.get("/api/v1/dashboard/live")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_demand_mw" in data
        assert "weather" in data

    def test_historical(self, client):
        resp = client.get("/api/v1/dashboard/historical?days=7&resolution=hourly")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamps" in data
        assert "demand_mw" in data

    def test_stats_summary(self, client):
        resp = client.get("/api/v1/dashboard/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "season" in data
        assert "demand_trend" in data

    def test_heatmap(self, client):
        resp = client.get("/api/v1/dashboard/heatmap?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["hours"]) == 24
        assert len(data["days"]) == 7

    def test_prediction_history(self, client):
        resp = client.get("/api/v1/dashboard/prediction-history?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "summary" in data

    def test_accuracy_trend(self, client):
        resp = client.get("/api/v1/dashboard/accuracy-trend?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "drift_status" in data

    def test_seasonal_stats(self, client):
        resp = client.get("/api/v1/dashboard/stats/seasonal")
        assert resp.status_code == 200
        data = resp.json()
        assert "seasons" in data

    def test_model_performance(self, client):
        resp = client.get("/api/v1/dashboard/model-performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "champion" in data
        assert "models_available" in data


class TestForecastEndpoints:
    def test_available_models(self, client):
        resp = client.get("/api/v1/forecast/models/available")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_forecast_historical_date(self, client):
        """Test forecast for a date where we have data."""
        resp = client.get("/api/v1/forecast/hourly?date=2026-03-20")
        assert resp.status_code in (200, 404, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert "predicted_mw" in data
            assert "timestamps" in data
            assert len(data["predicted_mw"]) > 0

    def test_forecast_invalid_resolution(self, client):
        resp = client.get("/api/v1/forecast/invalid?date=2026-03-20")
        assert resp.status_code == 400

    def test_forecast_invalid_date(self, client):
        resp = client.get("/api/v1/forecast/hourly?date=not-a-date")
        assert resp.status_code in (400, 503)  # 503 if no model loaded in test env

    def test_what_if(self, client):
        resp = client.post("/api/v1/forecast/what-if", json={
            "date": "2026-03-20",
            "resolution": "hourly",
            "overrides": {"temperature": 40.0},
        })
        assert resp.status_code in (200, 404, 503)


class TestAdminEndpoints:
    def test_admin_models(self, client):
        resp = client.get("/api/v1/admin/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))  # may be wrapped in {"models": [...]}

    def test_scraper_status(self, client):
        resp = client.get("/api/v1/admin/scraper-status")
        assert resp.status_code == 200

    def test_scheduler_jobs(self, client):
        resp = client.get("/api/v1/admin/scheduler-jobs")
        assert resp.status_code == 200
