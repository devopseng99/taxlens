#!/usr/bin/env bash
# TaxLens PostgreSQL backup script
# Runs pg_dump inside the PostgreSQL pod and copies the dump to a local path.
# Usage: ./scripts/backup-pg.sh [backup_dir]
# Default backup_dir: /opt/k8s-pers/vol1/backups/taxlens
#
# Intended to be run as a CronJob or manually before upgrades.
# Retains the last 7 daily backups by default (RETENTION_DAYS).

set -euo pipefail

NAMESPACE="${TAXLENS_DB_NAMESPACE:-taxlens-db}"
PG_POD="${TAXLENS_PG_POD:-taxlens-pg-0}"
PG_USER="${TAXLENS_PG_USER:-postgres}"
PG_DB="${TAXLENS_PG_DB:-taxlens}"
BACKUP_DIR="${1:-/opt/k8s-pers/vol1/backups/taxlens}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="taxlens-${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] Starting TaxLens PostgreSQL backup"
echo "  Namespace: ${NAMESPACE}"
echo "  Pod:       ${PG_POD}"
echo "  Database:  ${PG_DB}"
echo "  Output:    ${BACKUP_DIR}/${DUMP_FILE}"

# Ensure backup directory exists (on mgplcb05 via kubectl exec or local)
ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 "mkdir -p ${BACKUP_DIR}" 2>/dev/null || mkdir -p "${BACKUP_DIR}"

# Run pg_dump inside the pod and stream compressed output
kubectl exec -n "${NAMESPACE}" "${PG_POD}" -- \
    pg_dump -U "${PG_USER}" -d "${PG_DB}" --no-owner --no-acl --clean --if-exists | \
    gzip > "/tmp/${DUMP_FILE}"

# Copy to backup dir on node
cat "/tmp/${DUMP_FILE}" | ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
    "cat > ${BACKUP_DIR}/${DUMP_FILE}"
rm -f "/tmp/${DUMP_FILE}"

# Get backup size
SIZE=$(ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
    "stat -c%s ${BACKUP_DIR}/${DUMP_FILE}" 2>/dev/null || echo "unknown")
echo "[$(date -Iseconds)] Backup complete: ${DUMP_FILE} (${SIZE} bytes)"

# Prune old backups
PRUNED=$(ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
    "find ${BACKUP_DIR} -name 'taxlens-*.sql.gz' -mtime +${RETENTION_DAYS} -delete -print | wc -l" 2>/dev/null || echo "0")
echo "[$(date -Iseconds)] Pruned ${PRUNED} backup(s) older than ${RETENTION_DAYS} days"

# List remaining backups
echo ""
echo "Current backups:"
ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
    "ls -lh ${BACKUP_DIR}/taxlens-*.sql.gz 2>/dev/null || echo '  (none)'"

echo ""
echo "To restore: gunzip -c ${BACKUP_DIR}/${DUMP_FILE} | kubectl exec -i -n ${NAMESPACE} ${PG_POD} -- psql -U ${PG_USER} -d ${PG_DB}"
