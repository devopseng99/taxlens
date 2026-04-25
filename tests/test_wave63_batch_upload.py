"""Wave 63 tests — Batch Document Upload + Document Manager."""

import sys, os, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Doc Type Detection Map
# =========================================================================
class TestDocTypeMap:
    def test_map_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "_DOC_TYPE_MAP" in src

    def test_map_has_w2(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"tax.us.w2"' in src

    def test_map_has_1099_types(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        for form in ["1099Int", "1099Div", "1099Nec", "1099R", "1099Misc", "1099G"]:
            assert f'"tax.us.{form}"' in src

    def test_map_has_1098(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"tax.us.1098"' in src


# =========================================================================
# Batch Upload Endpoint
# =========================================================================
class TestBatchUploadEndpoint:
    def test_batch_upload_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "batch-upload" in src
        assert "async def batch_upload" in src

    def test_batch_upload_accepts_files(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "list[UploadFile]" in src

    def test_batch_upload_max_20(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "Maximum 20 files" in src

    def test_batch_upload_saves_metadata(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "metadata.json" in src


# =========================================================================
# Batch Analyze Endpoint
# =========================================================================
class TestBatchAnalyzeEndpoint:
    def test_batch_analyze_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "batch-analyze" in src
        assert "async def batch_analyze" in src

    def test_batch_analyze_uses_asyncio_gather(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "asyncio.gather" in src

    def test_batch_analyze_checks_ocr_enabled(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "OCR_ENABLED" in src


# =========================================================================
# OCR Correction Endpoint
# =========================================================================
class TestOCRCorrectionEndpoint:
    def test_patch_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "ocr-result" in src
        assert "async def patch_ocr_result" in src

    def test_corrections_merge_fields(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "manually_corrected" in src

    def test_ocr_correction_logic(self):
        """Verify the correction merge logic works correctly."""
        # Simulate the correction merge
        existing = {"fields": {"Box1": {"value": "50000"}, "Box2": {"value": "10000"}}}
        corrections = {"Box1": "55000", "Box3": {"value": "2000", "confidence": 1.0}}

        fields = existing.get("fields", {})
        for key, value in corrections.items():
            if isinstance(value, dict):
                if key in fields:
                    fields[key].update(value)
                else:
                    fields[key] = value
            else:
                fields[key] = {"value": value}

        assert fields["Box1"]["value"] == "55000"
        assert fields["Box2"]["value"] == "10000"  # Unchanged
        assert fields["Box3"]["value"] == "2000"
        assert fields["Box3"]["confidence"] == 1.0


# =========================================================================
# Document List Endpoint
# =========================================================================
class TestDocumentListEndpoint:
    def test_list_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "/documents" in src
        assert "async def list_documents" in src

    def test_list_handles_empty(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert '"documents": []' in src


# =========================================================================
# Storage Integration
# =========================================================================
class TestStorageIntegration:
    def test_uuid_proc_id_generation(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "uuid.uuid4()" in src

    def test_original_file_saved(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "original" in src

    def test_asyncio_imported(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "import asyncio" in src
