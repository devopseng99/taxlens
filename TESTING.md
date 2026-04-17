# TaxLens — Testing Commands Reference

Updated: 2026-04-17

## Smoke Test Suite (20 scenarios)

```bash
# Run all 20 smoke tests (creates drafts under "smoketest" user)
bash /var/lib/rancher/ansible/db/taxlens/tests/smoke_test_tax_drafts.sh

# Verbose mode (shows full JSON responses)
bash /var/lib/rancher/ansible/db/taxlens/tests/smoke_test_tax_drafts.sh --verbose
```

### Test Cases
| TC | Description | Status | Forms |
|----|-------------|--------|-------|
| TC01 | Single W-2 worker | single | 1040, Sch D, IL-1040 |
| TC02 | MFJ couple with investments | mfj | 1040, Sch B/D, IL-1040 |
| TC03 | HoH with CTC | hoh | 1040, Sch A, IL-1040 |
| TC04 | Freelance developer | single | 1040, Sch C/SE, IL-1040 |
| TC05 | Rideshare driver + W-2 MFJ | mfj | 1040, Sch C/SE, IL-1040 |
| TC06 | Restaurant owner | single | 1040, Sch C/SE, IL-1040 |
| TC07 | Multiple businesses | single | 1040, Sch A/B/C/D/SE, IL-1040 |
| TC08 | MFS high earner | mfs | 1040, Sch A/B/D, IL-1040 |
| TC09 | HoH freelance writer + CTC | hoh | 1040, Sch C/SE, IL-1040 |
| TC10 | MFJ dual-business couple | mfj | 1040, Sch A/B/C/D/SE, IL-1040 |
| TC11 | Low income single | single | 1040, IL-1040 |
| TC12 | High-income consultant underpaid | single | 1040, Sch A/B/C/D/SE, IL-1040 |
| TC13 | Nurse + tutor side hustle MFJ | mfj | 1040, Sch A/C/SE, IL-1040 |
| TC14 | Retired MFJ couple | mfj | 1040, Sch A/B/D, IL-1040 |
| TC15 | Young gig worker multi-platform | single | 1040, Sch C/SE, IL-1040 |
| TC16 | Real estate agent HoH | hoh | 1040, Sch A/C/SE, IL-1040 |
| TC17 | MFS crypto trader with losses | mfs | 1040, Sch B/D, IL-1040 |
| TC13a | Original Single (revalidation) | single | 1040, Sch D, IL-1040 |
| TC13b | Original MFJ (revalidation) | mfj | 1040, Sch B/D, IL-1040 |
| TC13c | Original HoH (revalidation) | hoh | 1040, Sch A, IL-1040 |

## API Draft Operations

```bash
API="https://dropit.istayintek.com/api"

# Create a tax draft
curl -sk -X POST "$API/tax-draft" \
  -H 'Content-Type: application/json' \
  -d '{"filing_status":"single","username":"hr1","filer":{"first_name":"Test","last_name":"User","ssn":"123-45-6789"}}'

# Get draft summary
curl -sk "$API/tax-draft/{draft_id}?username=hr1" | jq .

# List all drafts for a user
curl -sk "$API/tax-drafts/hr1" | jq '.drafts[] | {draft_id, filing_status, total_income}'

# List PDFs for a draft
curl -sk "$API/tax-draft/{draft_id}/pdfs?username=hr1" | jq .

# Download a specific PDF (inline)
curl -sk "$API/tax-draft/{draft_id}/pdf/1040?username=hr1" -o form_1040.pdf

# Download with forced download header
curl -sk "$API/tax-draft/{draft_id}/pdf/1040?username=hr1&download=true" -o form_1040.pdf
```

### Available form_name values
`summary`, `1040`, `schedule_a`, `schedule_b`, `schedule_c`, `schedule_d`, `schedule_se`, `il_1040`

## PDF Template Verification

