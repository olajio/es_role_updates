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
    "ccs_kibana_privileges": [
      "feature_discover.all",
      "feature_dashboard.all",
      "feature_visualize.all"
    ],
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
  ...

Default settings:
  Remote clusters: prod, qa, dev
  CCS cluster: ccs
  Remote inject patterns: partial-*, restored-*
  CCS inject patterns: partial-*, restored-*, elastic-cloud-logs-*
  CCS Kibana privileges: feature_dashboard.all, feature_discover.all, feature_visualize.all
```

---

## Step 5: Test Connection (Dry Run)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --dry-run
```

**Expected output:**
```
Analyzing: ELK-Analytics-Role
  [PROD] Needs 2 patterns: partial-*, restored-*
  [QA] Needs 2 patterns: partial-*, restored-*
  [DEV] Already has all required patterns
  [CCS] Needs 6 patterns:
    From injection: elastic-cloud-logs-*, partial-*, restored-*
    From prod sync: metricbeat-*
  [CCS] Needs Kibana privileges for 2 spaces:
    Spaces: space:analytics, space:operations
    Missing: feature_dashboard.all, feature_discover.all, feature_visualize.all

[DRY RUN] No changes made
```

---

## Step 6: Apply Updates

Once satisfied with the dry run, remove `--dry-run`:

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs
```

---

## What Gets Added

### Index Patterns

| Cluster Type | Patterns Added |
|--------------|----------------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` + synced from remotes |

### Kibana Privileges (CCS Only)

| Privilege | Purpose |
|-----------|---------|
| `feature_discover.all` | CSV export from Discover |
| `feature_dashboard.all` | PDF/PNG reports from Dashboard |
| `feature_visualize.all` | Full Visualize access |

**Note**: Kibana privileges are only added to spaces the role **already has access to**.

---

## Common Workflows

### Workflow 1: Full Update (Patterns + Kibana)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt
```

### Workflow 2: Patterns Only (No Kibana)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --skip-kibana-privileges
```

### Workflow 3: CCS Only (Patterns + Kibana)

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --skip-remote
```

### Workflow 4: Custom Kibana Privileges

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --ccs-kibana-privileges feature_discover.all feature_dashboard.all
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
| **Skip Kibana** | `--skip-kibana-privileges` |
| **Custom Kibana privs** | `--ccs-kibana-privileges priv1 priv2` |
| **Report only** | `--report-only` |

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

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection failed | Check URL and API key in config |
| Role not found | Verify role name (case-sensitive) |
| Permission denied | API key needs `manage_security` privilege |
| No Kibana update | Role has no Kibana spaces assigned (expected) |
| Already has privileges | Role already has required Kibana privileges |
| `*:filebeat-*` PIT error | Use explicit cluster names: `prod:filebeat-*,qa:filebeat-*` |

---

## Safety Checklist

- [ ] Created config with all cluster credentials
- [ ] Ran `--list-clusters` to verify config
- [ ] Ran with `--dry-run` first
- [ ] Reviewed the dry-run output
- [ ] Verified Kibana spaces are correct
- [ ] Backups enabled (don't use `--no-backup`)
- [ ] Ready to run without `--dry-run`

---

## Need More Help?

See the full [README.md](README.md) for detailed documentation.
