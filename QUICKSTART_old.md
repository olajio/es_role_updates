# Quick Start Guide: Elasticsearch Role Auto-Updater (Multi-Cluster)

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

## Step 3: Configure All Clusters

Create `es_clusters_config.json`:

```json
{
  "clusters": {
    "prod": {
      "url": "https://your-prod-cluster:9200",
      "api_key": "YOUR_PROD_API_KEY",
      "verify_ssl": false,
      "description": "Production cluster"
    },
    "qa": {
      "url": "https://your-qa-cluster:9200",
      "api_key": "YOUR_QA_API_KEY",
      "verify_ssl": false,
      "description": "QA cluster"
    },
    "dev": {
      "url": "https://your-dev-cluster:9200",
      "api_key": "YOUR_DEV_API_KEY",
      "verify_ssl": false,
      "description": "Development cluster"
    },
    "ccs": {
      "url": "https://your-ccs-cluster:9200",
      "api_key": "YOUR_CCS_API_KEY",
      "verify_ssl": false,
      "description": "Cross-Cluster Search cluster"
    }
  },
  "defaults": {
    "remote_inject_patterns": ["partial-*", "restored-*"],
    "ccs_inject_patterns": ["partial-*", "restored-*", "elastic-cloud-logs-*"],
    "remote_clusters": ["prod", "qa", "dev"],
    "ccs_cluster": "ccs"
  }
}
```

> **Getting API Keys**: Generate on each cluster with `POST /_security/api_key` with `manage_security` privilege.

---

## Step 4: Verify Configuration

```bash
# List all configured clusters
python es_role_auto_update.py --config es_clusters_config.json --list-clusters
```

**Expected output:**
```
Available clusters in configuration:
------------------------------------------------------------
  prod            - https://your-prod-cluster:9200
                    Production cluster

  qa              - https://your-qa-cluster:9200
                    QA cluster

  dev             - https://your-dev-cluster:9200
                    Development cluster

  ccs             - https://your-ccs-cluster:9200
                    Cross-Cluster Search cluster

Default settings:
  Remote clusters: prod, qa, dev
  CCS cluster: ccs
  Remote inject patterns: partial-*, restored-*
  CCS inject patterns: partial-*, restored-*, elastic-cloud-logs-*
```

---

## Step 5: Create Roles File (Optional)

Create `roles.txt` with one role per line:

```
ELK-Analytics-Role
ELK-Developer-Role
ELK-Operations-Role
```

---

## Step 6: Test Connection (Dry Run)

```bash
# Test with a single role across all clusters
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --dry-run
```

**Expected output:**
```
======================================================================
Elasticsearch Role Auto-Updater (Multi-Cluster)
======================================================================

Remote inject patterns: partial-*, restored-*
CCS inject patterns: elastic-cloud-logs-*, partial-*, restored-*

Connecting to PROD cluster...
✓ Connected to Elasticsearch 8.x.x
Retrieved 45 roles from prod

Connecting to QA cluster...
✓ Connected to Elasticsearch 8.x.x
Retrieved 42 roles from qa

Connecting to DEV cluster...
✓ Connected to Elasticsearch 8.x.x
Retrieved 38 roles from dev

Connecting to CCS (CCS) cluster...
✓ Connected to Elasticsearch 8.x.x
Retrieved 50 roles from ccs

Analyzing: ELK-Analytics-Role
  [PROD] Needs 2 patterns: partial-*, restored-*
  [QA] Needs 2 patterns: partial-*, restored-*
  [DEV] Already has all required patterns
  [CCS] Needs 6 patterns:
    From injection: elastic-cloud-logs-*, partial-*, restored-*
    From prod sync: metricbeat-*
    From qa sync: custom-qa-*, qa-logs-*

[DRY RUN] No changes made
```

---

## Step 7: Apply Updates

Once satisfied with the dry run, remove `--dry-run`:

```bash
# Full update: all remote clusters + CCS
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs
```

---

## What Gets Added

| Cluster Type | Patterns Added |
|--------------|----------------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` + all unique patterns from remote clusters |

---

## Common Workflows

### Workflow 1: Update Everything

```bash
# Uses defaults from config file
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt
```

### Workflow 2: Update Only PROD + CCS

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod \
  --ccs-cluster ccs
```

### Workflow 3: Update Remote Clusters Only (No CCS)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --skip-ccs
```

### Workflow 4: Sync to CCS Only (Don't Modify Remotes)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --skip-remote
```

---

## Command Reference

| Task | Command |
|------|---------|
| **List clusters** | `--list-clusters` |
| **Dry run** | `--dry-run` |
| **From file** | `--role-file roles.txt` |
| **Specific roles** | `--roles Role1 Role2` |
| **Select remotes** | `--remote-clusters prod qa` |
| **Select CCS** | `--ccs-cluster ccs` |
| **Skip remotes** | `--skip-remote` |
| **Skip CCS** | `--skip-ccs` |
| **Report only** | `--report-only` |
| **Debug** | `--log-level DEBUG` |
| **Custom remote patterns** | `--remote-inject-patterns "partial-*" "restored-*"` |
| **Custom CCS patterns** | `--ccs-inject-patterns "partial-*" "restored-*" "elastic-cloud-logs-*"` |

---

## Output Locations

After running:

```
./backups/
├── prod/roles_backup_YYYYMMDD_HHMMSS.json
├── qa/roles_backup_YYYYMMDD_HHMMSS.json
├── dev/roles_backup_YYYYMMDD_HHMMSS.json
└── ccs/roles_backup_YYYYMMDD_HHMMSS.json

./logs/
├── role_auto_update_YYYYMMDD_HHMMSS.log
└── role_update_report_YYYYMMDD_HHMMSS.json
```

---

## Adding a New Cluster

1. Add to `es_clusters_config.json`:
```json
{
  "clusters": {
    "staging": {
      "url": "https://staging-cluster:9200",
      "api_key": "STAGING_API_KEY",
      "verify_ssl": false
    }
  }
}
```

2. Use it:
```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles MyRole \
  --remote-clusters prod qa dev staging \
  --ccs-cluster ccs
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection failed | Check URL and API key in config |
| Role not found | Verify role name (case-sensitive) |
| Permission denied | API key needs `manage_security` privilege |
| SSL errors | Set `"verify_ssl": false` in config |
| `*:filebeat-*` PIT error | Use explicit cluster names: `prod:filebeat-*,qa:filebeat-*` |

---

## Safety Checklist

- [ ] Created config with all cluster credentials
- [ ] Ran `--list-clusters` to verify config
- [ ] Ran with `--dry-run` first
- [ ] Reviewed the dry-run output
- [ ] Backups enabled (don't use `--no-backup`)
- [ ] Ready to run without `--dry-run`

---

## Need More Help?

See the full [README.md](README.md) for detailed documentation.
