# EAN Extraction System

An automated barcode extraction system built with Azure, **Azure Cosmos DB (MongoDB API)**, and Google Gemini AI.

## Overview

This system processes product images to extract EAN/UPC barcodes using a multi-stage approach:

1. **Preprocessing** - Image normalization, enhancement, and optimization
2. **Primary Decoding** - Fast local barcode detection using ZXing/ZBar
3. **Fallback Decoding** - AI-powered extraction using Google Gemini for difficult cases
4. **Manual Review** - Human verification for ambiguous or failed detections

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Upload Tool    │───▶│  Azure Blob      │───▶│  Preprocessor   │
│  (CLI/Web)      │    │  Storage         │    │  Worker         │
└─────────────────┘    └──────────────────┘    └────────┬────────┘
                                                        │
                       ┌──────────────────┐             ▼
                       │ Azure Cosmos DB  │◀───┬────────────────┐
                       │ (MongoDB API)    │    │                │
                       └──────────────────┘    ▼                ▼
                                        ┌──────────┐    ┌──────────────┐
                                        │ Primary  │    │   Fallback   │
                                        │ Decoder  │    │   (Gemini)   │
                                        │ (ZBar)   │    │   Decoder    │
                                        └──────────┘    └──────────────┘
                                               │                │
                                               ▼                ▼
                                        ┌─────────────────────────────┐
                                        │      Manual Review UI       │
                                        └─────────────────────────────┘
```

## Project Structure

```
├── src/                          # Shared libraries
│   ├── models/                   # Pydantic models & MongoDB schemas
│   ├── db/                       # Database repository layer
│   ├── storage/                  # Azure Blob Storage integration
│   ├── barcode/                  # Barcode decoding utilities
│   ├── llm/                      # Gemini AI integration
│   └── config/                   # Configuration management
│
├── workers/                      # Background workers
│   ├── preprocess/              # Image preprocessing
│   ├── decode_primary/          # ZBar/ZXing decoding
│   ├── decode_fallback/         # Gemini AI fallback
│   └── dispatcher/              # Job orchestration
│
├── tools/                        # CLI & utility tools
│   ├── uploader/                # Batch image upload
│   └── manual_review_ui/        # Admin review interface
│
├── tests/                        # Test suites
├── infra/                        # Infrastructure as Code
└── docs/                         # Documentation
```

## Blob Container Structure

```
product-images/
├── incoming/          # Raw uploaded images
├── preprocessed/      # Normalized images ready for decoding
├── processed/         # Successfully decoded images
├── failed/            # Images that couldn't be decoded
└── manual-review/     # Images requiring human review
```

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Azure CLI
- Azure Cosmos DB (MongoDB API) account
- Google Gemini API key
- System deps for OpenCV (image preprocessing):
  ```bash
  sudo apt-get update && sudo apt-get install -y libgl1 libglib2.0-0
  ```
- System deps for ZBar (barcode decoding used by pyzbar):
  ```bash
  sudo apt-get update && sudo apt-get install -y libzbar0
  ```

### Installation

```bash
# Clone repository
git clone <repo-url>
cd EAN-numbers-vision

# Install dependencies
poetry install

# Copy environment template (use .env or .env.local; .env.local overrides .env)
cp .env.example .env
# OR
cp .env.example .env.local
# Edit with your credentials (Cosmos URI, Gemini key, storage, etc.)

# (Optional) Initialize Cosmos DB indexes on first deploy
# Uses Cosmos DB-compatible single-field indexes
poetry run python -m src.db.init_indexes
```

### Configuration

Set the following environment variables (or use `.env` / `.env.local`; `.env.local` overrides):

```bash
# Azure
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER=product-images

# Azure Cosmos DB (MongoDB API)
# Use the Cosmos DB connection string (Mongo API), e.g.:
# mongodb://<user>:<password>@<account>.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&maxIdleTimeMS=120000&appName=@<account>@
MONGODB_URI=
MONGODB_DATABASE=ean-extraction-dev

# Gemini
GEMINI_API_KEY=

# Environment
ENVIRONMENT=dev
```

### Usage

```bash
# Upload images
poetry run upload --batch-id batch_001 --source ./images/

# Run dispatcher (starts job processing)
poetry run dispatcher

# Run individual workers
poetry run python -m workers.preprocess.main
poetry run python -m workers.decode_primary.main
poetry run python -m workers.decode_fallback.main
poetry run python -m workers.decode_failed.main  # retries Gemini on previously failed images

# Generate reports (CSV or Markdown) for a batch
poetry run python -m tools.reports.main --batch-id <batch_id> --format csv
# Optional: output to file
poetry run python -m tools.reports.main --batch-id <batch_id> --format markdown --output report.md
# (Alias) using the Poetry script
poetry run report --batch-id <batch_id> --format csv

# Start manual review UI
poetry run uvicorn tools.manual_review_ui.app:app --reload

### Minimal run sequence for a fresh user

1) Install system deps (OpenCV & ZBar):
       ```bash
       sudo apt-get update && sudo apt-get install -y libgl1 libglib2.0-0 libzbar0
       ```
2) Install Python deps: `poetry install`
3) Configure env: copy `.env.example` to `.env.local` and fill `MONGODB_URI`, `MONGODB_DATABASE`, `AZURE_STORAGE_*`, `GEMINI_API_KEY`.
4) (First run) create indexes: `poetry run python -m src.db.init_indexes`
5) Upload images: `poetry run upload --batch-id batch_001 --source ./images/`
6) Start processing (new shells or tmux panes):
       ```bash
       poetry run dispatcher
       poetry run python -m workers.preprocess.main
       poetry run python -m workers.decode_primary.main
       poetry run python -m workers.decode_fallback.main
       poetry run python -m workers.decode_failed.main
       ```
7) Review & export:
       - Manual review UI: `poetry run uvicorn tools.manual_review_ui.app:app --reload`
       - Reports: `poetry run report --batch-id batch_001 --format markdown --output report.md`
```

## Development

```bash
# Install dev dependencies
poetry install --with dev

# Run linting
poetry run ruff check .
poetry run black --check .

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov=workers --cov-report=html
```

## API Endpoints (Manual Review UI)

- `GET /api/images/review` - List images pending review
- `GET /api/images/{image_id}` - Get image details
- `POST /api/images/{image_id}/resolve` - Submit review decision
- `GET /api/stats` - Get processing statistics

## Supported Barcode Formats

- EAN-13
- EAN-8
- UPC-A
- UPC-E

## License

Proprietary - All rights reserved
