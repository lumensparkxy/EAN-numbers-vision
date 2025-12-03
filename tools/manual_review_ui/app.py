"""
Manual Review UI - FastAPI application for reviewing ambiguous barcode detections.

Provides a web interface for operators to:
- View images requiring manual review
- See candidate barcode detections
- Confirm or reject detections
- Mark images as resolved
"""

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from src.config import get_settings
from src.db import DetectionRepository, ImageRepository, ProductRepository, get_database
from src.models import ImageStatus
from src.storage import get_blob_client

app = FastAPI(
    title="EAN Extraction - Manual Review",
    description="Review and resolve ambiguous barcode detections",
    version="1.0.0",
)


# Request/Response models
class ReviewDecision(BaseModel):
    """Decision for a manual review."""

    detection_id: str | None = None  # ID of chosen detection (None if no barcode)
    action: str  # "choose", "no_barcode", "skip"
    reviewer: str | None = None


class ImageSummary(BaseModel):
    """Summary of an image for listing."""

    image_id: str
    batch_id: str
    external_id: str | None
    status: str
    detection_count: int
    created_at: datetime


class DetectionInfo(BaseModel):
    """Detection information for review."""

    id: str
    code: str
    symbology: str
    source: str
    confidence: float | None
    checksum_valid: bool
    product_found: bool
    product_name: str | None = None


class ImageDetail(BaseModel):
    """Detailed image information for review."""

    image_id: str
    batch_id: str
    external_id: str | None
    image_url: str
    detections: list[DetectionInfo]


class StatsResponse(BaseModel):
    """Pipeline statistics."""

    total_images: int
    pending: int
    processing: int
    decoded: int
    manual_review: int
    failed: int
    success_rate: float


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def home():
    """Redirect to review page."""
    return RedirectResponse(url="/review")


@app.get("/review", response_class=HTMLResponse)
async def review_page():
    """Render the manual review page."""
    return get_review_html()


@app.get("/api/images/review")
async def list_review_images(
    limit: int = Query(50, ge=1, le=100),
    batch_id: str | None = None,
) -> list[ImageSummary]:
    """List images pending manual review."""
    db = get_database()
    image_repo = ImageRepository(db)

    images = image_repo.find_for_manual_review(limit=limit)

    if batch_id:
        images = [img for img in images if img.batch_id == batch_id]

    return [
        ImageSummary(
            image_id=img.image_id,
            batch_id=img.batch_id,
            external_id=img.external_id,
            status=img.status.value,
            detection_count=img.detection_count,
            created_at=img.created_at,
        )
        for img in images
    ]


