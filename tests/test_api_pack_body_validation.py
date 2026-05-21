"""tests/test_api_pack_body_validation.py — API rejects unsafe pack document fields."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from domain_packs.contract_reviewer.pack import ContractReviewerPack


def test_pack_run_rejects_null_byte_in_document_field(
    test_client: TestClient,
) -> None:
    def _noop_init(self, **kwargs):  # type: ignore[override]
        pass

    with (
        patch.object(ContractReviewerPack, "__init__", _noop_init),
        patch.object(ContractReviewerPack, "run_from_input"),
        patch.object(ContractReviewerPack, "close", return_value=None),
    ):
        response = test_client.post(
            "/packs/contract_reviewer/run",
            json={
                "query": "Vendor MSA",
                "contract_text": "Payment terms\x00hidden",
            },
        )

    assert response.status_code == 422
