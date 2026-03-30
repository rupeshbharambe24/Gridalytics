"""Grid India PSP daily report scraper using Selenium.

Source: https://report.grid-india.in/psp_report.php
Downloads daily PSP reports (Excel or PDF) and extracts Delhi demand data.
Requires: Chrome/Chromium + ChromeDriver installed.
"""

import os
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from src.data.db.models import PSPDailyReport
from .base import BaseScraper


class GridIndiaScraper(BaseScraper):
    """Selenium-based scraper for Grid India PSP daily reports."""

    def __init__(self):
        super().__init__(name="grid_india", max_retries=2, retry_delay=5.0)
        self.rate_limit_delay = 2.0
        self.url = "https://report.grid-india.in/psp_report.php"

    def _create_driver(self, download_dir: str):
        """Create headless Chrome WebDriver."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            raise RuntimeError(
                "Selenium is required for Grid India scraper. "
                "Install with: pip install selenium"
            )

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_experimental_option("prefs", {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        })

        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            raise RuntimeError(
                f"ChromeDriver not found or Chrome not installed: {e}\n"
                "Install Chrome and ChromeDriver, or use: apt install chromium chromium-driver"
            )

        return driver

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Scrape PSP reports for the date range."""
        download_dir = tempfile.mkdtemp(prefix="gridalytics_psp_")
        results = []

        try:
            driver = self._create_driver(download_dir)
        except RuntimeError as e:
            self.logger.error(str(e))
            return pd.DataFrame()

        try:
            current = start_date
            while current <= end_date:
                date_str = current.strftime("%d-%m-%Y")
                self.logger.info(f"Fetching PSP for {date_str}")

                try:
                    row = self._scrape_single_date(driver, current, date_str, download_dir)
                    if row:
                        results.append(row)
                except Exception as e:
                    self.logger.warning(f"Failed for {date_str}: {e}")

                current += timedelta(days=1)
                time.sleep(self.rate_limit_delay)
        finally:
            driver.quit()
            # Cleanup temp files
            import shutil
            shutil.rmtree(download_dir, ignore_errors=True)

        if not results:
            return pd.DataFrame()

        return pd.DataFrame(results)

    def _scrape_single_date(self, driver, target_date: date, date_str: str, download_dir: str) -> dict | None:
        """Scrape a single date's PSP report."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver.get(self.url)
        time.sleep(1)

        # Find and fill date input
        try:
            date_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "selected_date"))
            )
            date_input.clear()
            driver.execute_script(
                "arguments[0].value = arguments[1]", date_input, date_str
            )
        except Exception:
            # Try alternate selectors
            for selector in ["input[type='date']", "input[name='date']", "#date"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    driver.execute_script(f"arguments[0].value = '{date_str}'", el)
                    break
                except Exception:
                    continue

        # Submit form
        try:
            submit = driver.find_element(By.XPATH, "//input[@type='submit']")
            submit.click()
        except Exception:
            try:
                submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit.click()
            except Exception:
                self.logger.warning(f"Could not find submit button for {date_str}")
                return None

        time.sleep(2)

        # Try Excel download first
        row = self._try_excel_download(driver, target_date, download_dir)
        if row:
            return row

        # Try PDF download
        row = self._try_pdf_download(driver, target_date, download_dir)
        if row:
            return row

        # Fallback: parse HTML table
        return self._parse_html_table(driver, target_date)

    def _try_excel_download(self, driver, target_date: date, download_dir: str) -> dict | None:
        """Try to download and parse Excel report."""
        from selenium.webdriver.common.by import By

        for selector in [
            "//a[contains(@href, '.xlsx')]",
            "//a[contains(@href, '.xls')]",
            "//a[contains(text(), 'Excel')]",
            "//a[@id='lnkExcel']",
        ]:
            try:
                link = driver.find_element(By.XPATH, selector)
                link.click()
                time.sleep(3)

                # Find downloaded file
                files = [f for f in os.listdir(download_dir)
                         if f.endswith((".xlsx", ".xls")) and not f.startswith(".")]
                if files:
                    filepath = os.path.join(download_dir, files[-1])
                    return self._parse_excel(filepath, target_date)
            except Exception:
                continue

        return None

    def _try_pdf_download(self, driver, target_date: date, download_dir: str) -> dict | None:
        """Try to download and parse PDF report."""
        from selenium.webdriver.common.by import By

        try:
            link = driver.find_element(By.XPATH, "//a[contains(@href, '.pdf')]")
            link.click()
            time.sleep(3)

            files = [f for f in os.listdir(download_dir) if f.endswith(".pdf")]
            if files:
                filepath = os.path.join(download_dir, files[-1])
                return self._parse_pdf(filepath, target_date)
        except Exception:
            pass

        return None

    def _parse_excel(self, filepath: str, target_date: date) -> dict | None:
        """Extract Delhi demand from Excel file."""
        try:
            xls = pd.ExcelFile(filepath)
            for sheet in xls.sheet_names:
                df = xls.parse(sheet, header=None)
                result = self._extract_delhi_row(df, target_date)
                if result:
                    return result
        except Exception as e:
            self.logger.warning(f"Excel parse failed: {e}")
        return None

    def _parse_pdf(self, filepath: str, target_date: date) -> dict | None:
        """Extract Delhi demand from PDF file."""
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in (tables or []):
                        df = pd.DataFrame(table)
                        result = self._extract_delhi_row(df, target_date)
                        if result:
                            return result
        except Exception as e:
            self.logger.warning(f"PDF parse failed: {e}")
        return None

    def _parse_html_table(self, driver, target_date: date) -> dict | None:
        """Fallback: parse rendered HTML table for Delhi data."""
        from selenium.webdriver.common.by import By

        try:
            tables = driver.find_elements(By.TAG_NAME, "table")
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    cell_texts = [c.text.strip() for c in cells]
                    if any("delhi" in t.lower() for t in cell_texts):
                        # Find the demand value (usually 3rd column)
                        for i, t in enumerate(cell_texts):
                            if "delhi" in t.lower() and i + 1 < len(cell_texts):
                                try:
                                    demand = float(cell_texts[i + 1].replace(",", ""))
                                    if 1000 <= demand <= 12000:
                                        self.logger.info(f"HTML parse: Delhi demand = {demand} MW")
                                        return {
                                            "date": target_date,
                                            "delhi_demand_met_mw": demand,
                                        }
                                except ValueError:
                                    continue
        except Exception as e:
            self.logger.warning(f"HTML parse failed: {e}")
        return None

    def _extract_delhi_row(self, df: pd.DataFrame, target_date: date) -> dict | None:
        """Extract Delhi demand from a DataFrame (from Excel or PDF)."""
        for _, row in df.iterrows():
            row_str = " ".join(str(v).lower() for v in row if pd.notna(v))
            if "delhi" in row_str:
                # Find numeric values in this row
                nums = []
                for v in row:
                    try:
                        n = float(str(v).replace(",", ""))
                        if n > 100:
                            nums.append(n)
                    except (ValueError, TypeError):
                        continue

                if nums:
                    demand = nums[0]  # First large number is typically demand
                    energy = nums[1] if len(nums) > 1 else None
                    if 1000 <= demand <= 12000:
                        result = {
                            "date": target_date,
                            "delhi_demand_met_mw": demand,
                        }
                        if energy and energy < 500:  # Energy in MU
                            result["delhi_energy_met_mu"] = energy
                        return result
        return None

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate PSP report data."""
        if df.empty:
            return df

        initial_len = len(df)
        df = df.dropna(subset=["date"])

        if "delhi_demand_met_mw" in df.columns:
            df = df[
                (df["delhi_demand_met_mw"] >= 1000) &
                (df["delhi_demand_met_mw"] <= 12000)
            ]

        df = df.drop_duplicates(subset=["date"], keep="last")

        dropped = initial_len - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped} invalid PSP rows out of {initial_len}")

        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert or update PSP records."""
        if df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            existing = session.query(PSPDailyReport).filter(
                PSPDailyReport.date == row["date"]
            ).first()

            if existing:
                # Update existing record
                if row.get("delhi_demand_met_mw"):
                    existing.delhi_demand_met_mw = row["delhi_demand_met_mw"]
                if row.get("delhi_energy_met_mu"):
                    existing.delhi_energy_met_mu = row["delhi_energy_met_mu"]
                if row.get("northern_region_demand_mw"):
                    existing.northern_region_demand_mw = row["northern_region_demand_mw"]
                existing.source = "grid_india"
            else:
                record = PSPDailyReport(
                    date=row["date"],
                    delhi_demand_met_mw=row.get("delhi_demand_met_mw"),
                    delhi_energy_met_mu=row.get("delhi_energy_met_mu"),
                    northern_region_demand_mw=row.get("northern_region_demand_mw"),
                    source="grid_india",
                )
                session.add(record)
                count += 1

        session.flush()
        return count
