# Data Models

## Overview

The system uses MongoDB for storing metadata. All models inherit from `MongoBaseModel` which provides `to_mongo()` and `from_mongo()` methods for serialization.

---

## ImageDoc

**Collection:** `images`

Tracks an image through the processing pipeline.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB document ID |
| `image_id` | str | Unique UUID identifier |
| `batch_id` | str | Batch this image belongs to |
| `source_path` | str | Original blob path in `incoming/` |
| `source_filename` | str | Original filename |
| `external_id` | str | External system reference |
| `status` | ImageStatus | Current processing status |
| `status_updated_at` | datetime | Last status change timestamp |
| `preprocessing` | PreprocessingInfo | Preprocessing details |
| `processing` | ProcessingInfo | Decoding details |
| `final_blob_path` | str | Final location after processing |
| `detection_count` | int | Number of barcodes detected |
| `content_type` | str | MIME type (default: `image/jpeg`) |
| `file_size_bytes` | int | File size in bytes |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

### ImageStatus Enum

| Value | Description |
|-------|-------------|
| `pending` | Newly uploaded, awaiting preprocessing |
| `preprocessing` | Currently being preprocessed |
| `preprocessed` | Ready for decoding |
| `decoding_primary` | ZBar decoding in progress |
| `decoded_primary` | Successfully decoded by ZBar |
| `decoding_fallback` | Gemini decoding in progress |
| `decoded_fallback` | Successfully decoded by Gemini |
| `manual_review` | Needs human verification |
| `decoded_manual` | Resolved via manual review |
| `failed` | All decoding attempts failed |

### PreprocessingInfo

| Field | Type | Description |
|-------|------|-------------|
| `normalized_path` | str | Path to normalized image |
| `original_width` | int | Original image width |
| `original_height` | int | Original image height |
| `processed_width` | int | Processed image width |
| `processed_height` | int | Processed image height |
| `grayscale` | bool | Converted to grayscale |
| `clahe_applied` | bool | CLAHE enhancement applied |
| `denoised` | bool | Denoising applied |
| `rotations_generated` | list[int] | Rotation angles generated |
| `duration_ms` | int | Processing duration |
| `completed_at` | datetime | Completion timestamp |

### ProcessingInfo

| Field | Type | Description |
|-------|------|-------------|
| `primary_attempts` | list[DecoderAttempt] | ZBar decoding attempts |
| `fallback_attempts` | list[DecoderAttempt] | Gemini decoding attempts |
| `needs_fallback` | bool | Flagged for fallback processing |
| `gemini_tokens_used` | int | Total Gemini tokens consumed |
| `errors` | list[ProcessingError] | Processing errors |

### DecoderAttempt

| Field | Type | Description |
|-------|------|-------------|
| `decoder` | str | Decoder name: `zbar`, `zxing`, `gemini` |
| `attempt_number` | int | Attempt sequence number |
| `success` | bool | Whether attempt succeeded |
| `codes_found` | int | Number of barcodes found |
| `duration_ms` | int | Attempt duration |
| `timestamp` | datetime | Attempt timestamp |
| `error` | str | Error message if failed |

---

## DetectionDoc

**Collection:** `detections`

Stores detected barcode information.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB document ID |
| `image_id` | str | Parent image reference |
| `batch_id` | str | Batch identifier |
| `source_filename` | str | Original filename (denormalized) |
| `code` | str | Detected barcode value |
| `symbology` | BarcodeSymbology | Barcode type |
| `normalized_code` | str | EAN-13 normalized form |
| `source` | DetectionSource | How the barcode was detected |
| `confidence` | float | Confidence score (0.0-1.0) |
| `rotation` | int | Rotation angle when detected |
| `checksum_valid` | bool | Checksum validation passed |
| `length_valid` | bool | Valid length for symbology |
| `numeric_only` | bool | Contains only digits |
| `ambiguous` | bool | Multiple codes, needs review |
| `chosen` | bool | Selected in manual review |
| `rejected` | bool | Rejected in manual review |
| `product_found` | bool | Exists in product catalog |
| `product_id` | str | Product reference if found |
| `gemini_confidence` | float | Gemini's confidence score |
| `gemini_symbology` | str | Gemini's symbology guess |
| `created_at` | datetime | Detection timestamp |
| `reviewed_at` | datetime | Review timestamp |
| `reviewed_by` | str | Reviewer identifier |

