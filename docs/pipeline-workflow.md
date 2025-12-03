# Pipeline Workflow

## Overview

The EAN Extraction System uses a multi-stage pipeline to process product images and extract barcodes. Each stage is handled by a dedicated worker that processes images asynchronously.

---

## Pipeline Stages

### 1. Upload

**Tool:** `poetry run upload`

Images are uploaded to Azure Blob Storage and registered in MongoDB.

**Actions:**
- Upload image to `incoming/{batch_id}/{filename}`
- Create `ImageDoc` with status `pending`
- Check for duplicates (same `batch_id` + `source_filename`)

---

### 2. Preprocessing

**Worker:** `workers/preprocess/main.py`

Normalizes images for optimal barcode detection.

**Input Status:** `pending`
**Output Status:** `preprocessed`

**Processing Steps:**
1. Download image from blob storage
2. Convert to grayscale
3. Resize if larger than max dimension (2048px default)
4. Apply denoising filter
5. Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
6. Generate rotated versions (0°, 90°, 180°, 270°)
7. Upload normalized image to `preprocessed/{batch_id}/{image_id}.jpg`
8. Move original to `original/{batch_id}/{filename}`

---

### 3. Primary Decoding (ZBar)

**Worker:** `workers/decode_primary/main.py`

Fast local barcode detection using ZBar library.

**Input Status:** `preprocessed`
**Output Status:** `decoded_primary`, or flags `needs_fallback=true`

**Processing Steps:**
1. Download preprocessed image
2. Attempt decoding with ZBar on each rotation
3. Validate detected codes (checksum, length, numeric)
4. Create `DetectionDoc` for each valid code
5. If codes found → `decoded_primary`
6. If no codes → set `needs_fallback=true`

**Barcode Types Detected:**
- EAN-13
- EAN-8
- UPC-A
- UPC-E

---

### 4. Fallback Decoding (Gemini AI)

**Worker:** `workers/decode_fallback/main.py`

AI-powered barcode extraction for difficult images.

**Input Status:** `preprocessed` with `needs_fallback=true`
**Output Status:** `decoded_fallback`, `manual_review`, or `failed`

**Processing Steps:**
1. Download image
2. Send to Gemini with specialized prompt
3. Parse structured response (code, symbology, confidence)
4. Validate detected codes
5. If single valid code → `decoded_fallback`
6. If multiple codes → `manual_review`
7. If no codes after max attempts → `failed`

**Gemini Prompt Strategy:**
- Request structured JSON output
- Ask for code, symbology type, and confidence
- Include retry logic with different prompts

---

### 5. Manual Review

**Tool:** `tools/manual_review_ui/app.py`

Human verification for ambiguous detections.

**Input Status:** `manual_review`
**Output Status:** `decoded_manual` or `failed`

**Review Actions:**
| Action | Effect |
|--------|--------|
| `choose` | Select one detection as correct, reject others |
| `no_barcode` | Mark image as having no valid barcode → `failed` |
| `skip` | Leave for later review |

---

### 6. Failed Retry

**Worker:** `workers/decode_failed/main.py`

Retries failed images with Gemini (up to 3 total attempts).

**Input Status:** `failed` with < 3 fallback attempts
**Output Status:** `decoded_fallback` or remains `failed`

---

## Status Flow Diagram

```
                    ┌─────────┐
                    │ pending │
                    └────┬────┘
                         │
                    ┌────▼────────┐
                    │preprocessing│
                    └────┬────────┘
                         │
                    ┌────▼───────┐
                    │preprocessed│
                    └────┬───────┘
                         │
               ┌─────────▼─────────┐
               │ decoding_primary  │
               └─────────┬─────────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
     ┌─────▼─────┐       │       ┌─────▼──────────┐
     │ decoded_  │       │       │ needs_fallback │
     │ primary   │       │       │    = true      │
     └───────────┘       │       └───────┬────────┘
                         │               │
                         │     ┌─────────▼─────────┐
                         │     │decoding_fallback  │
                         │     └─────────┬─────────┘
                         │               │
                         │   ┌───────────┼───────────┐
                         │   │           │           │
                   ┌─────▼───▼───┐ ┌─────▼─────┐ ┌───▼────┐
                   │  decoded_   │ │  manual_  │ │ failed │
                   │  fallback   │ │  review   │ └───┬────┘
                   └─────────────┘ └─────┬─────┘     │
                                         │           │
                                   ┌─────▼─────┐     │
                                   │ decoded_  │     │
                                   │  manual   │     │
                                   └───────────┘     │
                                                     │
                                         ┌───────────▼───────────┐
                                         │  retry (< 3 attempts) │
                                         └───────────────────────┘
```

---

## Final States

| Status | Blob Location | Description |
|--------|---------------|-------------|
| `decoded_primary` | `processed/` | Successfully decoded by ZBar |
| `decoded_fallback` | `processed/` | Successfully decoded by Gemini |
| `decoded_manual` | `processed/` | Confirmed via manual review |
| `failed` | `failed/` | Could not extract barcode |

---

## Concurrency & Idempotency

### Job Locking

Each worker acquires a lock on images before processing:
- `lock_until` field prevents concurrent processing
- Lock automatically expires after timeout
- Failed jobs can be retried

### Idempotency Checks

Workers check for existing work before processing:
- `DetectionRepository.exists_for_image()` - Skip if detections exist
- Status checks - Only process images in expected state

---

## Error Handling

### Retry Strategy

| Stage | Max Retries | Backoff |
|-------|-------------|---------|
| Preprocessing | 3 | Immediate |
| Primary Decode | 1 | N/A |
| Fallback Decode | 3 | Exponential |
| Failed Retry | 3 total | 30s interval |

### Error Recording

All errors are stored in `ImageDoc.processing.errors`:
```python
{
    "stage": "decode_fallback",
    "message": "Gemini API rate limit exceeded",
    "timestamp": "2025-12-03T10:30:00Z",
    "details": {"status_code": 429}
}
```

---

## Monitoring

### Get Pipeline Statistics

```bash
poetry run dispatcher --stats
```

Output:
```json
{
  "pending": 50,
  "preprocessing": 0,
  "preprocessed": 10,
  "decoding_primary": 5,
  "decoded_primary": 600,
  "decoding_fallback": 2,
  "decoded_fallback": 150,
  "manual_review": 20,
  "decoded_manual": 43,
  "failed": 120
}
```

### Success Rate Calculation

```
success_rate = (decoded_primary + decoded_fallback + decoded_manual) / total_images * 100
```
