"""Wave 60 tests — 1099-MISC + 1099-G OCR Parsers."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# 1099-MISC OCR Parser
# =========================================================================
class TestParse1099Misc:
    def test_basic_misc_income(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {
            "Payer": {"value": {"Name": {"value": "Acme Corp"}}},
            "Box1": {"value": "12000.00"},
            "Box2": {"value": "5000.00"},
            "Box3": {"value": "3000.00"},
            "Box4": {"value": "2000.00"},
        }
        result = parse_1099misc_from_ocr(fields)
        assert result["payer_name"] == "Acme Corp"
        assert result["rents"] == 12000.0
        assert result["royalties"] == 5000.0
        assert result["other_income"] == 3000.0
        assert result["federal_withheld"] == 2000.0
        assert result["total_income"] == 20000.0

    def test_nec_income(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {
            "Payer": {"value": "Freelance Client"},
            "Box7": {"value": "45000"},
        }
        result = parse_1099misc_from_ocr(fields)
        assert result["nonemployee_compensation"] == 45000.0
        assert result["payer_name"] == "Freelance Client"

    def test_fishing_crop_attorney(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {
            "Box5": {"value": "1000"},
            "Box9": {"value": "2000"},
            "Box10": {"value": "3000"},
        }
        result = parse_1099misc_from_ocr(fields)
        assert result["other_income"] == 6000.0  # 1000+2000+3000

    def test_medical_payments(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {
            "Box6": {"value": "8000.00"},
        }
        result = parse_1099misc_from_ocr(fields)
        assert result["medical_payments"] == 8000.0

    def test_empty_fields(self):
        from tax_engine import parse_1099misc_from_ocr
        result = parse_1099misc_from_ocr({})
        assert result["payer_name"] == "1099-MISC Payer"
        assert result["rents"] == 0.0
        assert result["royalties"] == 0.0
        assert result["other_income"] == 0.0
        assert result["total_income"] == 0.0

    def test_payer_string_format(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {"Payer": {"value": "Simple LLC"}}
        result = parse_1099misc_from_ocr(fields)
        assert result["payer_name"] == "Simple LLC"

    def test_substitute_payments(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {"Box8": {"value": "1500"}}
        result = parse_1099misc_from_ocr(fields)
        assert result["other_income"] == 1500.0

    def test_all_boxes(self):
        from tax_engine import parse_1099misc_from_ocr
        fields = {
            "Payer": {"value": "Full Payer"},
            "Box1": {"value": "10000"},
            "Box2": {"value": "5000"},
            "Box3": {"value": "2000"},
            "Box4": {"value": "3000"},
            "Box5": {"value": "1000"},
            "Box6": {"value": "500"},
            "Box7": {"value": "8000"},
            "Box8": {"value": "200"},
            "Box9": {"value": "300"},
            "Box10": {"value": "400"},
        }
        result = parse_1099misc_from_ocr(fields)
        assert result["rents"] == 10000.0
        assert result["royalties"] == 5000.0
        # other_income = Box3(2000) + Box5(1000) + Box8(200) + Box9(300) + Box10(400)
        assert result["other_income"] == 3900.0
        assert result["nonemployee_compensation"] == 8000.0
        assert result["federal_withheld"] == 3000.0
        assert result["medical_payments"] == 500.0
        # total = rents + royalties + other + fishing + nec + sub + crop + atty
        assert result["total_income"] == 26900.0


# =========================================================================
# 1099-G OCR Parser
# =========================================================================
class TestParse1099G:
    def test_basic_unemployment(self):
        from tax_engine import parse_1099g_from_ocr, UnemploymentCompensation
        fields = {
            "Box1": {"value": "12000.00"},
            "Box4": {"value": "1200.00"},
            "Box11": {"value": "600.00"},
            "Box10a": {"value": "IL"},
        }
        result = parse_1099g_from_ocr(fields)
        assert isinstance(result, UnemploymentCompensation)
        assert result.compensation == 12000.0
        assert result.federal_withheld == 1200.0
        assert result.state_withheld == 600.0
        assert result.state == "IL"

    def test_no_withholding(self):
        from tax_engine import parse_1099g_from_ocr
        fields = {
            "Box1": {"value": "8000"},
        }
        result = parse_1099g_from_ocr(fields)
        assert result.compensation == 8000.0
        assert result.federal_withheld == 0.0
        assert result.state_withheld == 0.0

    def test_payer_state_field(self):
        from tax_engine import parse_1099g_from_ocr
        fields = {
            "Box1": {"value": "5000"},
            "PayerState": {"value": "CA"},
        }
        result = parse_1099g_from_ocr(fields)
        assert result.state == "CA"

    def test_empty_fields(self):
        from tax_engine import parse_1099g_from_ocr
        result = parse_1099g_from_ocr({})
        assert result.compensation == 0.0
        assert result.state == ""

    def test_state_prefers_box10a(self):
        from tax_engine import parse_1099g_from_ocr
        fields = {
            "Box1": {"value": "1000"},
            "Box10a": {"value": "NY"},
            "PayerState": {"value": "CA"},
        }
        result = parse_1099g_from_ocr(fields)
        assert result.state == "NY"


# =========================================================================
# Tax Routes Integration
# =========================================================================
class TestTaxRoutesIntegration:
    def test_misc_proc_ids_field_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "misc_1099_proc_ids" in src

    def test_unemployment_proc_ids_field_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "unemployment_1099g_proc_ids" in src

    def test_parse_1099misc_imported(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "parse_1099misc_from_ocr" in src

    def test_parse_1099g_imported(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "parse_1099g_from_ocr" in src

    def test_misc_ocr_loop_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "ocr_misc_other_income" in src

    def test_unemployment_ocr_merge(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "ocr_unemployment" in src


# =========================================================================
# Engine Callable
# =========================================================================
class TestEngineCallable:
    def test_parse_1099misc_callable(self):
        from tax_engine import parse_1099misc_from_ocr
        assert callable(parse_1099misc_from_ocr)

    def test_parse_1099g_callable(self):
        from tax_engine import parse_1099g_from_ocr
        assert callable(parse_1099g_from_ocr)
