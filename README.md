# Elasticsearch Role Auto-Updater (Multi-Cluster)

A Python tool for automatically synchronizing and updating Elasticsearch security roles across multiple clusters including Production, QA, Development, and Cross-Cluster Search (CCS) environments.

## Overview

This tool addresses common challenges in multi-cluster Elasticsearch environments:

1. **Pattern Injection (Remote Clusters)**: Adds `partial-*`, `restored-*` to roles in remote clusters (prod, qa, dev)
2. **Pattern Injection (CCS Cluster)**: Adds `partial-*`, `restored-*`, `elastic-cloud-logs-*` to CCS roles
3. **Pattern Synchronization**: Syncs index patterns from all remote clusters to corresponding CCS cluster roles
4. **Multi-Cluster Support**: Works with any number of clusters defined in a single configuration file

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
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Inject Patterns Summary

| Cluster Type | Patterns Injected |
|--------------|-------------------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` |

## Features

- **Dynamic multi-cluster support**: Add any number of clusters to the configuration
- **Separate inject patterns**: Different patterns for remote clusters vs CCS cluster
- **Flexible cluster selection**: Choose which remote clusters to update and sync from
- **Selective updates**: Update specific roles via command line or from a file
- **Dry-run mode**: Preview changes without applying them
- **Automatic backups**: Creates JSON backups per cluster before modifications
- **Detailed logging**: Comprehensive logs with configurable verbosity
- **Report generation**: JSON reports with source tracking (INJ vs SYNC per cluster)
- **Error handling**: Continue-on-error option for batch operations
- **Pattern deduplication**: Prevents duplicate patterns using normalized comparison
- **Backward compatible**: Supports old config formats

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
      "api_key": "PROD_API_KEY,
      "verify_ssl": false,
      "description": "Production Elasticsearch cluster"
    },
    "qa": {
      "url": "https://qa-elasticsearch.example.com:9200",
      "api_key": "QA_API_KEY",
      "verify_ssl": false,
      "description": "QA Elasticsearch cluster"
    },
    "dev": {
      "url": "https://dev-elasticsearch.example.com:9200",
      "api_key": "DEV_API_KEY",
      "verify_ssl": false,
      "description": "Development Elasticsearch cluster"
    },
    "ccs": {
      "url": "https://ccs-elasticsearch.example.com:9200",
      "api_key": "CCS_API_KEY",
      "verify_ssl": false,
      "description": "Cross-Cluster Search Elasticsearch cluster"
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

### Configuration Fields

| Field | Description |
|-------|-------------|
| `clusters` | Dictionary of all cluster configurations |
| `clusters.<name>.url` | Full URL to the Elasticsearch cluster including port |
| `clusters.<name>.api_key` | Elasticsearch API key with security management privileges |
| `clusters.<name>.verify_ssl` | Set to `false` to skip SSL certificate verification |
| `clusters.<name>.description` | Optional description for logging purposes |
| `defaults.remote_inject_patterns` | Patterns to inject into remote cluster roles |
| `defaults.ccs_inject_patterns` | Patterns to inject into CCS cluster roles |
| `defaults.remote_clusters` | Default remote clusters when not specified via CLI |
| `defaults.ccs_cluster` | Default CCS cluster when not specified via CLI |

### Adding New Clusters

Simply add a new entry to the `clusters` dictionary:

```json
{
  "clusters": {
    "prod": { ... },
    "qa": { ... },
    "dev": { ... },
    "staging": {
      "url": "https://staging-elasticsearch.example.com:9200",
      "api_key": "your-staging-api-key",
      "verify_ssl": false,
      "description": "Staging Elasticsearch cluster"
    },
    "ccs": { ... }
  },
  "defaults": {
    "remote_clusters": ["prod", "qa", "dev", "staging"],
    ...
  }
}
```

### Generating API Keys

```bash
# On each cluster, generate an API key with appropriate privileges
POST /_security/api_key
{
  "name": "role-updater-key",
  "role_descriptors": {
    "role_manager": {
      "cluster": ["manage_security"],
      "indices": [
        {
          "names": ["*"],
          "privileges": ["monitor"]
        }
      ]
    }
  }
}
```

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

### Common Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview changes without applying them |
| `--report-only` | Generate report without making changes |
| `--continue-on-error` | Don't stop on first failure |
| `--no-backup` | Skip backup creation (not recommended) |

### Additional Options

| Option | Default | Description |
|--------|---------|-------------|
| `--backup-dir DIR` | `./backups` | Directory for backup files |
| `--log-dir DIR` | `./logs` | Directory for log files |
| `--log-level LEVEL` | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |

## Examples

### List Available Clusters

```bash
python es_role_auto_update.py --config es_clusters_config.json --list-clusters
```

Output:
```
Available clusters in configuration:
------------------------------------------------------------
  prod            - https://prod-elasticsearch:9200
                    Production Elasticsearch cluster

  qa              - https://qa-elasticsearch:9200
                    QA Elasticsearch cluster

  dev             - https://dev-elasticsearch:9200
                    Development Elasticsearch cluster

  ccs             - https://ccs-elasticsearch:9200
                    Cross-Cluster Search Elasticsearch cluster

Default settings:
  Remote clusters: prod, qa, dev
  CCS cluster: ccs
  Remote inject patterns: partial-*, restored-*
  CCS inject patterns: partial-*, restored-*, elastic-cloud-logs-*
