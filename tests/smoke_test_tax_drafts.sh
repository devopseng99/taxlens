#!/usr/bin/env bash
# =============================================================================
# TaxLens Tax Draft Smoke Tests — 13 Realistic Filing Scenarios
# =============================================================================
# Re-runnable validation suite. Tests compute + PDF generation end-to-end.
#
# Usage:
#   bash tests/smoke_test_tax_drafts.sh [--verbose]
#
# Requires: curl, jq
# API: https://dropit.istayintek.com/api/tax-draft
# =============================================================================

set -euo pipefail

API="https://dropit.istayintek.com/api"
API_KEY="${TAXLENS_API_KEY:-}"
VERBOSE="${1:-}"
PASS=0
FAIL=0
ERRORS=()

if [[ -z "$API_KEY" ]]; then
    echo -e "\033[0;31m[ERROR]\033[0m TAXLENS_API_KEY not set. Export it before running."
    exit 1
fi

# Color output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[TEST]${NC} $*"; }
pass() { PASS=$((PASS + 1)); echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo -e "${RED}[FAIL]${NC} $*"; }

# ---------------------------------------------------------------------------
# Helper: POST tax draft and validate response
# ---------------------------------------------------------------------------
run_test() {
    local test_name="$1"
    local payload="$2"
    local expect_refund="${3:-}"        # "refund" or "owed"
    local expect_forms="${4:-}"         # comma-sep form names to check
    local expect_biz="${5:-}"           # "yes" if business income expected

    log "=== ${test_name} ==="

    local response
    response=$(curl -sk -X POST "${API}/tax-draft" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        -d "${payload}" 2>&1) || {
        fail "${test_name}: curl failed"
        return
    }

    # Check for error
    if echo "$response" | jq -e '.detail' >/dev/null 2>&1; then
        fail "${test_name}: API error — $(echo "$response" | jq -r '.detail')"
        return
    fi

    local draft_id total_income agi fed_tax net_refund forms
    draft_id=$(echo "$response" | jq -r '.draft_id')
    total_income=$(echo "$response" | jq -r '.total_income')
    agi=$(echo "$response" | jq -r '.agi')
    fed_tax=$(echo "$response" | jq -r '.federal_tax')
    net_refund=$(echo "$response" | jq -r '.net_refund')
    forms=$(echo "$response" | jq -r '.forms_generated | join(", ")')
    biz_income=$(echo "$response" | jq -r '.business_income')
    se_tax=$(echo "$response" | jq -r '.se_tax')
    qbi=$(echo "$response" | jq -r '.qbi_deduction')

    if [[ -z "$draft_id" || "$draft_id" == "null" ]]; then
        fail "${test_name}: no draft_id in response"
        return
    fi

    if [[ "$VERBOSE" == "--verbose" ]]; then
        echo "  draft_id:     ${draft_id}"
        echo "  total_income: ${total_income}"
        echo "  agi:          ${agi}"
        echo "  federal_tax:  ${fed_tax}"
        echo "  net_refund:   ${net_refund}"
        echo "  biz_income:   ${biz_income}"
        echo "  se_tax:       ${se_tax}"
        echo "  qbi_deduct:   ${qbi}"
        echo "  forms:        ${forms}"
    fi

    # Validate refund vs owed
    if [[ "$expect_refund" == "refund" ]]; then
        local refund_val
        refund_val=$(echo "$net_refund" | awk '{if ($1 > 0) print "yes"; else print "no"}')
        if [[ "$refund_val" != "yes" ]]; then
            fail "${test_name}: expected refund but got net_refund=${net_refund}"
            return
        fi
    elif [[ "$expect_refund" == "owed" ]]; then
        local owed_val
        owed_val=$(echo "$net_refund" | awk '{if ($1 < 0) print "yes"; else print "no"}')
        if [[ "$owed_val" != "yes" ]]; then
            fail "${test_name}: expected amount owed but got net_refund=${net_refund}"
            return
        fi
    fi

    # Validate business income present
    if [[ "$expect_biz" == "yes" ]]; then
        local has_biz
        has_biz=$(echo "$biz_income" | awk '{if ($1 > 0) print "yes"; else print "no"}')
        if [[ "$has_biz" != "yes" ]]; then
            fail "${test_name}: expected business income > 0 but got ${biz_income}"
            return
        fi
        # Check SE tax computed
        local has_se
        has_se=$(echo "$se_tax" | awk '{if ($1 > 0) print "yes"; else print "no"}')
        if [[ "$has_se" != "yes" ]]; then
            fail "${test_name}: expected SE tax > 0 but got ${se_tax}"
            return
        fi
    fi

    # Validate expected forms in the PDF list
    if [[ -n "$expect_forms" ]]; then
        IFS=',' read -ra FORM_ARRAY <<< "$expect_forms"
        for form in "${FORM_ARRAY[@]}"; do
            form=$(echo "$form" | xargs)  # trim
            if ! echo "$forms" | grep -qi "$form"; then
                fail "${test_name}: expected form '${form}' not in generated forms: ${forms}"
                return
            fi
        done
    fi

    # Verify draft is retrievable
    local get_resp
    get_resp=$(curl -sk -H "X-API-Key: ${API_KEY}" "${API}/tax-draft/${draft_id}?username=smoketest" 2>&1)
    local get_id
    get_id=$(echo "$get_resp" | jq -r '.draft_id' 2>/dev/null)
    if [[ "$get_id" != "$draft_id" ]]; then
        fail "${test_name}: GET /tax-draft/${draft_id} returned wrong id"
        return
    fi

    # Verify PDFs are listed
    local pdfs_resp pdf_count
    pdfs_resp=$(curl -sk -H "X-API-Key: ${API_KEY}" "${API}/tax-draft/${draft_id}/pdfs?username=smoketest" 2>&1)
    pdf_count=$(echo "$pdfs_resp" | jq '.pdfs | length' 2>/dev/null)
    if [[ "$pdf_count" -lt 2 ]]; then
        fail "${test_name}: expected at least 2 PDFs but got ${pdf_count}"
        return
    fi

    pass "${test_name} — draft=${draft_id} income=${total_income} refund=${net_refund} forms=[${forms}]"
}


