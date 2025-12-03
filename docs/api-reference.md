# API Reference

## Manual Review UI

The Manual Review UI is a FastAPI application for human verification of ambiguous barcode detections.

**Base URL:** `http://localhost:8000`

---

## Endpoints

### GET /

Redirects to the review interface.

**Response:** `302 Redirect` to `/review`

---

### GET /review

HTML page for manual review interface.

**Response:** HTML page

---

### GET /api/images/review

List images pending manual review.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max results (1-100) |
| `batch_id` | string | - | Filter by batch ID |

**Response:**

```json
{
  "images": [
    {
      "image_id": "abc123",
      "batch_id": "batch001",
      "source_filename": "product_001.jpg",
      "status": "manual_review",
      "blob_url": "https://...",
      "detections": [
        {
          "detection_id": "det001",
          "code": "8011642115887",
          "symbology": "EAN-13",
          "source": "fallback_gemini",
          "confidence": 0.95,
          "checksum_valid": true
        }
      ]
    }
  ],
  "total": 25
}
```

---

### GET /api/images/{image_id}

Get detailed information for a specific image.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `image_id` | string | Unique image identifier |

**Response:**

```json
{
  "image_id": "abc123",
  "batch_id": "batch001",
  "source_filename": "product_001.jpg",
  "source_path": "incoming/batch001/product_001.jpg",
  "status": "manual_review",
  "blob_url": "https://...",
  "preprocessing": {
    "normalized_path": "preprocessed/batch001/abc123.jpg",
    "original_width": 4000,
    "original_height": 3000,
    "processed_width": 2048,
    "processed_height": 1536,
    "grayscale": true,
    "clahe_applied": true
  },
  "detections": [
    {
      "detection_id": "det001",
      "code": "8011642115887",
      "symbology": "EAN-13",
      "source": "fallback_gemini",
      "confidence": 0.95,
      "checksum_valid": true,
      "length_valid": true,
      "numeric_only": true,
      "product_found": false,
      "gemini_confidence": 0.95,
      "gemini_symbology": "EAN-13"
    }
  ],
  "created_at": "2025-12-03T10:30:00Z",
  "updated_at": "2025-12-03T10:35:00Z"
}
```

**Error Response (404):**

```json
{
  "detail": "Image not found"
}
```

---

### POST /api/images/{image_id}/resolve

Submit a review decision for an image.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `image_id` | string | Unique image identifier |

**Request Body:**

```json
{
  "detection_id": "det001",
  "action": "choose",
  "reviewer": "john@example.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `detection_id` | string | Conditional | Detection to choose (required if action is `choose`) |
| `action` | string | Yes | `choose`, `no_barcode`, or `skip` |
| `reviewer` | string | No | Reviewer identifier |

**Actions:**

| Action | Description |
|--------|-------------|
| `choose` | Select the specified detection as correct |
| `no_barcode` | Mark image as having no valid barcode |
| `skip` | Skip this image for later review |

**Response (200):**

```json
{
  "success": true,
  "image_id": "abc123",
  "new_status": "decoded_manual"
}
```

**Error Response (400):**

```json
{
  "detail": "detection_id required when action is 'choose'"
}
```

---

### GET /api/stats

Get pipeline statistics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `batch_id` | string | - | Filter by batch ID |

**Response:**

```json
{
  "total_images": 1000,
  "pending": 50,
  "preprocessing": 0,
  "preprocessed": 10,
  "decoding_primary": 5,
  "decoded_primary": 600,
  "decoding_fallback": 2,
  "decoded_fallback": 150,
  "manual_review": 20,
  "decoded_manual": 43,
  "failed": 120,
  "success_rate": 79.3
}
```

---

## Error Responses

All endpoints may return these error responses:

### 400 Bad Request

```json
{
  "detail": "Error message describing the issue"
}
```

### 404 Not Found

```json
{
  "detail": "Resource not found"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error"
}
```

---

## Authentication

Currently, the API does not require authentication. For production deployments, consider adding:

- API key authentication
- OAuth2/JWT tokens
- Azure AD integration