### BarcodeSymbology Enum

| Value | Description |
|-------|-------------|
| `EAN-13` | 13-digit European Article Number |
| `EAN-8` | 8-digit EAN |
| `UPC-A` | 12-digit Universal Product Code |
| `UPC-E` | Compressed UPC |
| `UNKNOWN` | Unknown or unsupported format |

### DetectionSource Enum

| Value | Description |
|-------|-------------|
| `primary_zbar` | Detected by ZBar library |
| `primary_zxing` | Detected by ZXing library |
| `fallback_gemini` | Detected by Gemini AI |
| `manual` | Manually entered |

---

## ProductDoc

**Collection:** `products`

Product catalog for barcode validation.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB document ID |
| `ean` | str | Primary EAN-13 code |
| `upc` | str | UPC-A code |
| `ean8` | str | EAN-8 code |
| `alternate_codes` | list[str] | Other barcodes for this product |
| `name` | str | Product name |
| `brand` | str | Brand name |
| `description` | str | Product description |
| `category` | str | Primary category |
| `subcategory` | str | Subcategory |
| `size` | str | Size/weight description |
| `unit` | str | Unit type |
| `pack_size` | int | Pack quantity |
| `external_id` | str | External system reference |
| `sku` | str | Internal SKU |
| `active` | bool | Is product active |
| `image_url` | str | Product image URL |
| `source` | str | Data source |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

---

## JobDoc

**Collection:** `jobs`

Processing job queue.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB document ID |
| `job_id` | str | Unique job UUID |
| `job_type` | JobType | Type of job |
| `image_id` | str | Target image ID |
| `batch_id` | str | Batch identifier |
| `status` | JobStatus | Current job status |
| `priority` | int | Priority (higher = more urgent) |
| `attempt` | int | Current attempt number |
| `max_retries` | int | Maximum retry attempts (default: 3) |
| `worker_id` | str | Processing worker ID |
| `started_at` | datetime | Job start time |
| `completed_at` | datetime | Job completion time |
| `result` | dict | Job result data |
| `error` | str | Error message if failed |
| `error_details` | dict | Detailed error information |
| `scheduled_for` | datetime | Scheduled execution time |
| `lock_until` | datetime | Lock expiry for distributed processing |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

### JobType Enum

| Value | Description |
|-------|-------------|
| `preprocess` | Image preprocessing |
| `decode_primary` | Primary barcode decoding |
| `decode_fallback` | Fallback AI decoding |
| `cleanup` | Cleanup/archival job |

### JobStatus Enum

| Value | Description |
|-------|-------------|
| `pending` | Awaiting processing |
| `in_progress` | Currently being processed |
| `completed` | Successfully completed |
| `failed` | Failed (may retry) |
| `cancelled` | Manually cancelled |

---

## Database Indexes

### images Collection

- `status` (ascending)
- `batch_id` (ascending)
- `image_id` (ascending)
- `created_at` (ascending)
- `source_filename` (ascending)

### detections Collection

- `image_id` (ascending)
- `code` (ascending)
- `batch_id` (ascending)
- `source` (ascending)
- `ambiguous` (ascending)
- `checksum_valid` (ascending)
- `source_filename` (ascending)

### products Collection

- `ean` (ascending)
- `upc` (ascending)
- `name` (ascending)

### jobs Collection

- `job_id` (ascending)
- `status` (ascending)
- `job_type` (ascending)
- `image_id` (ascending)
