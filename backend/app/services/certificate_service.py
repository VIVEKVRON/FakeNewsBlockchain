"""
backend/app/services/certificate_service.py
Generates downloadable, cryptographically verifiable PDF certificates with embedded QR codes
for confirmed blockchain-anchored verification records.

STRICT RULE:
Certificates are ONLY issued when an actual successful Ethereum transaction receipt
and verified on-chain anchor exist.
"""

import io
import socket
import qrcode
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from PIL import Image

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from backend.app.config import get_settings
from backend.app.database.repository import get_verification_record
from backend.app.services.blockchain_service import get_blockchain_service

logger = logging.getLogger(__name__)


def get_public_verification_url(verification_id: str, record_hash: str) -> str:
    """
    Builds the verification URL embedded into certificate QR codes.

    ACCESSIBILITY & NETWORKING RULES:
    1. Production Deployment:
       Requires configuring `PUBLIC_VERIFICATION_BASE_URL` in `.env` to a publicly reachable
       HTTPS URL (e.g. 'https://verify.fakenewsblockchain.org/verify-certificate').
    2. Local Development & LAN Testing:
       If `PUBLIC_VERIFICATION_BASE_URL` is empty, resolves the host machine's private IPv4
       address (RFC 1918, e.g. '192.168.x.x') so mobile phones and laptops on the SAME local Wi-Fi
       can scan and test the QR code during demo.
    
    IMPORTANT NOTICE:
    Private IPv4 addresses (192.168.x.x, 10.x.x.x, 172.16-31.x.x) are strictly LAN-only.
    They do not provide public internet accessibility without an internet-facing reverse proxy or public domain.
    """
    settings = get_settings()
    base_url = settings.PUBLIC_VERIFICATION_BASE_URL.strip().rstrip("/") if settings.PUBLIC_VERIFICATION_BASE_URL else ""
    
    if not base_url:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            base_url = f"http://{local_ip}:5173/verify-certificate"
        except Exception:
            base_url = "http://192.168.1.102:5173/verify-certificate"

    return f"{base_url}?id={verification_id}&hash={record_hash}"


