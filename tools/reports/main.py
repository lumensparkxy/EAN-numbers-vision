"""
CLI tool to generate reports from processed images.

Usage:
    poetry run python -m tools.reports.main --batch-id my_batch
    poetry run python -m tools.reports.main --batch-id my_batch --format markdown
    poetry run python -m tools.reports.main --batch-id my_batch --output report.csv
"""

import csv
import sys
from io import StringIO

import click # type: ignore

from src.db import get_database, DetectionRepository, ImageRepository
from src.models import ImageStatus


def get_report_data(batch_id: str) -> list[dict[str, str]]:
    """
    Collect report data for a batch.
    
    Returns a list of dicts with source_filename and code.
    For failed images, code will be "failed".
    For successful images, picks the first chosen/valid detection.
    """
    db = get_database()
    detection_repo = DetectionRepository(db)
    image_repo = ImageRepository(db)
    
    results: list[dict[str, str]] = []
    seen_filenames: set[str] = set()
    
    # Get successful detections: chosen=True first, then non-rejected/non-ambiguous
    # CosmosDB doesn't support complex $sort in aggregation, so we query and process in Python
    
    # First try to get chosen detections
    chosen_cursor = detection_repo.collection.find({
        "batch_id": batch_id,
        "chosen": True,
    })
    
    for doc in chosen_cursor:
        source_filename = doc.get("source_filename")
        if source_filename and source_filename not in seen_filenames:
            results.append({
                "source_filename": source_filename,
                "code": doc["code"],
            })
            seen_filenames.add(source_filename)
    
    # Then get non-rejected, non-ambiguous detections for remaining files
    valid_cursor = detection_repo.collection.find({
        "batch_id": batch_id,
        "rejected": {"$ne": True},
        "ambiguous": {"$ne": True},
    })
    
    for doc in valid_cursor:
        source_filename = doc.get("source_filename")
        if source_filename and source_filename not in seen_filenames:
            results.append({
                "source_filename": source_filename,
                "code": doc["code"],
            })
            seen_filenames.add(source_filename)
    
    # Get failed images
    failed_images = image_repo.find_by_status(
        ImageStatus.FAILED, 
        limit=10000,  # Large limit to get all
        batch_id=batch_id,
    )
    
    for image in failed_images:
        if image.source_filename and image.source_filename not in seen_filenames:
            results.append({
                "source_filename": image.source_filename,
                "code": "failed",
            })
            seen_filenames.add(image.source_filename)
    
    # Sort by source_filename for consistent output
    results.sort(key=lambda x: x["source_filename"])
    
    return results


def format_csv(data: list[dict[str, str]]) -> str:
    """Format data as CSV."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["source_filename", "code"])
    for row in data:
        writer.writerow([row["source_filename"], row["code"]])
    return output.getvalue()


def format_markdown(data: list[dict[str, str]]) -> str:
    """Format data as markdown table."""
    lines = [
        "| source_filename | code |",
        "|-----------------|------|",
    ]
    for row in data:
        lines.append(f"| {row['source_filename']} | {row['code']} |")
    return "\n".join(lines)


@click.command()
@click.option(
    "--batch-id", "-b",
    required=True,
    help="Batch ID to generate report for",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file path (defaults to stdout)",
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["csv", "markdown"]),
    default="csv",
    help="Output format (default: csv)",
)
def main(batch_id: str, output: str | None, output_format: str) -> None:
    """Generate a report of processed images with their detected codes."""
    data = get_report_data(batch_id)
    
    if not data:
        click.echo(f"No data found for batch: {batch_id}", err=True)
        sys.exit(1)
    
    if output_format == "csv":
        content = format_csv(data)
    else:
        content = format_markdown(data)
    
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Report written to: {output}")
    else:
        click.echo(content)


if __name__ == "__main__":
    main()