# ===========================================================================
# TEST CASES
# ===========================================================================

# --- 1. Single W-2 worker (basic) ---
run_test "TC01: Single W-2 worker" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Alice", "last_name": "Johnson", "ssn": "XXX-XX-1001"},
    "w2_proc_ids": [],
    "additional_income": {
        "other_interest": 340.00,
        "capital_transactions": [
            {"description": "AAPL stock", "proceeds": 5200, "cost_basis": 4800, "is_long_term": true}
        ]
    },
    "deductions": {"student_loan_interest": 1800},
    "payments": {},
    "businesses": [],
    "num_dependents": 0
}' "" "1040,IL-1040" ""

# --- 2. MFJ couple with investments ---
run_test "TC02: MFJ couple with investments" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "James", "last_name": "Wilson", "ssn": "XXX-XX-2001"},
    "spouse": {"first_name": "Sarah", "last_name": "Wilson", "ssn": "XXX-XX-2002"},
    "additional_income": {
        "other_interest": 2800.00,
        "ordinary_dividends": 4500.00,
        "qualified_dividends": 3200.00,
        "capital_transactions": [
            {"description": "MSFT stock", "proceeds": 15000, "cost_basis": 10000, "is_long_term": true},
            {"description": "Crypto BTC", "proceeds": 8000, "cost_basis": 12000, "is_long_term": false}
        ]
    },
    "deductions": {
        "mortgage_interest": 14000,
        "property_tax": 7500,
        "state_income_tax_paid": 3200,
        "charitable_cash": 5000
    },
    "payments": {"estimated_federal": 3000, "estimated_state": 500}
}' "" "1040,Schedule B,Schedule D,IL-1040" ""

# --- 3. Head of Household with 2 dependents ---
run_test "TC03: HoH with CTC" '{
    "filing_status": "hoh",
    "username": "smoketest",
    "filer": {"first_name": "Maria", "last_name": "Garcia", "ssn": "XXX-XX-3001",
              "address_street": "456 Oak Ave", "address_city": "Chicago", "address_zip": "60614"},
    "num_dependents": 2,
    "additional_income": {
        "other_interest": 150.00,
        "ordinary_dividends": 800.00,
        "qualified_dividends": 600.00
    },
    "deductions": {
        "mortgage_interest": 18000,
        "property_tax": 8500,
        "state_income_tax_paid": 2500,
        "charitable_cash": 3500,
        "charitable_noncash": 1200
    },
    "payments": {"estimated_federal": 1000}
}' "" "1040,IL-1040" ""