def generate_certificate_qr_code(verification_id: str, record_hash: str) -> io.BytesIO:
    """Generates QR code linking to public verification page."""
    verify_url = get_public_verification_url(verification_id, record_hash)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_verification_pdf(verification_id: str) -> bytes:
    """
    Generates an official PDF certificate for a verified and anchored record.
    Enforces that the record is confirmed on-chain before generating.
    """
    record = get_verification_record(verification_id)
    if not record:
        raise ValueError(f"Verification record '{verification_id}' does not exist.")

    # Strict check: Must have confirmed on-chain transaction
    if not record.get("transaction_hash") or record.get("blockchain_status") != "confirmed":
        raise ValueError(
            f"Cannot issue certificate: Record '{verification_id}' is not confirmed on the blockchain. "
            "Certificates are strictly issued only for confirmed blockchain-anchored records with on-chain receipts."
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CertTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=1  # Center
    )

    subtitle_style = ParagraphStyle(
        "CertSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2563eb"),
        alignment=1
    )

    body_style = ParagraphStyle(
        "CertBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155")
    )

    code_style = ParagraphStyle(
        "CertCode",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a")
    )

    disclaimer_style = ParagraphStyle(
        "CertDisclaimer",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748b"),
        alignment=1
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("FAKENEWSBLOCKCHAIN", subtitle_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("CERTIFICATE OF VERIFICATION & CRYPTOGRAPHIC INTEGRITY", title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Ethereum Sepolia Cryptographic Anchoring Proof", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=12))

    # 2. Verdict & Confidence Badge Table
    verdict = record.get("verdict", "UNVERIFIED")
    confidence = float(record.get("confidence_score", 0.0))
    
    verdict_colors = {
        "GENUINE": colors.HexColor("#059669"),
        "LIKELY_GENUINE": colors.HexColor("#059669"),
        "FAKE": colors.HexColor("#dc2626"),
        "LIKELY_FAKE": colors.HexColor("#dc2626"),
        "MISLEADING": colors.HexColor("#d97706"),
        "PARTIALLY_TRUE": colors.HexColor("#0284c7"),
        "OUTDATED": colors.HexColor("#7c3aed"),
        "UNVERIFIED": colors.HexColor("#64748b"),
    }
    v_color = verdict_colors.get(verdict, colors.HexColor("#2563eb"))

    verdict_p = Paragraph(
        f"<b>VERDICT:</b> <font color='{v_color.hexval()}'><b>{verdict}</b></font> &nbsp;|&nbsp; "
        f"<b>CONFIDENCE:</b> <b>{confidence * 100:.1f}%</b>",
        ParagraphStyle("VerdictBadge", fontName="Helvetica", fontSize=12, alignment=1)
    )

    verdict_table = Table([[verdict_p]], colWidths=[540])
    verdict_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 12))

    # 3. Content Details
    content_text = record.get("original_content", "")
    if len(content_text) > 350:
        content_text = content_text[:347] + "..."

    content_table_data = [
        [Paragraph("<b>Verification ID:</b>", body_style), Paragraph(record.get("verification_id", ""), code_style)],
        [Paragraph("<b>Content Type:</b>", body_style), Paragraph(record.get("content_type", "").upper(), body_style)],
        [Paragraph("<b>Verification Timestamp:</b>", body_style), Paragraph(record.get("created_at", ""), body_style)],
        [Paragraph("<b>Verified Claim / Content:</b>", body_style), Paragraph(content_text, body_style)],
        [Paragraph("<b>Grounding Explanation:</b>", body_style), Paragraph(record.get("explanation", ""), body_style)],
    ]

    content_table = Table(content_table_data, colWidths=[130, 410])
    content_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
    ]))
    story.append(content_table)
    story.append(Spacer(1, 12))

    # 4. Cryptographic Proof & Blockchain Details with QR Code
    qr_buf = generate_certificate_qr_code(
        record.get("verification_id", ""),
        record.get("record_hash", "")
    )
    qr_img = RLImage(qr_buf, width=1.4*inch, height=1.4*inch)

    blockchain_data = [
        [Paragraph("<b>Canonical Record SHA-256:</b>", body_style), Paragraph(record.get("record_hash", ""), code_style)],
        [Paragraph("<b>Blockchain Network:</b>", body_style), Paragraph(f"Ethereum {record.get('network', 'sepolia').capitalize()} (Chain ID: {record.get('chain_id', 11155111)})", body_style)],
        [Paragraph("<b>Smart Contract Address:</b>", body_style), Paragraph(record.get("contract_address", ""), code_style)],
        [Paragraph("<b>Transaction Hash:</b>", body_style), Paragraph(record.get("transaction_hash", ""), code_style)],
        [Paragraph("<b>Block Number / Timestamp:</b>", body_style), Paragraph(f"#{record.get('block_number', '')} &nbsp;({record.get('block_datetime', '')})", body_style)],
        [Paragraph("<b>Submitter Address:</b>", body_style), Paragraph(record.get("submitter_address", ""), code_style)],
        [Paragraph("<b>Etherscan Verification Link:</b>", body_style), Paragraph(record.get("etherscan_url", ""), code_style)],
    ]

    blockchain_table = Table(blockchain_data, colWidths=[140, 270])
    blockchain_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
    ]))

    proof_combined = Table([[blockchain_table, qr_img]], colWidths=[410, 130])
    proof_combined.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'CENTER'),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(proof_combined)
    story.append(Spacer(1, 14))

    # 5. Epistemological Principle & Disclaimer Footer
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#cbd5e1"), spaceAfter=8))
    story.append(Paragraph(
        "<b>EPISTEMOLOGICAL INTEGRITY NOTICE:</b> This certificate provides mathematical cryptographic proof that this "
        "exact AI verification record existed at the recorded Ethereum block height and has not been altered or tampered "
        "with (anti-tampering and non-repudiation). Blockchain anchoring proves record integrity and authenticity; it is "
        "not empirical proof that the underlying real-world news claim or model output is infallible ground truth.",
        disclaimer_style
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Issued by FakeNewsBlockchain Verification Authority • Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        disclaimer_style
    ))

    # Build document
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
