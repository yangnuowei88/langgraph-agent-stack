"""tests/test_security_pack_body.py — Full-body validation for typed pack routes."""

from __future__ import annotations

import pytest

from control_plane.enforce import validate_pack_body
from core.security import InputValidator
from domain_packs.legal.contract_reviewer.schemas import ContractReviewerInput
from domain_packs.productivity.support_triage.schemas import SupportTriageInput


def test_validate_pack_body_rejects_oversized_document_field() -> None:
    """Document fields must respect per-field max_length via check_content_safety."""
    validator = InputValidator(max_length=2000)
    body = ContractReviewerInput.model_construct(
        query="Vendor MSA",
        contract_text="x" * 50001,
    )
    with pytest.raises(ValueError, match="exceeds maximum length"):
        validate_pack_body(body, "contract_reviewer", validator)


def test_validate_pack_body_allows_clean_document() -> None:
    validator = InputValidator(max_length=2000)
    body = ContractReviewerInput(
        query="Vendor MSA",
        contract_text="Standard payment terms net 30.",
    )
    validate_pack_body(body, "contract_reviewer", validator)


def test_validate_pack_body_rejects_null_byte_in_ticket_body() -> None:
    validator = InputValidator(max_length=8000)
    body = SupportTriageInput(
        ticket_subject="Billing issue",
        body="Customer report\x00with null byte",
    )
    with pytest.raises(ValueError, match="null bytes"):
        validate_pack_body(body, "support_triage", validator)
