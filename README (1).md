# Elasticsearch Role Auto-Updater (Multi-Cluster)

A Python tool for automatically synchronizing and updating Elasticsearch security roles across Production (PROD) and Cross-Cluster Search (CCS) clusters.

## Overview

This tool addresses a common challenge in Elasticsearch CCS environments: ensuring that roles in the CCS cluster have the necessary index patterns for both local and remote data access. It automates the following tasks:

1. **Pattern Injection**: Adds required patterns (`partial-*`, `restored-*`) to roles in both PROD and CCS clusters
2. **Pattern Synchronization**: Syncs index patterns from PROD roles to corresponding CCS roles
3. **Backup Management**: Creates timestamped backups before any modifications

## Features

- **Multi-cluster support**: Connects to both PROD and CCS clusters simultaneously
- **Selective updates**: Update specific roles via command line or from a file
- **Dry-run mode**: Preview changes without applying them
- **Automatic backups**: Creates JSON backups before modifications
- **Detailed logging**: Comprehensive logs with configurable verbosity
- **Report generation**: JSON reports of planned/executed changes
- **Error handling**: Continue-on-error option for batch operations
- **Pattern deduplication**: Prevents duplicate patterns using normalized comparison

## Requirements

- Python 3.7+
- `requests` library
- Network access to both Elasticsearch clusters
- API keys with `manage_security` privileges for both clusters

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

Create a JSON configuration file with your cluster credentials:

```json
{
  "prod": {
    "url": "https://prod-elasticsearch.example.com:9200",
    "api_key": "your-prod-api-key-here",
    "verify_ssl": false,
    "description": "Production Elasticsearch cluster"
  },
  "ccs": {
    "url": "https://ccs-elasticsearch.example.com:9200",
    "api_key": "your-ccs-api-key-here",
    "verify_ssl": false,
    "description": "Cross-Cluster Search Elasticsearch cluster"
  }
}
```

| Field | Description |
|-------|-------------|
| `url` | Full URL to the Elasticsearch cluster including port |
| `api_key` | Elasticsearch API key with security management privileges |
| `verify_ssl` | Set to `false` to skip SSL certificate verification |
| `description` | Optional description for logging purposes |

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
python es_role_auto_update.py --config <config_file> [role_selection] [options]
```

### Role Selection (one required)

| Option | Description |
|--------|-------------|
| `--roles ROLE1 ROLE2 ...` | Space-separated list of role names |
| `--role-file FILE` | Path to file containing role names (one per line) |
| `--all-matching` | Update all roles that exist in both clusters |

### Common Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview changes without applying them |
| `--report-only` | Generate report without making changes |
| `--skip-prod` | Skip updating PROD cluster (CCS only) |
| `--skip-ccs` | Skip updating CCS cluster (PROD only) |
| `--skip-sync` | Skip syncing patterns from PROD to CCS |
| `--skip-inject` | Skip injecting required patterns |
| `--continue-on-error` | Don't stop on first failure |
| `--no-backup` | Skip backup creation (not recommended) |

### Additional Options

| Option | Default | Description |
|--------|---------|-------------|
| `--inject-patterns PAT1 PAT2` | `partial-* restored-*` | Custom patterns to inject |
| `--backup-dir DIR` | `./backups` | Directory for backup files |
| `--log-dir DIR` | `./logs` | Directory for log files |
| `--log-level LEVEL` | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |

## Examples

### Preview Changes (Dry Run)

```bash
# See what would change for specific roles
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role ELK-Admin-Role \
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
  --role-file roles.txt
```

### Update Only CCS Cluster

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --skip-prod
```

### Update Only PROD Cluster

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --skip-ccs
```

### Inject Custom Patterns

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Analytics-Role \
  --inject-patterns "partial-*" "restored-*" "snapshot-*"
```

### Generate Report Only

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --all-matching \
  --report-only
```

### Debug Mode

```bash
python es_role_auto_update.py \
  --config es_clusters_config.json \
  --roles ELK-Test-Role \
  --log-level DEBUG \
  --dry-run
```

## Output Files

### Backups

Backups are stored in timestamped JSON files:

```
./backups/
├── prod/
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

The JSON report includes:

```json
{
  "timestamp": "2024-12-10T14:30:52.123456",
  "config": {
    "inject_patterns": ["partial-*", "restored-*"]
  },
  "summary": {
    "prod_roles_to_update": 3,
    "ccs_roles_to_update": 5
  },
  "prod_updates": {
    "ELK-Analytics-Role": {
      "patterns_to_add": ["partial-*", "restored-*"],
      "count": 2
    }
  },
  "ccs_updates": {
    "ELK-Analytics-Role": {
      "patterns_to_add": ["partial-*", "restored-*", "metricbeat-*"],
      "count": 3,
      "sources": {
        "inject": ["partial-*", "restored-*"],
        "sync": ["metricbeat-*"]
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

Scoring criteria:
- +10 points per matching privilege
- +5 points if entry has only local patterns
- +1 point per existing pattern

### Update Sequence

1. **PROD cluster** is updated first (inject `partial-*`, `restored-*`)
2. **CCS cluster** is updated second (inject patterns + sync from PROD)

This order ensures PROD patterns are available for sync to CCS.

## Troubleshooting

### Connection Issues

```
Failed to connect to PROD cluster
```
- Verify the URL in your config file
- Check network connectivity
- Ensure API key has correct privileges

### Role Not Found

```
Role not found in PROD: ELK-Custom-Role
```
- Verify the role name spelling (case-sensitive)
- Check if the role exists in the cluster

### SSL Certificate Errors

Set `"verify_ssl": false` in your config file, or ensure proper CA certificates are installed.

### Permission Denied

Ensure your API key has the `manage_security` cluster privilege.

## File Structure

```
.
├── es_role_auto_update.py      # Main script
├── es_role_manager_utils.py    # Utility library
├── es_clusters_config.json     # Cluster configuration
├── roles.txt                   # (Optional) Role names file
├── backups/                    # Backup directory
│   ├── prod/
│   └── ccs/
└── logs/                       # Log directory
```

## Safety Features

1. **Dry-run mode**: Always test with `--dry-run` first
2. **Automatic backups**: Backups created before any modification
3. **Verification**: Post-update verification of changes
4. **Reserved role protection**: Built-in roles are automatically skipped
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