```bash
# Verify templates match official IRS forms
for f in app/templates/*.pdf; do
  echo "$(sha256sum "$f" | cut -c1-12) $(basename $f) $(stat -c%s "$f") bytes"
done

# Compare with 26f25 tax-refs
diff <(sha256sum app/templates/f1040sa.pdf | cut -d' ' -f1) \
     <(sha256sum /var/lib/rancher/ansible/db/openfile-26f25/tax-refs/26f25/f1040sa.pdf | cut -d' ' -f1)

# Inspect fillable field names in a template
python3 -c "
import pypdf
r = pypdf.PdfReader('app/templates/f1040.pdf')
fields = r.get_fields()
print(f'{len(fields)} fields')
for name in sorted(fields.keys())[:20]:
    print(f'  {name}')
"
```

## Playwright E2E Testing

Playwright tests run via the central Playwright server (`playwright` namespace).

```bash
# Start port-forward to Playwright server
kubectl port-forward -n playwright svc/playwright-server 13000:3000 &

# Verify Playwright server is accessible
curl -s http://localhost:13000/health

# Connect via WebSocket (Node.js example)
const { chromium } = require('playwright');
const browser = await chromium.connectOverCDP('ws://localhost:13000/playwright/chromium');
```

### Playwright Test Scenarios
1. **UI Tab Navigation** — Verify Documents, Tax Drafts, Smoke Tests tabs load
2. **Draft Listing** — Verify drafts appear with correct filing status/income
3. **PDF Download Headers** — Verify `content-type: application/pdf` and `content-disposition: inline`
4. **PDF File Size** — Verify PDFs are proper IRS forms (100KB-1MB), not stubs

### Programmatic PDF Verification (curl)
```bash
# Check PDF headers for inline viewing
curl -skI "$API/tax-draft/{draft_id}/pdf/1040?username=hr1" | grep -i 'content-'

# Expected:
# content-type: application/pdf
# content-disposition: inline; filename="TaxLens_{draft_id}_1040.pdf"

# Verify PDF file size (should be 100KB+ for IRS forms)
curl -sk "$API/tax-draft/{draft_id}/pdf/1040?username=hr1" | wc -c
```

### Notes on Headless Chromium + PDFs
- Headless Chromium triggers download for PDF URLs instead of rendering inline
- This is expected browser behavior, not a bug
- Content-Disposition headers are correct (`inline`) — real browsers render PDFs fine
- For automated validation, use curl header checks instead of Playwright page assertions

## Pod-Level Verification

```bash
# Check deployed PDFs on PVC
kubectl exec -n taxlens deploy/taxlens-api -- ls -lh /data/documents/smoketest/drafts/

# Check specific draft files
kubectl exec -n taxlens deploy/taxlens-api -- ls -lh /data/documents/hr1/drafts/{draft_id}/

# Verify template files in container
kubectl exec -n taxlens deploy/taxlens-api -- ls -lh /app/templates/

# Check API logs
kubectl logs -n taxlens deploy/taxlens-api --tail=50
```

## Delete and Recreate All Drafts

```bash
# Delete smoketest drafts
kubectl exec -n taxlens deploy/taxlens-api -- sh -c 'rm -rf /data/documents/smoketest/drafts/*'

# Delete hr1 drafts
kubectl exec -n taxlens deploy/taxlens-api -- sh -c 'rm -rf /data/documents/hr1/drafts/*'

# Recreate via smoke test
bash /var/lib/rancher/ansible/db/taxlens/tests/smoke_test_tax_drafts.sh

# Recreate hr1 custom drafts (see examples in BACKLOG.md or run via API)
```

## Build & Deploy After Changes

```bash
# Build image
cd /var/lib/rancher/ansible/db/taxlens
podman build --network=host --no-cache -t localhost/taxlens-api:latest .

# Transfer to worker node
podman save localhost/taxlens-api:latest -o /tmp/tl.tar
cat /tmp/tl.tar | ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
  "cat > /tmp/tl.tar && sudo /var/lib/rancher/rke2/bin/ctr --address /run/k3s/containerd/containerd.sock -n k8s.io images import /tmp/tl.tar && rm /tmp/tl.tar"

# Redeploy
helm upgrade --install taxlens /var/lib/rancher/ansible/db/taxlens/taxlens-chart \
  --namespace=taxlens -f /var/lib/rancher/ansible/db/taxlens/overrides.yaml

# Verify
kubectl rollout status deploy/taxlens-api -n taxlens
bash /var/lib/rancher/ansible/db/taxlens/tests/smoke_test_tax_drafts.sh
```