# --- 4. Freelance software developer (single + Schedule C) ---
run_test "TC04: Freelance developer" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Dev", "last_name": "Patel", "ssn": "XXX-XX-4001"},
    "businesses": [
        {
            "business_name": "Patel Consulting LLC",
            "business_type": "Software Development",
            "gross_receipts": 125000,
            "cost_of_goods_sold": 0,
            "advertising": 1200,
            "office_expense": 3500,
            "supplies": 2800,
            "utilities": 600,
            "home_office_sqft": 200,
            "home_total_sqft": 1800,
            "home_expenses": 24000,
            "other_expenses": 4000,
            "other_expenses_description": "Software subscriptions"
        }
    ],
    "additional_income": {"other_interest": 500},
    "deductions": {"student_loan_interest": 2500},
    "payments": {"estimated_federal": 20000, "estimated_state": 5000}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 5. Rideshare driver + W-2 day job (MFJ) ---
run_test "TC05: Rideshare driver + W-2 MFJ" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "Carlos", "last_name": "Rodriguez", "ssn": "XXX-XX-5001"},
    "spouse": {"first_name": "Ana", "last_name": "Rodriguez", "ssn": "XXX-XX-5002"},
    "num_dependents": 1,
    "businesses": [
        {
            "business_name": "Carlos Rideshare",
            "business_type": "Rideshare/Delivery",
            "gross_receipts": 38000,
            "car_expenses": 12000,
            "insurance": 2400,
            "supplies": 500,
            "other_expenses": 1800,
            "other_expenses_description": "Phone plan, tolls"
        }
    ],
    "additional_income": {"other_interest": 200},
    "deductions": {
        "mortgage_interest": 10000,
        "property_tax": 5000,
        "state_income_tax_paid": 2000,
        "charitable_cash": 1500
    },
    "payments": {"estimated_federal": 4000, "estimated_state": 1000}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 6. Small business owner (restaurant) ---
run_test "TC06: Restaurant owner" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Tony", "last_name": "Chen", "ssn": "XXX-XX-6001"},
    "businesses": [
        {
            "business_name": "Tonys Kitchen",
            "business_type": "Food Service",
            "gross_receipts": 280000,
            "cost_of_goods_sold": 95000,
            "advertising": 8000,
            "rent": 36000,
            "insurance": 6000,
            "supplies": 12000,
            "utilities": 9600,
            "other_expenses": 15000,
            "other_expenses_description": "Wages, cleaning, permits"
        }
    ],
    "deductions": {"charitable_cash": 5000},
    "payments": {"estimated_federal": 25000, "estimated_state": 6000}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 7. Consultant with multiple businesses ---
run_test "TC07: Multiple businesses" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Lisa", "last_name": "Park", "ssn": "XXX-XX-7001"},
    "businesses": [
        {
            "business_name": "Park Marketing",
            "business_type": "Marketing Consulting",
            "gross_receipts": 85000,
            "advertising": 3000,
            "office_expense": 2000,
            "other_expenses": 5000,
            "other_expenses_description": "Subcontractors"
        },
        {
            "business_name": "LP Photography",
            "business_type": "Photography",
            "gross_receipts": 25000,
            "supplies": 4000,
            "car_expenses": 3000,
            "insurance": 1200,
            "other_expenses": 2000,
            "other_expenses_description": "Equipment rental"
        }
    ],
    "additional_income": {
        "ordinary_dividends": 2000,
        "qualified_dividends": 1500,
        "capital_transactions": [
            {"description": "ETF sale", "proceeds": 20000, "cost_basis": 17000, "is_long_term": true}
        ]
    },
    "deductions": {"mortgage_interest": 12000, "property_tax": 6000, "state_income_tax_paid": 4000},
    "payments": {"estimated_federal": 18000, "estimated_state": 4500}
}' "" "1040,Schedule C,Schedule SE,Schedule D,IL-1040" "yes"

# --- 8. MFS high earner (no business) ---
run_test "TC08: MFS high earner" '{
    "filing_status": "mfs",
    "username": "smoketest",
    "filer": {"first_name": "Robert", "last_name": "Kim", "ssn": "XXX-XX-8001"},
    "additional_income": {
        "other_interest": 8500,
        "ordinary_dividends": 12000,
        "qualified_dividends": 9000,
        "capital_transactions": [
            {"description": "GOOG stock", "proceeds": 50000, "cost_basis": 30000, "is_long_term": true},
            {"description": "Day trades", "proceeds": 25000, "cost_basis": 22000, "is_long_term": false}
        ]
    },
    "deductions": {
        "mortgage_interest": 20000,
        "property_tax": 3000,
        "state_income_tax_paid": 2000,
        "charitable_cash": 10000,
        "medical_expenses": 15000
    },
    "payments": {"estimated_federal": 10000, "estimated_state": 2000}
}' "" "1040,Schedule A,Schedule B,Schedule D,IL-1040" ""

