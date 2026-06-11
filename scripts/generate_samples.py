"""Generate synthetic trade documents so the pipeline is demoable without real PDFs.

Part 1: one clean and one discrepant Commercial Invoice (single-doc).
Part 2: shipment emails exercising multiple outcomes and two customers —
  ACME and Globex Trading are validated against their own rule sets.
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
SHIPMENTS_DIR = SAMPLES_DIR / "shipments"
SH_GLOBAL = "Shanghai Global Manufacturing Co."
BUSAN = "Busan Components Ltd"

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

# One fact set, shared by all docs in a clean shipment -> cross-checks agree, rules pass.
CLEAN = {
    "consignee": "ACME Imports Ltd",
    "shipper": SH_GLOBAL,
    "hs_code": "8471.30.00",
    "incoterms": "FOB Shanghai",
    "port_of_loading": "Shanghai, China",
    "port_of_discharge": "Rotterdam, Netherlands",
    "description": "Laptop computers, 14-inch, 1200 units",
    "gross_weight": "12,500 KG",
    "net_weight": "11,200 KG",
    "packages": "60 cartons",
    "country_of_origin": "China",
    "invoice_number": "INV-2026-0042",
    "invoice_date": "2026-05-30",
    "total_value": "USD 540,000.00",
}

# Messy shipment: a shared base with per-document divergences seeded in.
_MESSY_BASE = {**CLEAN}
MESSY_INVOICE = {
    **_MESSY_BASE,
    "invoice_number": "2026-0099",  # rule break: missing INV- prefix
    "incoterms": "DDP Rotterdam",  # rule break: not an allowed Incoterm
    "gross_weight": "27,500 LBS",  # rule break: wrong unit
}
MESSY_BOL = {
    **_MESSY_BASE,
    "consignee": "ACME Trading LLC",  # cross-doc: consignee disagrees with the others
    "port_of_loading": "Mumbai, India",  # rule break: not an approved origin port
}
MESSY_PACKING = {**_MESSY_BASE, "hs_code": "8528.72.00"}  # cross-doc: HS code disagrees

# Clean variant (different goods) -> auto-approve.
LEDS = {
    **CLEAN,
    "hs_code": "8528.52.00",
    "incoterms": "CIF Shanghai",
    "description": "LED monitors, 27-inch, 800 units",
    "gross_weight": "9,800 KG",
    "net_weight": "9,100 KG",
    "packages": "40 pallets",
    "invoice_number": "INV-2026-0061",
    "invoice_date": "2026-06-02",
    "total_value": "USD 320,000.00",
}

# Second customer, validated against rules/globex_trading.yaml -> auto-approve.
GLOBEX = {
    "consignee": "Globex Trading GmbH",
    "shipper": BUSAN,
    "hs_code": "8542.31.00",
    "incoterms": "CIF Busan",
    "port_of_loading": "Busan, South Korea",
    "port_of_discharge": "Hamburg, Germany",
    "description": "Semiconductor wafers, 300mm, 5000 units",
    "gross_weight": "6,400 KG",
    "net_weight": "6,000 KG",
    "packages": "25 crates",
    "country_of_origin": "South Korea",
    "invoice_number": "GBX-2026-0007",
    "invoice_date": "2026-05-28",
    "total_value": "USD 1,250,000.00",
}

GLOBEX_MESSY_INVOICE = {
    **GLOBEX,
    "invoice_number": "2026-0008",  # rule break: missing GBX- prefix
    "incoterms": "FOB Busan",  # rule break: not an allowed Globex Incoterm
    "gross_weight": "14,100 LBS",  # rule break: wrong unit
}
GLOBEX_MESSY_BOL = {
    **GLOBEX,
    "consignee": "Globex Trading LLC",  # cross-doc: consignee disagrees with the others
    "port_of_loading": "Shanghai, China",  # rule break: not an approved Globex origin port
}
GLOBEX_MESSY_PACKING = {
    **GLOBEX,
    "hs_code": "8471.30.00",  # cross-doc: HS code disagrees
}


def _render(path: Path, title: str, org: str, rows: list[tuple[str, str]]) -> None:
    styles = getSampleStyleSheet()
    pdf = SimpleDocTemplate(str(path), pagesize=A4)
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
    pdf.build([Paragraph(title, styles["Title"]), Paragraph(org, styles["Normal"]), Spacer(1, 24), table])


def _invoice_rows(doc: dict) -> list[tuple[str, str]]:
    return [
        ("Invoice No.", doc["invoice_number"]),
        ("Consignee", doc["consignee"]),
        ("HS Code", doc["hs_code"]),
        ("Port of Loading", doc["port_of_loading"]),
        ("Port of Discharge", doc["port_of_discharge"]),
        ("Incoterms", doc["incoterms"]),
        ("Description of Goods", doc["description"]),
        ("Gross Weight", doc["gross_weight"]),
    ]


def _bol_rows(f: dict) -> list[tuple[str, str]]:
    return [
        ("Shipper", f["shipper"]),
        ("Consignee", f["consignee"]),
        ("Port of Loading", f["port_of_loading"]),
        ("Port of Discharge", f["port_of_discharge"]),
        ("Description of Goods", f["description"]),
        ("HS Code", f["hs_code"]),
        ("Gross Weight", f["gross_weight"]),
        ("Country of Origin", f["country_of_origin"]),
    ]


def _full_invoice_rows(f: dict) -> list[tuple[str, str]]:
    return [
        ("Invoice No.", f["invoice_number"]),
        ("Invoice Date", f["invoice_date"]),
        ("Shipper", f["shipper"]),
        ("Consignee", f["consignee"]),
        ("HS Code", f["hs_code"]),
        ("Incoterms", f["incoterms"]),
        ("Port of Loading", f["port_of_loading"]),
        ("Port of Discharge", f["port_of_discharge"]),
        ("Description of Goods", f["description"]),
        ("Gross Weight", f["gross_weight"]),
        ("Country of Origin", f["country_of_origin"]),
        ("Total Value", f["total_value"]),
    ]


def _packing_rows(f: dict) -> list[tuple[str, str]]:
    return [
        ("Shipper", f["shipper"]),
        ("Consignee", f["consignee"]),
        ("Description of Goods", f["description"]),
        ("HS Code", f["hs_code"]),
        ("Gross Weight", f["gross_weight"]),
        ("Net Weight", f["net_weight"]),
        ("Packages", f["packages"]),
        ("Country of Origin", f["country_of_origin"]),
    ]


def _bol(f):
    return ("bill_of_lading.pdf", "BILL OF LADING", _bol_rows(f))


def _invoice(f):
    return ("commercial_invoice.pdf", "COMMERCIAL INVOICE", _full_invoice_rows(f))


def _packing(f):
    return ("packing_list.pdf", "PACKING LIST", _packing_rows(f))


def _write_shipment(name, *, customer, sender, shipper, subject, body, docs) -> None:
    out = SHIPMENTS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    for filename, title, rows in docs:
        _render(out / filename, title, shipper, rows)
    email = {
        "shipment_id": f"SAMPLE-{name.upper()}",
        "sender": sender,
        "customer": customer,
        "subject": subject,
        "body": body,
    }
    (out / "_email.json").write_text(json.dumps(email, indent=2), encoding="utf-8")
    print(f"wrote shipment {out}")


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    for doc in (CLEAN_INVOICE, DISCREPANT_INVOICE):
        _render(SAMPLES_DIR / doc["filename"], "COMMERCIAL INVOICE", "Global Freight Forwarders Pvt. Ltd.", _invoice_rows(doc))
        print(f"wrote {SAMPLES_DIR / doc['filename']}")

    acme = {"customer": "ACME Imports Ltd", "sender": "exports@shanghaiglobal.example", "shipper": SH_GLOBAL}

    _write_shipment(
        "clean", **acme,
        subject="Shipment docs - PO 4512 (Rotterdam)",
        body="Hi CG team, please find attached the Bill of Lading, Commercial Invoice and Packing "
        "List for PO-4512 to Rotterdam. Kind regards, Shanghai Global.",
        docs=[_bol(CLEAN), _invoice(CLEAN), _packing(CLEAN)],
    )
    _write_shipment(
        "messy", **acme,
        subject="Shipment docs - PO 4513 (Rotterdam)",
        body="Hi CG, attached are the documents for PO-4513. Please process at the earliest. "
        "Regards, Shanghai Global.",
        docs=[_bol(MESSY_BOL), _invoice(MESSY_INVOICE), _packing(MESSY_PACKING)],
    )
    _write_shipment(
        "clean_leds", **acme,
        subject="Shipment docs - PO 4514 (Rotterdam)",
        body="Hi CG team, documents for PO-4514 (LED monitors) are attached. Thanks, Shanghai Global.",
        docs=[_bol(LEDS), _invoice(LEDS), _packing(LEDS)],
    )
    _write_shipment(
        "no_invoice", **acme,
        subject="Shipment docs - PO 4515 (invoice to follow)",
        body="Hi CG, attached are the Bill of Lading and Packing List for PO-4515. The commercial "
        "invoice will follow separately. Regards, Shanghai Global.",
        docs=[_bol(CLEAN), _packing(CLEAN)],
    )
    _write_shipment(
        "globex",
        customer="Globex Trading",
        sender="exports@busancomponents.example",
        shipper=BUSAN,
        subject="Shipment docs - PO 7781 (Hamburg)",
        body="Dear CG, please find attached the documents for PO-7781 to Hamburg. "
        "Best regards, Busan Components.",
        docs=[_bol(GLOBEX), _invoice(GLOBEX), _packing(GLOBEX)],
    )
    _write_shipment(
        "globex_messy",
        customer="Globex Trading",
        sender="exports@busancomponents.example",
        shipper=BUSAN,
        subject="Shipment docs - PO 7782 (Hamburg)",
        body="Dear CG, attached are the documents for PO-7782 to Hamburg. "
        "Please review and confirm. Best regards, Busan Components.",
        docs=[
            _bol(GLOBEX_MESSY_BOL),
            _invoice(GLOBEX_MESSY_INVOICE),
            _packing(GLOBEX_MESSY_PACKING),
        ],
    )


if __name__ == "__main__":
    main()
