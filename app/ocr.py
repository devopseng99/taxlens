"""Azure Document Intelligence integration for TaxLens."""

import os
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential


def get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ["AZURE_DOCAI_ENDPOINT"]
    key = os.environ["AZURE_DOCAI_KEY"]
    return DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))


async def analyze_document(file_path: Path, model_id: str = "prebuilt-tax.us") -> dict:
    """Send document to Azure Document Intelligence and return structured fields.

    Args:
        file_path: Path to the document file (PDF or image)
        model_id: Azure model ID (e.g., prebuilt-tax.us.w2, prebuilt-tax.us.1099Combo)

    Returns:
        dict with keys: fields (extracted data), confidence (avg), pages (count), raw (full response)
    """
    client = get_client()

    with open(file_path, "rb") as f:
        doc_bytes = f.read()

    # Determine content type
    suffix = file_path.suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    content_type = content_types.get(suffix, "application/octet-stream")

    # Analyze
    poller = client.begin_analyze_document(
        model_id=model_id,
        body=doc_bytes,
        content_type=content_type,
    )
    result = poller.result()

    # Extract fields from first document (with nested object/array support)
    fields = {}
    confidence_sum = 0.0
    field_count = 0

    def extract_field(field):
        """Recursively extract field value, handling objects and arrays."""
        ft = field.type if hasattr(field, "type") else None

        if ft == "object" and hasattr(field, "value_object") and field.value_object:
            sub = {}
            for k, v in field.value_object.items():
                sub[k] = extract_field(v)
            return {"value": sub, "confidence": field.confidence, "type": "object"}

        if ft == "array" and hasattr(field, "value_array") and field.value_array:
            items = [extract_field(item) for item in field.value_array]
            return {"value": items, "confidence": field.confidence, "type": "array"}

        val = field.content if hasattr(field, "content") and field.content else (
            str(field.value) if hasattr(field, "value") and field.value is not None else None
        )
        return {"value": val, "confidence": field.confidence, "type": ft}

    doc_type = None
    if result.documents:
        doc = result.documents[0]
        doc_type = doc.doc_type if hasattr(doc, "doc_type") else None
        for name, field in (doc.fields or {}).items():
            extracted = extract_field(field)
            fields[name] = extracted
            if extracted.get("confidence"):
                confidence_sum += extracted["confidence"]
                field_count += 1

    avg_confidence = confidence_sum / field_count if field_count > 0 else 0.0

    return {
        "fields": fields,
        "confidence": round(avg_confidence, 4),
        "pages": len(result.pages) if result.pages else 0,
        "doc_type": doc_type,
        "raw": {
            "model_id": result.model_id,
            "api_version": result.api_version if hasattr(result, "api_version") else None,
            "document_count": len(result.documents) if result.documents else 0,
            "page_count": len(result.pages) if result.pages else 0,
            "doc_type": doc_type,
            "fields": fields,
        },
    }