# --- 9. HoH single parent, freelance writer + CTC ---
run_test "TC09: HoH freelance writer + CTC" '{
    "filing_status": "hoh",
    "username": "smoketest",
    "filer": {"first_name": "Keisha", "last_name": "Brown", "ssn": "XXX-XX-9001"},
    "num_dependents": 3,
    "businesses": [
        {
            "business_name": "KB Writing Services",
            "business_type": "Freelance Writing",
            "gross_receipts": 55000,
            "office_expense": 1500,
            "supplies": 800,
            "home_office_sqft": 150,
            "home_total_sqft": 1200,
            "home_expenses": 18000,
            "other_expenses": 2000,
            "other_expenses_description": "Research subscriptions"
        }
    ],
    "deductions": {
        "mortgage_interest": 9000,
        "property_tax": 4500,
        "state_income_tax_paid": 1500,
        "charitable_cash": 2000
    },
    "payments": {"estimated_federal": 5000, "estimated_state": 1500}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 10. MFJ dual-business couple with heavy investments ---
run_test "TC10: MFJ dual-business couple" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "David", "last_name": "Thompson", "ssn": "XXX-XX-1010"},
    "spouse": {"first_name": "Emily", "last_name": "Thompson", "ssn": "XXX-XX-1011"},
    "num_dependents": 2,
    "businesses": [
        {
            "business_name": "Thompson IT Solutions",
            "business_type": "IT Consulting",
            "gross_receipts": 180000,
            "advertising": 5000,
            "insurance": 4000,
            "office_expense": 6000,
            "supplies": 3000,
            "utilities": 1200,
            "home_office_sqft": 250,
            "home_total_sqft": 2500,
            "home_expenses": 30000,
            "other_expenses": 8000,
            "other_expenses_description": "Subcontractors, training"
        },
        {
            "business_name": "Emily T Coaching",
            "business_type": "Life Coaching",
            "gross_receipts": 45000,
            "advertising": 3000,
            "office_expense": 1000,
            "car_expenses": 4000,
            "other_expenses": 2000,
            "other_expenses_description": "Certification, materials"
        }
    ],
    "additional_income": {
        "other_interest": 5000,
        "ordinary_dividends": 8000,
        "qualified_dividends": 6000,
        "capital_transactions": [
            {"description": "NVDA stock", "proceeds": 40000, "cost_basis": 15000, "is_long_term": true},
            {"description": "Crypto ETH", "proceeds": 12000, "cost_basis": 8000, "is_long_term": false},
            {"description": "Bond fund", "proceeds": 10000, "cost_basis": 9500, "is_long_term": true}
        ]
    },
    "deductions": {
        "mortgage_interest": 22000,
        "property_tax": 9000,
        "state_income_tax_paid": 5000,
        "charitable_cash": 8000,
        "charitable_noncash": 3000,
        "medical_expenses": 5000,
        "student_loan_interest": 1200
    },
    "payments": {"estimated_federal": 40000, "estimated_state": 10000}
}' "" "1040,Schedule C,Schedule SE,Schedule B,Schedule D,IL-1040" "yes"

# --- 11. Minimum wage single (low income, small refund) ---
run_test "TC11: Low income single" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Jake", "last_name": "Miller", "ssn": "XXX-XX-1101"},
    "additional_income": {"other_interest": 25},
    "deductions": {},
    "payments": {}
}' "" "1040,IL-1040" ""

# --- 12. Single high-income consultant (owed scenario) ---
run_test "TC12: High-income consultant underpaid" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Victoria", "last_name": "Steele", "ssn": "XXX-XX-1201"},
    "businesses": [
        {
            "business_name": "Steele Strategy Group",
            "business_type": "Management Consulting",
            "gross_receipts": 350000,
            "advertising": 10000,
            "rent": 24000,
            "insurance": 8000,
            "office_expense": 5000,
            "supplies": 3000,
            "utilities": 2400,
            "other_expenses": 20000,
            "other_expenses_description": "Travel, professional development"
        }
    ],
    "additional_income": {
        "other_interest": 12000,
        "ordinary_dividends": 15000,
        "qualified_dividends": 10000,
        "capital_transactions": [
            {"description": "Index fund", "proceeds": 100000, "cost_basis": 60000, "is_long_term": true}
        ]
    },
    "deductions": {
        "mortgage_interest": 25000,
        "property_tax": 8000,
        "state_income_tax_paid": 6000,
        "charitable_cash": 15000,
        "charitable_noncash": 5000
    },
    "payments": {"estimated_federal": 30000, "estimated_state": 8000}
}' "owed" "1040,Schedule C,Schedule SE,Schedule A,Schedule B,Schedule D,IL-1040" "yes"

