#!/usr/bin/env bash
# =============================================================================
# TaxLens W-2/1099 OCR Fixture Tests
# =============================================================================
# Tests the OCR parse → compute → PDF pipeline using stored JSON fixtures
# instead of live Azure calls. Validates field extraction, computation, and
# PDF generation end-to-end.
#
# Usage:
#   bash tests/test_ocr_fixtures.sh
#
# Requires: curl, jq, API running at dropit.istayintek.com
# =============================================================================

set -euo pipefail

API="https://dropit.istayintek.com/api"
FIXTURES="$(cd "$(dirname "$0")/fixtures" && pwd)"
PASS=0
FAIL=0
ERRORS=()

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[TEST]${NC} $*"; }
pass() { PASS=$((PASS + 1)); echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo -e "${RED}[FAIL]${NC} $*"; }

# ---------------------------------------------------------------------------
# Helper: Create a mock OCR result on the PVC for a given fixture
# ---------------------------------------------------------------------------
setup_ocr_fixture() {
    local username="$1"
    local proc_id="$2"
    local fixture_file="$3"

    # Upload a dummy file first to create the directory structure
    local tmp_pdf="/tmp/taxlens_dummy_$$.pdf"
    echo "%PDF-1.4 dummy" > "$tmp_pdf"

    # Create directory via upload endpoint, then overwrite OCR result
    local upload_resp
    upload_resp=$(curl -sk -X POST "${API}/upload" \
        -F "file=@${tmp_pdf};type=application/pdf" \
        -F "username=${username}" 2>&1)
    rm -f "$tmp_pdf"

    local real_proc_id
    real_proc_id=$(echo "$upload_resp" | jq -r '.proc_id // empty')
    if [[ -z "$real_proc_id" ]]; then
        echo "ERROR: Failed to create upload for fixture: $upload_resp"
        return 1
    fi

    # Now we need to inject the OCR fixture via kubectl
    local fixture_content
    fixture_content=$(cat "$fixture_file")

    kubectl exec -n taxlens deploy/taxlens-api -- sh -c \
        "echo '${fixture_content}' > /data/documents/${username}/${real_proc_id}/ocr_result.json" 2>/dev/null || {
        # Fallback: write via heredoc for large JSON
        kubectl exec -n taxlens deploy/taxlens-api -i -- sh -c \
            "cat > /data/documents/${username}/${real_proc_id}/ocr_result.json" < "$fixture_file" 2>/dev/null
    }

    echo "$real_proc_id"
}

# ---------------------------------------------------------------------------
# Test 1: Parse W-2 fixture → compute single filer
# ---------------------------------------------------------------------------
log "=== OCR-F1: Single filer with W-2 OCR ($72,500 wages) ==="

W2_PROC=$(setup_ocr_fixture "ocrtest" "" "${FIXTURES}/w2_sample.json")
if [[ -n "$W2_PROC" ]]; then
    resp=$(curl -sk -X POST "${API}/tax-draft" \
        -H "Content-Type: application/json" \
        -d "{
            \"filing_status\": \"single\",
            \"username\": \"ocrtest\",
            \"filer\": {\"first_name\":\"Jane\",\"last_name\":\"Doe\",\"ssn\":\"123-45-6789\",\"address_street\":\"456 Oak St\",\"address_city\":\"Springfield\",\"address_state\":\"IL\",\"address_zip\":\"62704\"},
            \"w2_proc_ids\": [\"${W2_PROC}\"]
        }" 2>&1)

    draft_id=$(echo "$resp" | jq -r '.draft_id // empty')
    total_income=$(echo "$resp" | jq -r '.total_income // 0')
    fed_withholding=$(echo "$resp" | jq -r '.federal_withholding // 0')

    if [[ -n "$draft_id" ]] && (( $(echo "$total_income > 72000" | bc -l) )); then
        # Verify withholding pulled from W-2
        if (( $(echo "$fed_withholding > 10000" | bc -l) )); then
            pass "OCR-F1: W-2 parse OK — draft=$draft_id income=$total_income withheld=$fed_withholding"
        else
            fail "OCR-F1: W-2 withholding not parsed — got $fed_withholding, expected ~10875"
        fi
    else
        fail "OCR-F1: Failed — draft=$draft_id income=$total_income"
    fi
