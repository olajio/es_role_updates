# Elasticsearch Role Auto-Updater (Multi-Cluster)

A Python tool for automatically synchronizing and updating Elasticsearch security roles across multiple clusters including Production, QA, Development, and Cross-Cluster Search (CCS) environments.

## Overview

This tool addresses common challenges in multi-cluster Elasticsearch environments:

1. **Pattern Injection (Remote Clusters)**: Adds `partial-*`, `restored-*` to roles in remote clusters (prod, qa, dev)
2. **Pattern Injection (CCS Cluster)**: Adds `partial-*`, `restored-*`, `elastic-cloud-logs-*` to CCS roles
3. **Pattern Synchronization**: Syncs index patterns from all remote clusters to corresponding CCS cluster roles
4. **Kibana Privileges (CCS Cluster)**: Grants `feature_discover.all`, `feature_dashboard.all`, `feature_visualize.all` for existing Kibana spaces

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REMOTE CLUSTERS                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │    PROD     │     │     QA      │     │     DEV     │               │
│  │   Cluster   │     │   Cluster   │     │   Cluster   │               │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘               │
│         │                   │                   │                       │
│         │ Inject: partial-*, restored-*         │                       │
│         │                   │                   │                       │
└─────────┼───────────────────┼───────────────────┼───────────────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │ Sync patterns
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          CCS CLUSTER                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Inject: partial-*, restored-*, elastic-cloud-logs-*            │   │
│  │  + Sync all patterns from remote clusters                        │   │
│  │  + Grant Kibana privileges for existing spaces                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Summary Tables

### Inject Patterns

| Cluster Type | Patterns Injected |
|--------------|-------------------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` |

### Kibana Privileges (CCS Only)

| Privilege | Description |
|-----------|-------------|
| `feature_discover.all` | Full Discover access including CSV export |
| `feature_dashboard.all` | Full Dashboard access including report generation |
| `feature_visualize.all` | Full Visualize access |

**Note**: Kibana privileges are only added to spaces that the role **already has access to**. The script does not add new space assignments.

## Features

- **Dynamic multi-cluster support**: Add any number of clusters to the configuration
- **Separate inject patterns**: Different patterns for remote clusters vs CCS cluster
- **Kibana privilege management**: Automatically grants reporting capabilities in CCS
- **Flexible cluster selection**: Choose which remote clusters to update and sync from
- **Selective updates**: Update specific roles via command line or from a file
- **Dry-run mode**: Preview changes without applying them
- **Automatic backups**: Creates JSON backups per cluster before modifications
- **Detailed logging**: Comprehensive logs with configurable verbosity
- **Report generation**: JSON reports with source tracking
- **Error handling**: Continue-on-error option for batch operations

## Requirements

- Python 3.7+
- `requests` library
- Network access to all Elasticsearch clusters
- API keys with `manage_security` privileges for each cluster

## Installation

```bash
# Clone or download the scripts
# Install dependencies
pip install requests