# --- 13. Nurse with side tutoring business (MFJ, 1 dependent) ---
run_test "TC13: Nurse + tutor side hustle MFJ" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "Amanda", "last_name": "Foster", "ssn": "XXX-XX-1301",
              "address_street": "1422 Lakeshore Dr", "address_city": "Evanston", "address_state": "IL", "address_zip": "60201"},
    "spouse": {"first_name": "Brian", "last_name": "Foster", "ssn": "XXX-XX-1302"},
    "num_dependents": 1,
    "businesses": [
        {
            "business_name": "Foster Tutoring",
            "business_type": "Educational Services",
            "gross_receipts": 18000,
            "advertising": 400,
            "supplies": 950,
            "car_expenses": 1800,
            "other_expenses": 600,
            "other_expenses_description": "Online platform fees"
        }
    ],
    "additional_income": {
        "other_interest": 1200,
        "ordinary_dividends": 900,
        "qualified_dividends": 700
    },
    "deductions": {
        "mortgage_interest": 16500,
        "property_tax": 7200,
        "state_income_tax_paid": 3800,
        "charitable_cash": 4200
    },
    "payments": {"estimated_federal": 2500, "estimated_state": 800}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 14. Retired couple with pension + investments (MFJ) ---
run_test "TC14: Retired MFJ couple" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "Harold", "last_name": "Nakamura", "ssn": "XXX-XX-1401",
              "address_street": "890 Willow Ct", "address_city": "Schaumburg", "address_state": "IL", "address_zip": "60193"},
    "spouse": {"first_name": "Doris", "last_name": "Nakamura", "ssn": "XXX-XX-1402"},
    "num_dependents": 0,
    "additional_income": {
        "other_interest": 18500,
        "ordinary_dividends": 22000,
        "qualified_dividends": 16000,
        "capital_transactions": [
            {"description": "Municipal bond fund", "proceeds": 25000, "cost_basis": 22000, "is_long_term": true},
            {"description": "Growth ETF rebalance", "proceeds": 35000, "cost_basis": 28000, "is_long_term": true}
        ],
        "other_income": 42000,
        "other_income_description": "Pension"
    },
    "deductions": {
        "mortgage_interest": 8000,
        "property_tax": 9500,
        "charitable_cash": 12000,
        "charitable_noncash": 5000,
        "medical_expenses": 28000
    },
    "payments": {"estimated_federal": 15000, "estimated_state": 4000}
}' "" "1040,Schedule A,Schedule B,Schedule D,IL-1040" ""

# --- 15. Young single gig worker (Etsy + DoorDash) ---
run_test "TC15: Young gig worker multi-platform" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Zoe", "last_name": "Martinez", "ssn": "XXX-XX-1501",
              "address_street": "2100 N Milwaukee Ave Apt 3B", "address_city": "Chicago", "address_state": "IL", "address_zip": "60647"},
    "num_dependents": 0,
    "businesses": [
        {
            "business_name": "Zoe Creates (Etsy)",
            "business_type": "Online Retail",
            "gross_receipts": 32000,
            "cost_of_goods_sold": 9500,
            "advertising": 2400,
            "supplies": 4200,
            "other_expenses": 1800,
            "other_expenses_description": "Etsy fees, packaging, shipping"
        },
        {
            "business_name": "Zoe Delivers",
            "business_type": "Delivery Services",
            "gross_receipts": 22000,
            "car_expenses": 8500,
            "insurance": 1800,
            "supplies": 300,
            "other_expenses": 600,
            "other_expenses_description": "Phone mount, insulated bags"
        }
    ],
    "additional_income": {"other_interest": 85},
    "deductions": {"student_loan_interest": 2500},
    "payments": {"estimated_federal": 3000, "estimated_state": 1000}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 16. Real estate agent with heavy expenses (HoH, 2 kids) ---
run_test "TC16: Real estate agent HoH" '{
    "filing_status": "hoh",
    "username": "smoketest",
    "filer": {"first_name": "Denise", "last_name": "Washington", "ssn": "XXX-XX-1601",
              "address_street": "4500 S King Dr", "address_city": "Chicago", "address_state": "IL", "address_zip": "60653"},
    "num_dependents": 2,
    "businesses": [
        {
            "business_name": "Washington Realty",
            "business_type": "Real Estate Agent",
            "gross_receipts": 145000,
            "advertising": 12000,
            "car_expenses": 9500,
            "insurance": 3200,
            "office_expense": 4800,
            "rent": 6000,
            "supplies": 2000,
            "other_expenses": 8500,
            "other_expenses_description": "MLS dues, lockboxes, staging"
        }
    ],
    "additional_income": {
        "other_interest": 350,
        "ordinary_dividends": 1200,
        "qualified_dividends": 900
    },
    "deductions": {
        "mortgage_interest": 14000,
        "property_tax": 6800,
        "state_income_tax_paid": 3500,
        "charitable_cash": 6000,
        "charitable_noncash": 2500
    },
    "payments": {"estimated_federal": 18000, "estimated_state": 5000}
}' "" "1040,Schedule C,Schedule SE,IL-1040" "yes"

