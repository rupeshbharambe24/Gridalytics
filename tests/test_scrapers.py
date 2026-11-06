"""Tests for data scrapers."""

import pandas as pd
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

    def test_holi_and_diwali_week_every_year(self):
        """Holi (~-31% peak) was missing before 2024; Diwali spans 3 days."""
        scraper = HolidayScraper()
        df = scraper.validate(scraper.scrape(date(2015, 1, 1), date(2023, 12, 31)))
        years = lambda n: set(pd.to_datetime(df[df["name"] == n]["date"]).dt.year)
        for name in ["Holi", "Diwali", "Govardhan Puja", "Bhai Duj"]:
            assert years(name) == set(range(2015, 2024)), name
        assert (df[df["name"] == "Holi"]["category"] == "festival").all()

    def test_canonical_names(self):
        scraper = HolidayScraper()
        df = scraper.validate(scraper.scrape(date(2015, 1, 1), date(2027, 12, 31)))
        names = set(df["name"])
        assert not any(";" in n or "/" in n or "(estimated)" in n for n in names)
        assert "Diwali (Deepavali)" not in names and "Eid ul-Fitr" not in names

    def test_diwali_2026_date(self):
        scraper = HolidayScraper()
        df = scraper.scrape(date(2026, 1, 1), date(2026, 12, 31))
        assert set(df[df["name"] == "Diwali"]["date"]) == {date(2026, 11, 8)}


class TestOfficialPSPParser:
    TEXT = "\n".join([
        "B. Frequency Profile",
        "UP 1 2 3 4 5 6 7",                                   # before section C: ignored
        "C. Power Supply Position in States",
        "NR UP 24896 490 526.5 279.7 1.4 928 20.69",
        "Uttarakhand 2517 0 54.3 33.8 0.1 291 0.47",
        "J&K(UT) & Ladakh(UT) 2550 0 48.7 40.9 -0.8 215/ -717 0.00",  # 2026 layout
        "DNH 648 0 14.6 14.5 0.1 70 0.00",                    # pre-merger: not mapped
        "DNHDDPDCL 1272 0 24.6 25.4 -0.8 19/ -298 0.00",
        "MP 10772 0 242.0 106.5 0.0 706 0.00",
        "D. Next section",
        "MP 1 1 1 1 1 1 1",                                   # after section C: ignored
    ])

    def test_parses_wanted_rows(self):
        from src.data.scrapers.state_fallback import parse_section_c
        out = parse_section_c(self.TEXT)
        assert set(out) == {"uttar_pradesh", "jammu_kashmir", "dnh_dd", "madhya_pradesh"}
        assert out["uttar_pradesh"] == {"peak_demand_met_mw": 24896.0, "shortage_mw": 490.0,
                                        "energy_met_mu": 526.5}
        assert out["jammu_kashmir"]["peak_demand_met_mw"] == 2550.0
        assert out["dnh_dd"]["peak_demand_met_mw"] == 1272.0
        assert out["madhya_pradesh"]["energy_met_mu"] == 242.0
