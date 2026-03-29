"""Tests for data scrapers."""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from src.data.scrapers.sldc import SLDCScraper
from src.data.scrapers.open_meteo import OpenMeteoScraper
from src.data.scrapers.aqi import AQIScraper
from src.data.scrapers.holidays import HolidayScraper


class TestSLDCScraper:
    def test_init(self):
        scraper = SLDCScraper()
        assert scraper.name == "sldc"
        assert scraper.rate_limit_delay == 1.0

    def test_validate_drops_nulls(self):
        import pandas as pd
        scraper = SLDCScraper()
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "delhi_mw": [3000.0, None, 4000.0],
            "brpl_mw": [1000, 1000, 1000],
            "bypl_mw": [500, 500, 500],
            "ndpl_mw": [800, 800, 800],
            "ndmc_mw": [100, 100, 100],
            "mes_mw": [50, 50, 50],
        })
        result = scraper.validate(df)
        assert len(result) == 2  # null row dropped

    def test_validate_drops_unreasonable(self):
        import pandas as pd
        scraper = SLDCScraper()
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
            "delhi_mw": [3000.0, 50000.0],  # 50000 is too high
            "brpl_mw": [1000, 1000],
            "bypl_mw": [500, 500],
            "ndpl_mw": [800, 800],
            "ndmc_mw": [100, 100],
            "mes_mw": [50, 50],
        })
        result = scraper.validate(df)
        assert len(result) == 1


class TestOpenMeteoScraper:
    def test_init(self):
        scraper = OpenMeteoScraper()
        assert scraper.name == "open_meteo"

    def test_validate_clamps_humidity(self):
        import pandas as pd
        scraper = OpenMeteoScraper()
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-01")],
            "temperature_2m": [25.0],
            "relative_humidity_2m": [120.0],  # > 100
        })
        result = scraper.validate(df)
        assert result["relative_humidity_2m"].iloc[0] == 100


class TestAQIScraper:
    def test_init(self):
        scraper = AQIScraper()
        assert scraper.name == "aqi"


class TestHolidayScraper:
    def test_generates_holidays(self):
        scraper = HolidayScraper()
        df = scraper.scrape(date(2024, 1, 1), date(2024, 12, 31))
        assert len(df) > 10  # should have many holidays
        assert "name" in df.columns
        assert "date" in df.columns

    def test_includes_republic_day(self):
        scraper = HolidayScraper()
        df = scraper.scrape(date(2024, 1, 1), date(2024, 2, 28))
        names = df["name"].str.lower().tolist()
        assert any("republic" in n for n in names)