# Create your configuration file
cp es_clusters_config.json.example es_clusters_config.json
# Edit es_clusters_config.json with your cluster details
```

## Configuration

### Cluster Configuration File

Create a JSON configuration file with all your cluster credentials:

```json
{
  "clusters": {
    "prod": {
      "url": "https://prod-elasticsearch.example.com:9200",
      "api_key": "your-prod-api-key-here",
      "verify_ssl": false,
      "description": "Production Elasticsearch cluster"
    },
    "qa": {
      "url": "https://qa-elasticsearch.example.com:9200",
      "api_key": "your-qa-api-key-here",
      "verify_ssl": false,
      "description": "QA Elasticsearch cluster"
    },
    "dev": {
      "url": "https://dev-elasticsearch.example.com:9200",
      "api_key": "your-dev-api-key-here",
      "verify_ssl": false,
      "description": "Development Elasticsearch cluster"
    },
    "ccs": {
      "url": "https://ccs-elasticsearch.example.com:9200",
      "api_key": "your-ccs-api-key-here",
      "verify_ssl": false,
      "description": "Cross-Cluster Search Elasticsearch cluster"
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

### Configuration Fields

| Field | Description |
|-------|-------------|
| `clusters` | Dictionary of all cluster configurations |
| `clusters.<n>.url` | Full URL to the Elasticsearch cluster including port |
| `clusters.<n>.api_key` | Elasticsearch API key with security management privileges |
| `clusters.<n>.verify_ssl` | Set to `false` to skip SSL certificate verification |
| `clusters.<n>.description` | Optional description for logging purposes |
| `defaults.remote_inject_patterns` | Patterns to inject into remote cluster roles |
| `defaults.ccs_inject_patterns` | Patterns to inject into CCS cluster roles |
| `defaults.ccs_kibana_privileges` | Kibana privileges to grant in CCS for existing spaces |
| `defaults.remote_clusters` | Default remote clusters when not specified via CLI |
| `defaults.ccs_cluster` | Default CCS cluster when not specified via CLI |

## Usage

### Basic Syntax

```bash
python es_role_auto_update.py --config <config_file> [role_selection] [cluster_options] [options]
```

### Role Selection (one required)

| Option | Description |
|--------|-------------|
| `--roles ROLE1 ROLE2 ...` | Space-separated list of role names |
| `--role-file FILE` | Path to file containing role names (one per line) |
| `--all-matching` | Update all roles that exist in all specified clusters |

### Cluster Selection

| Option | Description |
|--------|-------------|
| `--remote-clusters CLUSTER1 CLUSTER2 ...` | Remote clusters to update (e.g., prod qa dev) |
| `--ccs-cluster CLUSTER` | CCS cluster to sync patterns to |
| `--skip-remote` | Skip updating remote clusters (only update CCS) |
| `--skip-ccs` | Skip updating CCS cluster (only update remote clusters) |
| `--list-clusters` | List available clusters from config and exit |

### Pattern Options

| Option | Description |
|--------|-------------|
| `--remote-inject-patterns PAT1 PAT2` | Override patterns for remote clusters |
| `--ccs-inject-patterns PAT1 PAT2` | Override patterns for CCS cluster |
| `--skip-inject` | Skip injecting all patterns |

### Kibana Privilege Options

| Option | Description |
|--------|-------------|
| `--ccs-kibana-privileges PRIV1 PRIV2` | Override Kibana privileges for CCS |
| `--skip-kibana-privileges` | Skip granting Kibana privileges in CCS |

### Common Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview changes without applying them |
| `--report-only` | Generate report without making changes |
| `--continue-on-error` | Don't stop on first failure |
| `--no-backup` | Skip backup creation (not recommended) |

## Examples

### List Available Clusters

```bash
python es_role_auto_update.py --config es_clusters_config.json --list-clusters
```

### Preview Changes (Dry Run)

```bash
# Update all clusters with defaults from config
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role ELK-Admin-Role \
  --dry-run
```

### Update Without Kibana Privileges

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --skip-kibana-privileges
```

### Update Roles from File

```bash
# Create a roles file
cat > roles.txt << EOF
ELK-Analytics-Role
ELK-Developer-Role
ELK-Operations-Role
EOF

# Run the update
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs
```

### Custom Kibana Privileges

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --ccs-kibana-privileges feature_discover.all feature_dashboard.all
```

## How Kibana Privileges Work

### What Gets Updated

1. The script extracts existing Kibana spaces from the role's `applications` section
2. For each space, it checks if the required privileges are present
3. If any privileges are missing, it adds a **new application entry** with all required privileges for all spaces

### Before and After Example

**Before:**
```json
{
  "applications": [
    {
      "application": "kibana-.kibana",
      "privileges": ["feature_discover.read", "feature_dashboard.read"],
      "resources": ["space:analytics", "space:operations"]
    }
  ]
}
```

**After:**
```json
{
  "applications": [
    {
      "application": "kibana-.kibana",
      "privileges": ["feature_discover.read", "feature_dashboard.read"],
      "resources": ["space:analytics", "space:operations"]
    },
    {
      "application": "kibana-.kibana",
      "privileges": ["feature_dashboard.all", "feature_discover.all", "feature_visualize.all"],
      "resources": ["space:analytics", "space:operations"]
    }
  ]
}
```

### What If a Role Has No Kibana Spaces?

If a role has no Kibana space assignments (no `applications` entries with `kibana` application), the script **skips** Kibana privilege updates for that role. It only enhances existing space access.

## Output Files

### Backups

Backups are stored per cluster in timestamped JSON files:

```
./backups/
├── prod/
│   └── roles_backup_20241210_143052.json
├── qa/
│   └── roles_backup_20241210_143052.json
├── dev/
│   └── roles_backup_20241210_143052.json
└── ccs/
    └── roles_backup_20241210_143052.json
```

### Report Format

The JSON report includes Kibana updates:

```json
{
  "timestamp": "2024-12-10T14:30:52.123456",
  "config": {
    "remote_inject_patterns": ["partial-*", "restored-*"],
    "ccs_inject_patterns": ["partial-*", "restored-*", "elastic-cloud-logs-*"],
    "ccs_kibana_privileges": ["feature_dashboard.all", "feature_discover.all", "feature_visualize.all"],
    "remote_clusters": ["prod", "qa", "dev"],
    "ccs_cluster": "ccs"
  },
  "summary": {
    "remote_clusters_updated": { "prod": 2, "qa": 2, "dev": 0 },
    "ccs_roles_to_update": 2,
    "ccs_kibana_updates": 2
  },
  "ccs_kibana_updates": {
    "ELK-Analytics-Role": {
      "spaces": ["space:analytics", "space:operations"],
      "missing_privileges": ["feature_discover.all", "feature_dashboard.all", "feature_visualize.all"]
    }
  }
}
```

## Troubleshooting

### Kibana Privileges Not Being Added

**Cause**: Role has no Kibana spaces assigned
**Solution**: This is expected. The script only enhances existing space access. Assign spaces to the role first via Kibana UI or API.

### Role Has Spaces But Still No Kibana Update

**Cause**: Role already has all required privileges
**Solution**: Check the dry-run output. If all privileges exist, no update is needed.

### CCS Wildcard PIT Error

**Cause**: Using `*:filebeat-*` pattern in CCS Discover
**Solution**: Use explicit cluster names: `prod:filebeat-*,qa:filebeat-*,dev:filebeat-*`

## File Structure

```
.
├── es_role_auto_update.py      # Main script
├── es_role_manager_utils.py    # Utility library
├── es_clusters_config.json     # Cluster configuration
├── roles.txt                   # (Optional) Role names file
├── backups/                    # Backup directory
│   ├── prod/
│   ├── qa/
│   ├── dev/
│   └── ccs/
└── logs/                       # Log directory
```

## Safety Features

1. **Dry-run mode**: Always test with `--dry-run` first
2. **Automatic backups**: Per-cluster backups before any modification
3. **Reserved role protection**: Built-in roles are automatically skipped
4. **No new spaces**: Kibana privileges only added to existing spaces
5. **Detailed logging**: Full audit trail of all operations

## Best Practices

1. **Always run `--dry-run` first** to preview changes
2. **Start with a single role** before batch updates
3. **Keep backups** - don't use `--no-backup` in production
4. **Review logs** after each run
5. **Use `--role-file`** for repeatable batch operations
6. **Store config securely** - the config file contains API keys

## License

Internal use only.

## Support

For issues or feature requests, contact the Infrastructure team.
