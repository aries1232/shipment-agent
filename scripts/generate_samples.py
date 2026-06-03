"""Generate synthetic trade documents so the pipeline is demoable without real PDFs.

Produces one clean Commercial Invoice (should auto-approve) and one with several
discrepancies against the ACME Imports rule set (should trigger an amendment).
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

CLEAN_INVOICE = {
    "filename": "commercial_invoice_clean.pdf",
    "invoice_number": "INV-2026-0042",
    "consignee": "ACME Imports Ltd",
    "hs_code": "8471.30.00",
    "port_of_loading": "Shanghai, China",
    "port_of_discharge": "Rotterdam, Netherlands",
    "incoterms": "FOB Shanghai",
    "description": "Laptop computers, 14-inch, 1200 units",
    "gross_weight": "12,500 KG",
}

DISCREPANT_INVOICE = {
    "filename": "commercial_invoice_discrepant.pdf",
    "invoice_number": "2026-0099",  # missing required INV- prefix
    "consignee": "ACME Trading LLC",  # wrong legal entity
    "hs_code": "8471",  # too short for a valid HS code
    "port_of_loading": "Mumbai, India",  # not an approved origin port
    "port_of_discharge": "Rotterdam, Netherlands",
    "incoterms": "DDP Rotterdam",  # not an allowed Incoterm
    "description": "Laptop computers, 14-inch, 1200 units",
    "gross_weight": "27,500 LBS",  # wrong unit of measure
}


def _render(doc: dict) -> None:
    styles = getSampleStyleSheet()
    pdf = SimpleDocTemplate(str(SAMPLES_DIR / doc["filename"]), pagesize=A4)

    rows = [
        ("Invoice No.", doc["invoice_number"]),
        ("Consignee", doc["consignee"]),
        ("HS Code", doc["hs_code"]),
        ("Port of Loading", doc["port_of_loading"]),
        ("Port of Discharge", doc["port_of_discharge"]),
        ("Incoterms", doc["incoterms"]),
        ("Description of Goods", doc["description"]),
        ("Gross Weight", doc["gross_weight"]),
    ]
    table = Table(rows, colWidths=[150, 320])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ]
        )
    )

    pdf.build(
        [
            Paragraph("COMMERCIAL INVOICE", styles["Title"]),
            Paragraph("Global Freight Forwarders Pvt. Ltd.", styles["Normal"]),
            Spacer(1, 24),
            table,
        ]
    )


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    for doc in (CLEAN_INVOICE, DISCREPANT_INVOICE):
        _render(doc)
        print(f"wrote {SAMPLES_DIR / doc['filename']}")


if __name__ == "__main__":
    main()