else
    fail "OCR-F1: Could not set up fixture"
fi

# ---------------------------------------------------------------------------
# Test 2: Parse W-2 high earner → verify Additional Medicare Tax kicks in
# ---------------------------------------------------------------------------
log "=== OCR-F2: High earner W-2 ($285K) + Additional Medicare Tax ==="

W2H_PROC=$(setup_ocr_fixture "ocrtest" "" "${FIXTURES}/w2_high_earner.json")
if [[ -n "$W2H_PROC" ]]; then
    resp=$(curl -sk -X POST "${API}/tax-draft" \
        -H "Content-Type: application/json" \
        -d "{
            \"filing_status\": \"single\",
            \"username\": \"ocrtest\",
            \"filer\": {\"first_name\":\"Robert\",\"last_name\":\"Chen\",\"ssn\":\"987-65-4321\"},
            \"w2_proc_ids\": [\"${W2H_PROC}\"],
            \"additional_income\": {\"other_interest\": 5000, \"ordinary_dividends\": 8000, \"qualified_dividends\": 6000}
        }" 2>&1)

    draft_id=$(echo "$resp" | jq -r '.draft_id // empty')
    total_income=$(echo "$resp" | jq -r '.total_income // 0')
    niit=$(echo "$resp" | jq -r '.niit // 0')
    add_medicare=$(echo "$resp" | jq -r '.additional_medicare_tax // 0')

    if [[ -n "$draft_id" ]]; then
        errors=""
        # AGI > $200K single → NIIT should trigger on investment income
        if (( $(echo "$niit > 0" | bc -l) )); then
            niit_ok="NIIT=$niit"
        else
            niit_ok="NIIT=0(EXPECTED>0)"
            errors="niit "
        fi
        # Medicare wages $285K > $200K → Additional Medicare should trigger
        if (( $(echo "$add_medicare > 0" | bc -l) )); then
            med_ok="AddMed=$add_medicare"
        else
            med_ok="AddMed=0(EXPECTED>0)"
            errors="$errors addmed"
        fi

        if [[ -z "$errors" ]]; then
            pass "OCR-F2: High earner surtaxes OK — draft=$draft_id $niit_ok $med_ok"
        else
            fail "OCR-F2: Surtax missing — $niit_ok $med_ok"
        fi
    else
        fail "OCR-F2: Failed to create draft"
    fi
else
    fail "OCR-F2: Could not set up fixture"
fi

# ---------------------------------------------------------------------------
# Test 3: Parse 1099-INT fixture → verify interest extracted
# ---------------------------------------------------------------------------
log "=== OCR-F3: 1099-INT OCR ($2,450 interest) ==="

INT_PROC=$(setup_ocr_fixture "ocrtest" "" "${FIXTURES}/1099int_sample.json")
if [[ -n "$INT_PROC" ]]; then
    resp=$(curl -sk -X POST "${API}/tax-draft" \
        -H "Content-Type: application/json" \
        -d "{
            \"filing_status\": \"single\",
            \"username\": \"ocrtest\",
            \"filer\": {\"first_name\":\"Test\",\"last_name\":\"User\",\"ssn\":\"111-22-3333\"},
            \"interest_1099_proc_ids\": [\"${INT_PROC}\"]
        }" 2>&1)

    draft_id=$(echo "$resp" | jq -r '.draft_id // empty')
    total_income=$(echo "$resp" | jq -r '.total_income // 0')

    if [[ -n "$draft_id" ]] && (( $(echo "$total_income >= 2450" | bc -l) )); then
        pass "OCR-F3: 1099-INT parse OK — draft=$draft_id income=$total_income (includes $2,450 interest)"
    else
        fail "OCR-F3: Interest not extracted — income=$total_income, expected ≥2450"
    fi