@app.get("/api/images/{image_id}")
async def get_image_detail(image_id: str) -> ImageDetail:
    """Get detailed information about an image for review."""
    db = get_database()
    image_repo = ImageRepository(db)
    detection_repo = DetectionRepository(db)
    product_repo = ProductRepository(db)
    blob_client = get_blob_client()

    image = image_repo.get_by_id(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Get detections
    detections = detection_repo.find_by_image(image_id)

    # Generate SAS URL for image
    image_path = image.final_blob_path or image.source_path
    try:
        image_url = blob_client.generate_sas_url(image_path, expiry_hours=1)
    except Exception:
        image_url = blob_client.get_blob_url(image_path)

    # Build detection info
    detection_infos = []
    for det in detections:
        product_name = None
        if det.product_found and det.product_id:
            product = product_repo.get_by_ean(det.code)
            if product:
                product_name = product.name

        detection_infos.append(
            DetectionInfo(
                id=str(det.id) if det.id else "",
                code=det.code,
                symbology=det.symbology.value,
                source=det.source.value,
                confidence=det.gemini_confidence,
                checksum_valid=det.checksum_valid,
                product_found=det.product_found,
                product_name=product_name,
            )
        )

    return ImageDetail(
        image_id=image.image_id,
        batch_id=image.batch_id,
        external_id=image.external_id,
        image_url=image_url,
        detections=detection_infos,
    )


@app.post("/api/images/{image_id}/resolve")
async def resolve_image(image_id: str, decision: ReviewDecision) -> dict[str, Any]:
    """Submit a review decision for an image."""
    db = get_database()
    image_repo = ImageRepository(db)
    detection_repo = DetectionRepository(db)
    blob_client = get_blob_client()

    image = image_repo.get_by_id(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if decision.action == "choose" and decision.detection_id:
        # Mark chosen detection
        detection_repo.mark_chosen(decision.detection_id, decision.reviewer)

        # Reject other detections
        detection_repo.reject_other_detections(
            image_id,
            decision.detection_id,
            decision.reviewer,
        )

        # Update image status
        new_status = ImageStatus.DECODED_MANUAL

    elif decision.action == "no_barcode":
        # Reject all detections
        detections = detection_repo.find_by_image(image_id)
        for det in detections:
            if det.id:
                detection_repo.mark_rejected(str(det.id), decision.reviewer)

        new_status = ImageStatus.FAILED

    elif decision.action == "skip":
        # No changes, just acknowledge
        return {"status": "skipped", "image_id": image_id}

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Move image to final location
    if image.final_blob_path:
        from src.storage import BlobPaths

        if new_status == ImageStatus.DECODED_MANUAL:
            new_path = BlobPaths.processed(image.batch_id, image.image_id)
        else:
            new_path = BlobPaths.failed(image.batch_id, image.image_id)

        try:
            blob_client.move_blob(image.final_blob_path, new_path)
            image_repo.update(image_id, {"final_blob_path": new_path})
        except Exception:
            pass  # Ignore blob move errors

    image_repo.update_status(image_id, new_status)

    return {
        "status": "resolved",
        "image_id": image_id,
        "new_status": new_status.value,
    }


@app.get("/api/stats")
async def get_stats() -> StatsResponse:
    """Get pipeline statistics."""
    db = get_database()
    image_repo = ImageRepository(db)

    stats = image_repo.get_stats()

    total = sum(stats.values())
    decoded = (
        stats.get("decoded_primary", 0)
        + stats.get("decoded_fallback", 0)
        + stats.get("decoded_manual", 0)
    )
    processing = (
        stats.get("preprocessing", 0)
        + stats.get("decoding_primary", 0)
        + stats.get("decoding_fallback", 0)
    )

    success_rate = (decoded / total * 100) if total > 0 else 0.0

    return StatsResponse(
        total_images=total,
        pending=stats.get("pending", 0),
        processing=processing,
        decoded=decoded,
        manual_review=stats.get("manual_review", 0),
        failed=stats.get("failed", 0),
        success_rate=round(success_rate, 2),
    )


def get_review_html() -> str:
    """Generate the HTML for the review page."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EAN Extraction - Manual Review</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            background: #2c3e50;
            color: white;
            padding: 20px;
            margin-bottom: 20px;
        }
        header h1 { font-size: 1.5rem; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-value { font-size: 2rem; font-weight: bold; color: #2c3e50; }
        .stat-label { font-size: 0.85rem; color: #666; }
        .review-section {
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
        }
        .image-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            max-height: calc(100vh - 250px);
            overflow-y: auto;
        }
        .image-item {
            padding: 15px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            transition: background 0.2s;
        }
        .image-item:hover { background: #f9f9f9; }
        .image-item.active { background: #e3f2fd; border-left: 3px solid #2196f3; }
        .image-item-id { font-weight: 600; font-size: 0.9rem; }
        .image-item-meta { font-size: 0.8rem; color: #666; }
        .review-panel {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
        }
        .review-panel img {
            max-width: 100%;
            max-height: 400px;
            border-radius: 4px;
            display: block;
            margin: 0 auto 20px;
        }
        .detections { margin: 20px 0; }
        .detection {
            display: flex;
            align-items: center;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .detection:hover { border-color: #2196f3; }
        .detection.selected { border-color: #4caf50; background: #e8f5e9; }
        .detection-code {
            font-family: monospace;
            font-size: 1.2rem;
            font-weight: bold;
            margin-right: 15px;
        }
        .detection-meta { font-size: 0.85rem; color: #666; }
        .detection-badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            margin-left: 10px;
        }
        .badge-valid { background: #c8e6c9; color: #2e7d32; }
        .badge-product { background: #bbdefb; color: #1565c0; }
        .actions {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary { background: #4caf50; color: white; }
        .btn-primary:hover { background: #43a047; }
        .btn-secondary { background: #9e9e9e; color: white; }
        .btn-secondary:hover { background: #757575; }
        .btn-danger { background: #f44336; color: white; }
        .btn-danger:hover { background: #d32f2f; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .loading { text-align: center; padding: 40px; color: #666; }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>🔍 EAN Extraction - Manual Review</h1>
        </div>
    </header>

    <div class="container">
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="stat-total">-</div>
                <div class="stat-label">Total Images</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-decoded">-</div>
                <div class="stat-label">Decoded</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-review">-</div>
                <div class="stat-label">Need Review</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-success">-</div>
                <div class="stat-label">Success Rate</div>
            </div>
        </div>

        <div class="review-section">
            <div class="image-list" id="image-list">
                <div class="loading">Loading images...</div>
            </div>

            <div class="review-panel" id="review-panel">
                <div class="empty-state">
                    <h3>Select an image to review</h3>
                    <p>Choose an image from the list to see its detections</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentImageId = null;
        let selectedDetectionId = null;

        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const stats = await res.json();
                document.getElementById('stat-total').textContent = stats.total_images;
                document.getElementById('stat-decoded').textContent = stats.decoded;
                document.getElementById('stat-review').textContent = stats.manual_review;
                document.getElementById('stat-success').textContent = stats.success_rate + '%';
            } catch (e) {
                console.error('Failed to load stats:', e);
            }
        }

        async function loadImages() {
            try {
                const res = await fetch('/api/images/review');
                const images = await res.json();
                const list = document.getElementById('image-list');

                if (images.length === 0) {
                    list.innerHTML = '<div class="empty-state"><p>No images pending review</p></div>';
                    return;
                }

                list.innerHTML = images.map(img => `
                    <div class="image-item" onclick="selectImage('${img.image_id}')" id="item-${img.image_id}">
                        <div class="image-item-id">${img.external_id || img.image_id.substring(0, 8)}</div>
                        <div class="image-item-meta">
                            ${img.detection_count} detection(s) • ${img.batch_id}
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load images:', e);
                document.getElementById('image-list').innerHTML = '<div class="empty-state"><p>Error loading images</p></div>';
            }
        }

        async function selectImage(imageId) {
            currentImageId = imageId;
            selectedDetectionId = null;

            // Update list selection
            document.querySelectorAll('.image-item').forEach(el => el.classList.remove('active'));
            document.getElementById('item-' + imageId)?.classList.add('active');

            try {
                const res = await fetch(`/api/images/${imageId}`);
                const image = await res.json();

                const panel = document.getElementById('review-panel');
                panel.innerHTML = `
                    <img src="${image.image_url}" alt="Product image">
                    <h3>Detected Barcodes</h3>
                    <div class="detections">
                        ${image.detections.map(det => `
                            <div class="detection" onclick="selectDetection('${det.id}')" id="det-${det.id}">
                                <span class="detection-code">${det.code}</span>
                                <div class="detection-meta">
                                    ${det.symbology} • ${det.source}
                                    ${det.confidence ? ` • ${(det.confidence * 100).toFixed(0)}%` : ''}
                                </div>
                                ${det.checksum_valid ? '<span class="detection-badge badge-valid">✓ Valid</span>' : ''}
                                ${det.product_found ? '<span class="detection-badge badge-product">📦 In Catalog</span>' : ''}
                            </div>
                        `).join('')}
                    </div>
                    <div class="actions">
                        <button class="btn btn-primary" onclick="confirmSelection()" id="btn-confirm" disabled>
                            ✓ Confirm Selected
                        </button>
                        <button class="btn btn-danger" onclick="markNoBarcode()">
                            ✗ No Barcode
                        </button>
                        <button class="btn btn-secondary" onclick="skipImage()">
                            Skip
                        </button>
                    </div>
                `;
            } catch (e) {
                console.error('Failed to load image:', e);
            }
        }

        function selectDetection(detectionId) {
            selectedDetectionId = detectionId;
            document.querySelectorAll('.detection').forEach(el => el.classList.remove('selected'));
            document.getElementById('det-' + detectionId)?.classList.add('selected');
            document.getElementById('btn-confirm').disabled = false;
        }

        async function confirmSelection() {
            if (!currentImageId || !selectedDetectionId) return;
            await submitDecision('choose', selectedDetectionId);
        }

        async function markNoBarcode() {
            if (!currentImageId) return;
            await submitDecision('no_barcode', null);
        }

        async function skipImage() {
            if (!currentImageId) return;
            await submitDecision('skip', null);
        }

        async function submitDecision(action, detectionId) {
            try {
                const res = await fetch(`/api/images/${currentImageId}/resolve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: action,
                        detection_id: detectionId,
                        reviewer: 'web_ui'
                    })
                });

                if (res.ok) {
                    loadImages();
                    loadStats();
                    document.getElementById('review-panel').innerHTML = `
                        <div class="empty-state">
                            <h3>✓ Decision submitted</h3>
                            <p>Select another image to continue</p>
                        </div>
                    `;
                }
            } catch (e) {
                console.error('Failed to submit decision:', e);
                alert('Failed to submit decision');
            }
        }

        // Initialize
        loadStats();
        loadImages();

        // Auto-refresh stats every 30 seconds
        setInterval(loadStats, 30000);
    </script>
</body>
</html>
"""


def main():
    """Run the manual review UI server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "tools.manual_review_ui.app:app",
        host=settings.review_ui_host,
        port=settings.review_ui_port,
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    main()
