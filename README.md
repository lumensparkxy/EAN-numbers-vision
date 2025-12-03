# EAN Extraction System

An automated barcode extraction system built with Azure, MongoDB, and Google Gemini AI.

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
                       │  MongoDB Atlas   │◀───┬────────────────┐
                       │  (Metadata)      │    │                │
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
- MongoDB Atlas account (or Azure Cosmos DB)
- Google Gemini API key

### Installation

```bash
# Clone repository
git clone <repo-url>
cd ean-extraction

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run database migrations/index creation
poetry run python -m src.db.init_indexes
```

### Configuration

Set the following environment variables (or use `.env`):

```bash
# Azure
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER=product-images

# MongoDB
MONGODB_URI=mongodb+srv://...
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

# Start manual review UI
poetry run uvicorn tools.manual_review_ui.app:app --reload
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
