# Development Setup

## Prerequisites

- Python 3.11 or higher
- Poetry (package manager)
- Docker & Docker Compose (for local development)
- Azure CLI (for deployment)
- MongoDB Atlas account or local MongoDB

## Quick Start

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd 622_go_keto

# Install dependencies
poetry install

# Install with dev dependencies
poetry install --with dev
```

### 2. Environment Configuration

Create a `.env` file in the project root:

```bash
# Environment
ENVIRONMENT=dev

# Azure Storage (use Azurite for local development)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
AZURE_STORAGE_CONTAINER=images

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=ean_extraction

# Gemini AI (required for fallback decoding)
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-2.0-flash

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=console
```

### 3. Start Local Services with Docker

```bash
# Start MongoDB and Azurite (Azure Storage emulator)
docker-compose up -d mongodb azurite

# Verify services are running
docker-compose ps
```

### 4. Initialize Database Indexes

```bash
poetry run python -m src.db.init_indexes
```

### 5. Create Storage Container

```bash
# Using Azure CLI with Azurite
az storage container create \
  --name images \
  --connection-string "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
```

## Environment Variables Reference

### Required

| Variable | Description |
|----------|-------------|
| `MONGODB_URI` | MongoDB connection string |
| `GEMINI_API_KEY` | Google Gemini API key (for fallback) |

### Azure Storage (one of these required)

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Full connection string |
| `AZURE_STORAGE_ACCOUNT_URL` | Storage account URL (for Managed Identity) |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `dev` | Environment: `dev`, `staging`, `prod` |
| `AZURE_STORAGE_CONTAINER` | `images` | Blob container name |
| `MONGODB_DATABASE` | `ean_extraction` | Database name |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `GEMINI_MAX_TOKENS` | `1024` | Max output tokens |
| `GEMINI_TEMPERATURE` | `1.0` | Model temperature |
| `GEMINI_TIMEOUT` | `30` | Request timeout (seconds) |
| `WORKER_POLL_INTERVAL` | `5` | Seconds between job polls |
| `WORKER_BATCH_SIZE` | `10` | Max jobs per batch |
| `WORKER_MAX_RETRIES` | `3` | Max retry attempts |
| `PREPROCESS_MAX_DIMENSION` | `2048` | Max image dimension (px) |
| `PREPROCESS_DENOISE_STRENGTH` | `10` | Denoise filter strength |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `console` | Format: `console` or `json` |
| `REVIEW_UI_HOST` | `0.0.0.0` | Review UI host |
| `REVIEW_UI_PORT` | `8000` | Review UI port |
| `RETENTION_DAYS` | `90` | Days to retain processed images |

## Running the Full Stack

### Option 1: Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Option 2: Run Workers Individually

```bash
# Terminal 1: Dispatcher
poetry run dispatcher

# Terminal 2: Preprocess Worker
poetry run python -m workers.preprocess.main

# Terminal 3: Primary Decode Worker
poetry run python -m workers.decode_primary.main

# Terminal 4: Fallback Decode Worker
poetry run python -m workers.decode_fallback.main

# Terminal 5: Manual Review UI
poetry run python -m tools.manual_review_ui.app
```

## Development Commands

```bash
# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov=workers --cov-report=html

# Linting
poetry run ruff check .

# Formatting
poetry run black .

# Type checking
poetry run mypy src workers tools
```

## Troubleshooting

### MongoDB Connection Issues

```bash
# Check if MongoDB is running
docker-compose ps mongodb

# Check MongoDB logs
docker-compose logs mongodb
```

### Azurite (Azure Storage Emulator) Issues

```bash
# Check if Azurite is running
docker-compose ps azurite

# Verify container exists
az storage container list \
  --connection-string "..." \
  --output table
```

### ZBar Library Not Found

On macOS:
```bash
brew install zbar
```

On Ubuntu/Debian:
```bash
sudo apt-get install libzbar0
```
