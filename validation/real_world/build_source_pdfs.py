"""Generate deterministic text and image-only PDF inputs for real-world validation."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"


def text_pdf(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=letter, pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor("Synthetic validation fixture")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(54, 738, title)
    canvas.setFont("Helvetica", 10)
    y = 704
    for line in lines:
        canvas.drawString(54, y, line)
        y -= 18
    canvas.showPage()
    canvas.save()


def scanned_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    draw.rectangle((70, 70, 1205, 1580), outline="#6b7280", width=3)
    draw.text((115, 125), "SCANNED VENDOR INVOICE REGISTER", fill="#111827", font=font)
    draw.text((115, 190), "Lakeside Commons | March 2027", fill="#111827", font=font)
    draw.text((115, 275), "This page intentionally has no PDF text layer.", fill="#374151", font=font)
    draw.text((115, 340), "The application should flag it for OCR and continue.", fill="#374151", font=font)
    image.save(path, "PDF", resolution=150.0)


def main() -> None:
    harbor = SCENARIOS / "harbor_point_3q26" / "sources"
    text_pdf(
        harbor / "capital_calls_2026Q3.pdf",
        "Harbor Point Capital Activity",
        [
            "Harbor Point Holdings LLC",
            "New Capital Call",
            "Title  Due Date  Status  Amount",
            "3Q26 Working Capital  08/15/2026  Settled  $500,000.00",
            "Total Called $12,500,000.00",
            "Callable Capital $2,500,000.00",
        ],
    )
    text_pdf(
        harbor / "cash_distributions_2026Q3.pdf",
        "Harbor Point Distribution Activity",
        [
            "Harbor Point Holdings LLC",
            "New Distribution",
            "Title  Date  Status  Gross Amount  Net Amount",
            "3Q26 Operating Distribution  09/20/2026  Settled  $125,000.00  $125,000.00",
        ],
    )

    lakeside = SCENARIOS / "lakeside_commons_1q27" / "sources"
    text_pdf(
        lakeside / "capital_activity.pdf",
        "Lakeside Commons Capital Activity",
        [
            "Lakeside Commons Owner LLC",
            "New Capital Call",
            "Title  Due Date  Status  Amount",
            "1Q27 Amenity Program  02/15/2027  Open  $275,000.00",
            "Total Called $13,700,000.00",
            "Contributed capital activity through March 2027",
        ],
    )
    scanned_pdf(lakeside / "scanned_vendor_report.pdf")


if __name__ == "__main__":
    main()