```

### Preview Changes (Dry Run)

```bash
# Update all clusters with defaults from config
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role ELK-Admin-Role \
  --dry-run

# Update specific remote clusters
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa \
  --ccs-cluster ccs \
  --dry-run
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

### Update Only Remote Clusters (No CCS)

```bash
# Add partial-*/restored-* to prod, qa, dev only
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --skip-ccs
```

### Update Only CCS (Sync from Remotes)

```bash
# Sync patterns from prod, qa, dev to CCS without modifying remotes
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod qa dev \
  --ccs-cluster ccs \
  --skip-remote
```

### Update Single Cluster

```bash
# Only update prod cluster
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod \
  --skip-ccs
```

### Use Config Defaults

```bash
# Uses remote_clusters and ccs_cluster from config defaults
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --role-file roles.txt
```

### Override Inject Patterns

```bash
# Custom patterns for this run only
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --remote-clusters prod \
  --ccs-cluster ccs \
  --remote-inject-patterns "partial-*" "restored-*" "snapshot-*" \
  --ccs-inject-patterns "partial-*" "restored-*" "elastic-cloud-logs-*" "audit-*"
```

### Debug Mode

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Test-Role \
  --remote-clusters prod \
  --ccs-cluster ccs \
  --log-level DEBUG \
  --dry-run
```

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

### Logs

Detailed logs are stored per execution:

```
./logs/
├── role_auto_update_20241210_143052.log
└── role_update_report_20241210_143052.json
```

### Report Format

The JSON report includes source tracking:

```json
{
  "timestamp": "2024-12-10T14:30:52.123456",
  "config": {
    "remote_inject_patterns": ["partial-*", "restored-*"],
    "ccs_inject_patterns": ["partial-*", "restored-*", "elastic-cloud-logs-*"],
    "remote_clusters": ["prod", "qa", "dev"],
    "ccs_cluster": "ccs"
  },
  "summary": {
    "remote_clusters_updated": {
      "prod": 2,
      "qa": 2,
      "dev": 3
    },
    "ccs_roles_to_update": 3
  },
  "remote_updates": {
    "prod": {
      "ELK-Analytics-Role": {
        "patterns_to_add": ["partial-*", "restored-*"],
        "count": 2
      }
    }
  },
  "ccs_updates": {
    "ELK-Analytics-Role": {
      "patterns_to_add": ["partial-*", "restored-*", "elastic-cloud-logs-*", "metricbeat-*"],
      "count": 4,
      "sources": {
        "inject": ["partial-*", "restored-*", "elastic-cloud-logs-*"],
        "sync": {
          "prod": ["metricbeat-*"]
        }
      }
    }
  }
}
```

## How It Works

### Pattern Matching Logic

The script uses **exact string matching** (not wildcard matching) for pattern comparison:

- `partial-*` ≠ `partial-restored-*` (different strings, both kept)
- `restored-*` ≠ `restored-filebeat-*` (different strings, both kept)
- Patterns are normalized for comparison but original format is preserved

### Pattern Injection Strategy

When adding patterns to a role, the script:

1. Finds the best matching `indices` entry using a scoring system
2. Appends new patterns to the existing `names` array
3. Only creates a new entry if no `indices` entries exist

### Update Sequence

1. **Remote clusters** are updated first (inject `partial-*`, `restored-*`)
2. **CCS cluster** is updated last (inject `partial-*`, `restored-*`, `elastic-cloud-logs-*` + sync from all remotes)

This order ensures all remote patterns are available for sync to CCS.

### Source Tracking

The CCS update report tracks where each pattern came from:

- `INJ:3` - 3 patterns from injection (partial-*, restored-*, elastic-cloud-logs-*)
- `PROD:1` - 1 pattern synced from prod cluster
- `QA:3` - 3 patterns synced from qa cluster
- `DEV:2` - 2 patterns synced from dev cluster

## CCS Troubleshooting

### Why `*:filebeat-*` Fails with PIT Error

The `*:` wildcard means "all configured remote clusters." If you get a PIT error:

1. **Check configured remotes**:
   ```
   GET _remote/info
   ```

2. **Common causes**:
   - Additional remote cluster configured that your role doesn't have permissions for
   - DR, monitoring, or other cluster in the remote config
   - One remote cluster is unreachable

3. **Solution**: Use explicit cluster names instead of `*:`:
   ```
   prod:filebeat-*,qa:filebeat-*,dev:filebeat-*
   ```

### Connection Issues

```
Failed to connect to prod cluster
```
- Verify the URL in your config file
- Check network connectivity
- Ensure API key has correct privileges

### Role Not Found

```
Role not found in prod: ELK-Custom-Role
```
- Verify the role name spelling (case-sensitive)
- Check if the role exists in the specific cluster

### SSL Certificate Errors

Set `"verify_ssl": false` in your config file for each cluster.

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
4. **Detailed logging**: Full audit trail of all operations
5. **Source tracking**: Know exactly where each pattern came from

## Best Practices

1. **Always run `--dry-run` first** to preview changes
2. **Start with a single role** before batch updates
3. **Keep backups** - don't use `--no-backup` in production
4. **Review logs** after each run
5. **Use `--role-file`** for repeatable batch operations
6. **Store config securely** - the config file contains API keys
7. **Update remote clusters first** before syncing to CCS
8. **Use explicit cluster names** in CCS queries instead of `*:`

## License

Internal use only.

## Support

For issues or feature requests, contact the Infrastructure team.