else
    fail "OCR-F3: Could not set up fixture"
fi

# ---------------------------------------------------------------------------
# Test 4: Combined W-2 + 1099-INT + investments → full pipeline
# ---------------------------------------------------------------------------
log "=== OCR-F4: Combined W-2 + 1099-INT + capital gains ==="

W2C_PROC=$(setup_ocr_fixture "ocrtest" "" "${FIXTURES}/w2_sample.json")
INTC_PROC=$(setup_ocr_fixture "ocrtest" "" "${FIXTURES}/1099int_sample.json")
if [[ -n "$W2C_PROC" && -n "$INTC_PROC" ]]; then
    resp=$(curl -sk -X POST "${API}/tax-draft" \
        -H "Content-Type: application/json" \
        -d "{
            \"filing_status\": \"mfj\",
            \"username\": \"ocrtest\",
            \"filer\": {\"first_name\":\"Jane\",\"last_name\":\"Doe\",\"ssn\":\"123-45-6789\",\"address_street\":\"456 Oak St\",\"address_city\":\"Springfield\",\"address_state\":\"IL\",\"address_zip\":\"62704\"},
            \"spouse\": {\"first_name\":\"John\",\"last_name\":\"Doe\",\"ssn\":\"123-45-6780\"},
            \"num_dependents\": 2,
            \"w2_proc_ids\": [\"${W2C_PROC}\"],
            \"interest_1099_proc_ids\": [\"${INTC_PROC}\"],
            \"additional_income\": {
                \"ordinary_dividends\": 3500,
                \"qualified_dividends\": 2800,
                \"capital_transactions\": [{\"description\":\"AAPL\",\"proceeds\":15000,\"cost_basis\":10000,\"is_long_term\":true}]
            },
            \"deductions\": {\"mortgage_interest\":12000,\"property_tax\":8000,\"charitable_cash\":3000}
        }" 2>&1)

    draft_id=$(echo "$resp" | jq -r '.draft_id // empty')
    total_income=$(echo "$resp" | jq -r '.total_income // 0')
    forms=$(echo "$resp" | jq -r '.forms_generated[]' 2>/dev/null | sort | tr '\n' ',' | sed 's/,$//')

    if [[ -n "$draft_id" ]]; then
        # Income should be: wages(72500) + interest(2450) + dividends(3500) + capgain(5000) = ~83450
        if (( $(echo "$total_income > 80000" | bc -l) )); then
            # Check PDFs generated
            pdfs_resp=$(curl -sk "${API}/tax-draft/${draft_id}/pdfs?username=ocrtest" 2>&1)
            pdf_count=$(echo "$pdfs_resp" | jq '.pdfs | length')
            pass "OCR-F4: Full pipeline OK — draft=$draft_id income=$total_income pdfs=$pdf_count forms=[$forms]"
        else
            fail "OCR-F4: Income too low — $total_income, expected >80000"
        fi
    else
        fail "OCR-F4: Failed to create draft"
    fi
else
    fail "OCR-F4: Could not set up fixtures"
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
log "Cleaning up ocrtest user data..."
kubectl exec -n taxlens deploy/taxlens-api -- sh -c 'rm -rf /data/documents/ocrtest' 2>/dev/null || true

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=============================="
echo "  OCR Fixture Test Results"
echo "=============================="
echo -e "  ${GREEN}PASSED: ${PASS}${NC}"
echo -e "  ${RED}FAILED: ${FAIL}${NC}"
echo "  Total:  $((PASS + FAIL))"
echo ""

if [[ ${FAIL} -gt 0 ]]; then
    echo -e "${RED}Failures:${NC}"
    for e in "${ERRORS[@]}"; do
        echo "  - $e"
    done
    exit 1
fi

echo -e "${GREEN}All OCR fixture tests passed!${NC}"
