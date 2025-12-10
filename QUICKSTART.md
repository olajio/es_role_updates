# Quick Start Guide: Elasticsearch Role Auto-Updater

Get up and running in 5 minutes.

---

## Step 1: Prerequisites

```bash
# Ensure Python 3.7+ is installed
python3 --version

# Install requests library
pip install requests
```

---

## Step 2: Download Files

Ensure you have these files in the same directory:

```
├── es_role_auto_update.py      # Main script
├── es_role_manager_utils.py    # Utility library
└── es_clusters_config.json     # Configuration (create this)
```

---

## Step 3: Configure Clusters

Create `es_clusters_config.json`:

```json
{
  "prod": {
    "url": "https://your-prod-cluster:9200",
    "api_key": "YOUR_PROD_API_KEY",
    "verify_ssl": false
  },
  "ccs": {
    "url": "https://your-ccs-cluster:9200",
    "api_key": "YOUR_CCS_API_KEY",
    "verify_ssl": false
  }
}
```

> **Getting API Keys**: Generate keys with `POST /_security/api_key` with `manage_security` privilege.

---

## Step 4: Create Roles File (Optional)

Create `roles.txt` with one role per line:

```
ELK-Analytics-Role
ELK-Developer-Role
ELK-Operations-Role
```

---

## Step 5: Test Connection (Dry Run)

```bash
# Test with a single role
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --dry-run
```

**Expected output:**
```
======================================================================
Elasticsearch Role Auto-Updater (Multi-Cluster)
======================================================================
Loading configuration from: es_clusters_config.json
  PROD: https://your-prod-cluster:9200
  CCS: https://your-ccs-cluster:9200

Connecting to PROD cluster...
✓ Connected to Elasticsearch 8.x.x
Connecting to CCS cluster...
✓ Connected to Elasticsearch 8.x.x

Analyzing: ELK-Analytics-Role
  [PROD] Needs 2 patterns: partial-*, restored-*
  [CCS] Needs 3 patterns:
    From injection: partial-*, restored-*
    From PROD sync: metricbeat-*

[DRY RUN] No changes made
```

---

## Step 6: Apply Updates

Once satisfied with the dry run, remove the `--dry-run` flag:

```bash
# Update from roles file
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt

# Or update specific roles
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role ELK-Developer-Role
```

---

## Common Commands

| Task | Command |
|------|---------|
| **Dry run** | `--dry-run` |
| **Update from file** | `--role-file roles.txt` |
| **Update specific roles** | `--roles Role1 Role2` |
| **CCS only** | `--skip-prod` |
| **PROD only** | `--skip-ccs` |
| **Skip pattern sync** | `--skip-sync` |
| **Report only** | `--report-only` |
| **Debug logging** | `--log-level DEBUG` |

---

## Quick Reference

```bash
# Full command structure
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt \
  --dry-run \
  --log-level INFO

# Minimal command (uses defaults)
python es_role_auto_update.py --config es_clusters_config.json --roles MyRole
```

---

## Output Locations

After running:

```
./backups/prod/roles_backup_YYYYMMDD_HHMMSS.json   # PROD backup
./backups/ccs/roles_backup_YYYYMMDD_HHMMSS.json    # CCS backup
./logs/role_auto_update_YYYYMMDD_HHMMSS.log        # Execution log
./logs/role_update_report_YYYYMMDD_HHMMSS.json     # JSON report
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection failed | Check URL and API key in config |
| Role not found | Verify role name (case-sensitive) |
| Permission denied | API key needs `manage_security` privilege |
| SSL errors | Set `"verify_ssl": false` in config |

---

## What Gets Added

The script adds these patterns where missing:

**To PROD roles:**
- `partial-*`
- `restored-*`

**To CCS roles:**
- `partial-*`
- `restored-*`
- All index patterns from corresponding PROD role

---

## Safety Checklist

- [ ] Created config file with correct credentials
- [ ] Ran with `--dry-run` first
- [ ] Reviewed the dry-run output
- [ ] Backups enabled (don't use `--no-backup`)
- [ ] Ready to run without `--dry-run`

---

## Need More Help?

See the full [README.md](README.md) for detailed documentation.
