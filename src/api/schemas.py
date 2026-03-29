"""Pydantic request/response schemas for the Gridalytics API."""

from datetime import datetime, date
from pydantic import BaseModel, Field


# --- Auth ---

class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str | None = None

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str


# --- Forecast ---

class ForecastResponse(BaseModel):
    timestamps: list[str]
    predicted_mw: list[float]
    lower_bound_mw: list[float]
    upper_bound_mw: list[float]
    model_name: str
    model_version: str = "v2.0"
    resolution: str
    region: str = "delhi"
    metadata: dict = {}

class WhatIfRequest(BaseModel):
    date: str
    resolution: str = "hourly"
    overrides: dict = Field(default_factory=dict)
    # overrides can contain: temperature, humidity, is_holiday, aqi


# --- Dashboard ---

class LiveDashboardResponse(BaseModel):
    current_demand_mw: float | None
    timestamp: str | None
    forecast_1h_mw: float | None
    forecast_1h_lower: float | None
    forecast_1h_upper: float | None
    weather: dict = {}
    today_peak_mw: float | None
    today_peak_time: str | None
    vs_yesterday_pct: float | None

class SummaryStatsResponse(BaseModel):
    today: dict
    yesterday: dict
    this_week_avg: float | None
    last_week_avg: float | None
    season: str
    demand_trend: str

class ModelPerformanceResponse(BaseModel):
    champion: dict
    models_available: list[str]

class HeatmapResponse(BaseModel):
    hours: list[int]
    days: list[str]
    values: list[list[float]]

class AnomalyItem(BaseModel):
    timestamp: str
    actual_mw: float
    predicted_mw: float
    deviation_pct: float
    severity: str

class AnomalyResponse(BaseModel):
    anomalies: list[AnomalyItem]


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    models_loaded: int
    database: str
    demand_latest: str | None
    weather_latest: str | None