# --- 17. MFS spouse with crypto day trading losses ---
run_test "TC17: MFS crypto trader with losses" '{
    "filing_status": "mfs",
    "username": "smoketest",
    "filer": {"first_name": "Marcus", "last_name": "Okafor", "ssn": "XXX-XX-1701",
              "address_street": "155 N Wacker Dr Apt 42", "address_city": "Chicago", "address_state": "IL", "address_zip": "60606"},
    "num_dependents": 0,
    "additional_income": {
        "other_interest": 4500,
        "ordinary_dividends": 6000,
        "qualified_dividends": 4800,
        "capital_transactions": [
            {"description": "BTC swing trades", "proceeds": 85000, "cost_basis": 110000, "is_long_term": false},
            {"description": "ETH staking sale", "proceeds": 12000, "cost_basis": 8000, "is_long_term": true},
            {"description": "SOL position", "proceeds": 5000, "cost_basis": 18000, "is_long_term": false}
        ],
        "other_income": 3500,
        "other_income_description": "Crypto staking rewards"
    },
    "deductions": {
        "state_income_tax_paid": 2000,
        "charitable_cash": 3000
    },
    "payments": {"estimated_federal": 5000, "estimated_state": 1500}
}' "" "1040,Schedule B,Schedule D,IL-1040" ""

# --- Rerun original 3 validated scenarios ---
# TC13a: Original Single
run_test "TC13a: Original Single (revalidation)" '{
    "filing_status": "single",
    "username": "smoketest",
    "filer": {"first_name": "Test", "last_name": "Single", "ssn": "XXX-XX-0001",
              "address_street": "123 Main St", "address_city": "Chicago", "address_state": "IL", "address_zip": "60601"},
    "additional_income": {
        "other_interest": 340.41,
        "capital_transactions": [
            {"description": "AAPL stock sale", "proceeds": 5200, "cost_basis": 4800, "is_long_term": true},
            {"description": "Crypto BTC sale", "proceeds": 3000, "cost_basis": 3500, "is_long_term": false}
        ]
    },
    "deductions": {"student_loan_interest": 1800},
    "payments": {}
}' "" "1040,IL-1040" ""

# TC13b: Original MFJ
run_test "TC13b: Original MFJ (revalidation)" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "filer": {"first_name": "Test", "last_name": "Husband", "ssn": "XXX-XX-0002"},
    "spouse": {"first_name": "Test", "last_name": "Wife", "ssn": "XXX-XX-0003"},
    "additional_income": {
        "other_interest": 2840.41,
        "ordinary_dividends": 4500,
        "qualified_dividends": 3200,
        "capital_transactions": [
            {"description": "MSFT stock", "proceeds": 15000, "cost_basis": 10000, "is_long_term": true},
            {"description": "ETH crypto", "proceeds": 8000, "cost_basis": 12000, "is_long_term": false}
        ]
    },
    "deductions": {
        "mortgage_interest": 14000,
        "property_tax": 7500,
        "state_income_tax_paid": 3200,
        "charitable_cash": 5000
    },
    "payments": {"estimated_federal": 3000, "estimated_state": 500}
}' "" "1040,Schedule B,Schedule D,IL-1040" ""

# TC13c: Original HoH
run_test "TC13c: Original HoH (revalidation)" '{
    "filing_status": "hoh",
    "username": "smoketest",
    "filer": {"first_name": "Test", "last_name": "Parent", "ssn": "XXX-XX-0004",
              "address_street": "789 Elm Dr", "address_city": "Naperville", "address_state": "IL", "address_zip": "60540"},
    "num_dependents": 2,
    "additional_income": {
        "other_interest": 340.41,
        "ordinary_dividends": 4500,
        "qualified_dividends": 3200,
        "capital_transactions": [
            {"description": "VOO ETF", "proceeds": 12000, "cost_basis": 9000, "is_long_term": true}
        ]
    },
    "deductions": {
        "mortgage_interest": 18000,
        "property_tax": 8500,
        "state_income_tax_paid": 2500,
        "charitable_cash": 3500,
        "charitable_noncash": 1200
    },
    "payments": {"estimated_federal": 1000}
}' "" "1040,Schedule A,IL-1040" ""


