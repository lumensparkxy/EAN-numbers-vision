"""
CLI tool to find detections by source filename.

Usage:
    poetry run python -m tools.find_detection.main --filename my_product.jpg
"""

import argparse
import json

from src.db import get_database, DetectionRepository


def find_by_filename(filename: str, output_format: str = "table") -> None:
    """Find and display detections for a given source filename."""
    db = get_database()
    detection_repo = DetectionRepository(db)

    detections = detection_repo.find_by_source_filename(filename)

    if not detections:
        print(f"No detections found for filename: {filename}")
        return

    if output_format == "json":
        results = []
        for d in detections:
            results.append({
                "code": d.code,
                "symbology": d.symbology.value if d.symbology else None,
                "source": d.source.value if d.source else None,
                "checksum_valid": d.checksum_valid,
                "product_found": d.product_found,
                "image_id": d.image_id,
                "batch_id": d.batch_id,
            })
        print(json.dumps(results, indent=2))
    else:
        # Table format
        print(f"\nDetections for: {filename}")
        print("-" * 80)
        print(f"{'Code':<15} {'Symbology':<10} {'Source':<15} {'Valid':<6} {'Product':<8}")
        print("-" * 80)

        for d in detections:
            valid = "✓" if d.checksum_valid else "✗"
            product = "✓" if d.product_found else "✗"
            symbology = d.symbology.value if d.symbology else "N/A"
            source = d.source.value if d.source else "N/A"

            print(f"{d.code:<15} {symbology:<10} {source:<15} {valid:<6} {product:<8}")

        print("-" * 80)
        print(f"Total: {len(detections)} detection(s)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Find detections by source filename"
    )
    parser.add_argument(
        "--filename", "-f",
        required=True,
        help="Source filename to search for"
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)"
    )

    args = parser.parse_args()
    find_by_filename(args.filename, args.format)


if __name__ == "__main__":
    main()
