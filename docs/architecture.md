# System Architecture

## Overview

The EAN Extraction System is an automated barcode extraction pipeline for processing product images to extract EAN/UPC barcodes. It uses a multi-stage approach combining traditional barcode decoding (ZBar) with AI-powered fallback (Google Gemini) for difficult cases.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Image Storage | Azure Blob Storage |
| Metadata Store | MongoDB Atlas / Azure Cosmos DB |
| AI Fallback | Google Gemini |
| Web Framework | FastAPI |
| Barcode Decoding | ZBar (pyzbar) |
| Image Processing | OpenCV, Pillow |
| CLI Framework | Click |

## High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Upload Tool    │───▶│  Azure Blob      │───▶│  Preprocessor   │
│  (CLI)          │    │  Storage         │    │  Worker         │
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
                                        │         (FastAPI)           │
                                        └─────────────────────────────┘
                                                      │
                                                      ▼
                                        ┌─────────────────────────────┐
                                        │      Report Generator       │
                                        └─────────────────────────────┘
```

## Components

### Workers

| Worker | Purpose | Input Status | Output Status |
|--------|---------|--------------|---------------|
| `dispatcher` | Orchestrates pipeline, creates jobs | - | - |
| `preprocess` | Normalizes images (grayscale, resize, denoise) | `pending` | `preprocessed` |
| `decode_primary` | Decodes barcodes using ZBar | `preprocessed` | `decoded_primary` or fallback |
| `decode_fallback` | Uses Gemini AI for failed images | `needs_fallback` | `decoded_fallback` or `manual_review` |
| `decode_failed` | Retries failed images (up to 3 attempts) | `failed` | `decoded_fallback` or `failed` |

### Tools

| Tool | Purpose |
|------|---------|
| `upload` | Uploads images to blob storage, creates DB records |
| `report` | Generates CSV/Markdown reports of processed images |
| `find_detection` | Finds detections by source filename |
| `manual_review_ui` | FastAPI web UI for human verification |

### Source Modules

| Module | Purpose |
|--------|---------|
| `src/config` | Settings and logging configuration |
| `src/db` | MongoDB client and repositories |
| `src/models` | Pydantic document models |
| `src/storage` | Azure Blob Storage client and path helpers |
| `src/barcode` | Barcode decoding and validation |
| `src/llm` | Gemini AI integration |

## Blob Storage Structure

| Folder | Purpose |
|--------|---------|
| `incoming/` | Raw uploaded images (temporary staging) |
| `original/` | Moved from incoming after preprocessing |
| `preprocessed/` | Normalized images ready for decoding |
| `processed/` | Successfully decoded images |
| `failed/` | Images that couldn't be decoded |
| `manual-review/` | Images requiring human review |

## Data Flow

1. **Upload** → Images uploaded to `incoming/{batch_id}/`
2. **Preprocess** → Grayscale, resize, denoise, CLAHE → `preprocessed/{batch_id}/`
3. **Primary Decode** → ZBar attempts decoding with rotations
4. **Fallback Decode** → Gemini AI extraction if primary fails
5. **Manual Review** → Human verification for ambiguous detections
6. **Final State** → Images moved to `processed/` or `failed/`

## Database Collections

| Collection | Purpose |
|------------|---------|
| `images` | Image metadata and processing status |
| `detections` | Extracted barcode data |
| `products` | Product catalog for validation |
| `jobs` | Processing job queue |

## Supported Barcode Formats

| Format | Length | Description |
|--------|--------|-------------|
| EAN-13 | 13 digits | European Article Number (most common) |
| EAN-8 | 8 digits | Short EAN for small products |
| UPC-A | 12 digits | Universal Product Code (US/Canada) |
| UPC-E | 6-8 digits | Compressed UPC |

All formats use modulo-10 checksum validation. UPC-A is normalized to EAN-13 by prepending '0'.