# ===========================================================================
# MULTI-STATE TESTS (Wave 7)
# ===========================================================================

log "=== TC21: CA Resident — High Earner (graduated + surtax) ==="
run_test "TC21: CA high earner" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "CA",
    "filer": {"first_name": "Maria", "last_name": "Gonzalez", "ssn": "XXX-XX-0021",
              "address_street": "100 Market St", "address_city": "San Francisco", "address_state": "CA", "address_zip": "94105"},
    "additional_income": {
        "other_interest": 5000,
        "ordinary_dividends": 15000,
        "qualified_dividends": 10000,
        "capital_transactions": [
            {"description": "AAPL stock", "proceeds": 200000, "cost_basis": 80000, "is_long_term": true}
        ]
    },
    "deductions": {
        "mortgage_interest": 22000,
        "property_tax": 12000,
        "charitable_cash": 5000
    }
}' "" "1040,Schedule D,CA-540" ""

log "=== TC22: TX Resident — No State Tax ==="
run_test "TC22: TX no state tax" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "TX",
    "filer": {"first_name": "Jake", "last_name": "Austin", "ssn": "XXX-XX-0022",
              "address_street": "200 Congress Ave", "address_city": "Austin", "address_state": "TX", "address_zip": "78701"},
    "additional_income": {"other_interest": 500}
}' "" "1040" ""

log "=== TC23: PA Resident — Flat Rate ==="
run_test "TC23: PA flat rate" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "residence_state": "PA",
    "filer": {"first_name": "Sarah", "last_name": "Miller", "ssn": "XXX-XX-0023",
              "address_street": "300 Broad St", "address_city": "Philadelphia", "address_state": "PA", "address_zip": "19102"},
    "spouse": {"first_name": "Tom", "last_name": "Miller", "ssn": "XXX-XX-0024"},
    "num_dependents": 1,
    "additional_income": {"other_interest": 1200},
    "deductions": {"mortgage_interest": 15000, "property_tax": 6000}
}' "" "1040,PA-40" ""

log "=== TC24: NJ Resident, NY Worker (multi-state) ==="
run_test "TC24: NJ→NY multi-state" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "NJ",
    "work_states": ["NY"],
    "filer": {"first_name": "Alex", "last_name": "Park", "ssn": "XXX-XX-0025",
              "address_street": "400 Park Ave", "address_city": "Hoboken", "address_state": "NJ", "address_zip": "07030"},
    "additional_income": {"other_interest": 800},
    "deductions": {"mortgage_interest": 18000, "property_tax": 9000}
}' "" "1040,NJ-1040" ""

log "=== TC25: IL Resident, WI Worker (reciprocal — no WI return) ==="
run_test "TC25: IL→WI reciprocal" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "IL",
    "work_states": ["WI"],
    "filer": {"first_name": "Chris", "last_name": "Johnson", "ssn": "XXX-XX-0026",
              "address_street": "500 Lake Shore Dr", "address_city": "Chicago", "address_state": "IL", "address_zip": "60601"},
    "additional_income": {"other_interest": 300}
}' "" "1040,IL-1040" ""


# ===========================================================================
# Wave 9 — Extended OCR Parser Scenarios (TC26-TC29)
# ===========================================================================

log "=== TC26: Investor with dividends + brokerage (1099-DIV + 1099-B) ==="
run_test "TC26: Dividends + Brokerage" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "CA",
    "filer": {"first_name": "Morgan", "last_name": "Wells", "ssn": "XXX-XX-0027",
              "address_street": "600 Market St", "address_city": "San Francisco", "address_state": "CA", "address_zip": "94105"},
    "additional_income": {
        "ordinary_dividends": 3245.67,
        "qualified_dividends": 2100.00,
        "other_interest": 500
    },
    "brokerage_transactions": [
        {"description": "AAPL", "proceeds": 15000, "cost_basis": 10000, "is_long_term": true},
        {"description": "TSLA", "proceeds": 8000, "cost_basis": 9500, "is_long_term": false},
        {"description": "MSFT", "proceeds": 25000, "cost_basis": 18000, "is_long_term": true}
    ],
    "deductions": {"state_income_tax_paid": 5000}
}' "" "1040,Schedule B,Schedule D,CA-540" ""

