.PHONY: setup install db migrate-legacy scrape train serve test clean

# Setup everything from scratch
setup: install db

# Install dependencies
install:
	pip install -e ".[dev]"

# Create database tables
db:
	python -c "from src.data.db.session import create_tables; create_tables(); print('Database tables created')"

# Import legacy data from old EDFS project
migrate-legacy:
	python scripts/migrate_legacy_data.py

# Run all scrapers once
scrape:
	python -c "from scripts.run_scrapers import run_all; run_all()"

# Train all models
train:
	python -c "from src.training.train import run_champion_challenger; run_champion_challenger('daily')"

# Start FastAPI server
serve:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
test:
	pytest tests/ -v

# Clean generated files
clean:
	rm -rf data/edfs.db mlflow/ __pycache__ .pytest_cache
