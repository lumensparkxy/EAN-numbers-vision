# CLI Tools Guide

## Overview

The EAN Extraction System provides several CLI tools for managing the processing pipeline.

## Upload Tool

Uploads local images to Azure Blob Storage and creates database records.

### Usage

```bash
poetry run upload --batch-id BATCH_ID --source PATH [OPTIONS]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--batch-id`, `-b` | Yes | - | Batch identifier for grouping images |
| `--source`, `-s` | Yes | - | Source directory containing images |
| `--prefix` | No | `""` | Prefix for external IDs |
| `--recursive`, `-r` | No | False | Search subdirectories |
| `--dry-run` | No | False | Preview without uploading |
| `--skip-duplicates` | No | True | Skip files already in batch |
| `--allow-duplicates` | No | - | Allow duplicate filenames |

### Examples

```bash
# Upload all images from a folder
poetry run upload --batch-id batch001 --source ./product_images

# Recursive upload with prefix
poetry run upload -b batch001 -s ./images --recursive --prefix "store_a_"

# Dry run to preview
poetry run upload -b batch001 -s ./images --dry-run
```

### Supported Image Formats

`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`

---

## Dispatcher

Coordinates the processing pipeline by dispatching jobs to workers.

### Usage

```bash
poetry run dispatcher [OPTIONS]
# or
python -m workers.dispatcher.main [OPTIONS]
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `50` | Max jobs per dispatch cycle |
| `--poll-interval` | `10` | Seconds between dispatches |
| `--once` | False | Run once and exit |
| `--stats` | False | Print stats as JSON and exit |

### Examples

```bash
# Run continuously
poetry run dispatcher

# Run once for testing
poetry run dispatcher --once

# Get pipeline statistics
poetry run dispatcher --stats
```

---

## Report Tool

Generates CSV or Markdown reports from processed images.

### Usage

```bash
poetry run report --batch-id BATCH_ID [OPTIONS]
# or
python -m tools.reports.main --batch-id BATCH_ID [OPTIONS]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--batch-id`, `-b` | Yes | - | Batch ID to generate report for |
| `--output`, `-o` | No | stdout | Output file path |
| `--format`, `-f` | No | `csv` | Output format: `csv` or `markdown` |

### Examples

```bash
# CSV to stdout
poetry run report --batch-id batch001

# CSV to file
poetry run report -b batch001 -o results.csv

# Markdown report
poetry run report -b batch001 --format markdown -o report.md
```

### Output Format

| Column | Description |
|--------|-------------|
| `source_filename` | Original image filename |
| `code` | Detected barcode or "failed" |

---

## Find Detection Tool

Finds detections by source filename for debugging.

### Usage

```bash
python -m tools.find_detection.main --filename FILENAME [OPTIONS]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--filename`, `-f` | Yes | - | Source filename to search |
| `--format` | No | `table` | Output format: `table` or `json` |

### Examples

```bash
# Table output
python -m tools.find_detection.main -f "product_001.jpg"

# JSON output
python -m tools.find_detection.main -f "product_001.jpg" --format json
```

### Table Output

```
Detections for: product_001.jpg
--------------------------------------------------------------------------------
Code            Symbology  Source          Valid  Product
--------------------------------------------------------------------------------
8011642115887   EAN-13     primary_zbar    ✓      ✓
--------------------------------------------------------------------------------
Total: 1 detection(s)
```

---

## Worker Commands

### Preprocess Worker

```bash
python -m workers.preprocess.main [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `10` | Images per batch |
| `--poll-interval` | `5` | Seconds between polls |
| `--once` | False | Run once and exit |
| `--continuous` | False | Keep running even when no work |

### Primary Decode Worker

```bash
python -m workers.decode_primary.main [OPTIONS]
```

Same options as preprocess worker.

### Fallback Decode Worker

```bash
python -m workers.decode_fallback.main [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `5` | Images per batch (lower due to API costs) |
| `--poll-interval` | `10` | Seconds between polls |
| `--once` | False | Run once and exit |
| `--continuous` | False | Keep running even when no work |

### Failed Retry Worker

```bash
python -m workers.decode_failed.main [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `5` | Images per batch |
| `--poll-interval` | `30` | Seconds between polls (longer interval) |
| `--once` | False | Run once and exit |
| `--continuous` | False | Keep running even when no work |

---

## Manual Review UI

Starts the FastAPI web application for manual barcode review.

### Usage

```bash
python -m tools.manual_review_ui.app
# or with uvicorn directly
uvicorn tools.manual_review_ui.app:app --host 0.0.0.0 --port 8000
```

### Access

Open http://localhost:8000 in your browser.

See [api-reference.md](api-reference.md) for API documentation.