log "=== TC27: Freelancer with 1099-NEC income ==="
run_test "TC27: 1099-NEC Freelancer" '{
    "filing_status": "single",
    "username": "smoketest",
    "residence_state": "NY",
    "filer": {"first_name": "Dana", "last_name": "Rivera", "ssn": "XXX-XX-0028",
              "address_street": "700 Broadway", "address_city": "New York", "address_state": "NY", "address_zip": "10003"},
    "businesses": [
        {"business_name": "TechConsult LLC", "gross_receipts": 45000, "office_expense": 2000, "supplies": 1500},
        {"business_name": "Design Gigs", "gross_receipts": 12000, "car_expenses": 3000}
    ],
    "additional_income": {"other_interest": 200}
}' "owed" "1040,Schedule C,Schedule SE,IT-201" "yes"

log "=== TC28: Homeowner with mortgage (1098 deductions) ==="
run_test "TC28: Homeowner with mortgage" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "residence_state": "PA",
    "filer": {"first_name": "James", "last_name": "Cooper", "ssn": "XXX-XX-0029",
              "address_street": "800 Oak Ln", "address_city": "Philadelphia", "address_state": "PA", "address_zip": "19103"},
    "spouse": {"first_name": "Sarah", "last_name": "Cooper", "ssn": "XXX-XX-0030"},
    "num_dependents": 2,
    "additional_income": {"ordinary_dividends": 1500, "qualified_dividends": 1200},
    "deductions": {"mortgage_interest": 18750, "property_tax": 8500, "state_income_tax_paid": 4000, "charitable_cash": 3000}
}' "" "1040,PA-40" ""

log "=== TC29: Combined pipeline — all new form types ==="
run_test "TC29: Full pipeline (div + brokerage + business + mortgage)" '{
    "filing_status": "mfj",
    "username": "smoketest",
    "residence_state": "NJ",
    "work_states": ["NY"],
    "filer": {"first_name": "Pat", "last_name": "Kim", "ssn": "XXX-XX-0031",
              "address_street": "900 River Rd", "address_city": "Edgewater", "address_state": "NJ", "address_zip": "07020"},
    "spouse": {"first_name": "Lee", "last_name": "Kim", "ssn": "XXX-XX-0032"},
    "num_dependents": 1,
    "businesses": [{"business_name": "Kim Consulting", "gross_receipts": 35000, "office_expense": 3000, "supplies": 1000}],
    "additional_income": {
        "ordinary_dividends": 5000,
        "qualified_dividends": 3500,
        "other_interest": 1200
    },
    "brokerage_transactions": [
        {"description": "VTI ETF", "proceeds": 20000, "cost_basis": 15000, "is_long_term": true},
        {"description": "QQQ ETF", "proceeds": 5000, "cost_basis": 6000, "is_long_term": false}
    ],
    "deductions": {"mortgage_interest": 22000, "property_tax": 10000, "state_income_tax_paid": 8000, "charitable_cash": 5000}
}' "" "1040,Schedule A,Schedule B,Schedule C,Schedule D,Schedule SE,NJ-1040" "yes"


# ===========================================================================
# TC30: Plaid status endpoint
# ===========================================================================
log "=== TC30: Plaid Status ==="
PLAID_RES=$(curl -sk -H "X-API-Key: ${API_KEY}" "${API}/plaid/status" 2>&1)
if echo "$PLAID_RES" | jq -e '.enabled != null' >/dev/null 2>&1; then
    PLAID_ENV=$(echo "$PLAID_RES" | jq -r '.environment')
    pass "TC30: Plaid status endpoint — enabled=$(echo "$PLAID_RES" | jq -r '.enabled'), env=${PLAID_ENV}"
else
    fail "TC30: Plaid status endpoint failed"
fi

# ===========================================================================
# TC31: Plaid accounts (empty — no connected accounts)
# ===========================================================================
log "=== TC31: Plaid Accounts (empty) ==="
ACCT_RES=$(curl -sk -H "X-API-Key: ${API_KEY}" "${API}/plaid/accounts/smoketest" 2>&1)
if echo "$ACCT_RES" | jq -e '.accounts | length == 0' >/dev/null 2>&1; then
    pass "TC31: Empty Plaid accounts list for new user"
else
    fail "TC31: Expected empty accounts list"
fi

# ===========================================================================
# SUMMARY
# ===========================================================================
echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  TaxLens Smoke Test Results${NC}"
echo -e "${BLUE}==========================================${NC}"
echo -e "  ${GREEN}PASSED: ${PASS}${NC}"
echo -e "  ${RED}FAILED: ${FAIL}${NC}"
echo -e "  Total:  $((PASS + FAIL))"
echo ""

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo -e "${RED}Failed tests:${NC}"
    for e in "${ERRORS[@]}"; do
        echo -e "  ${RED}✗${NC} ${e}"
    done
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
