# Elasticsearch Role Manager for Cross-Cluster Search (CCS)

A comprehensive Python toolkit for managing Elasticsearch roles in Cross-Cluster Search environments. This tool automatically updates roles that have remote index access patterns to include corresponding local index patterns, ensuring proper CSV report generation capabilities.

## Problem Statement

In Elasticsearch Cross-Cluster Search (CCS) environments, when roles have access to remote indices (e.g., `prod:filebeat-*`, `qa:filebeat-*`), users may not be able to generate CSV reports unless the role also has access to the corresponding local index pattern (e.g., `filebeat-*`).

This toolkit automates the process of:
1. Identifying roles with remote index patterns
2. Extracting the base index patterns
3. Adding the corresponding local index patterns to those roles
4. Verifying the changes were applied correctly

## Features

- ✅ **Two Update Modes**: Automatic update of all roles or selective update of specified roles
- ✅ **Automatic Backup**: Creates timestamped backups before making any changes
- ✅ **Dry Run Mode**: Preview changes without modifying roles
- ✅ **Comprehensive Logging**: Detailed logs for troubleshooting and audit trails
- ✅ **Verification**: Automatically verifies that changes were applied correctly
- ✅ **Error Handling**: Robust error handling with optional continue-on-error mode
- ✅ **Report Generation**: Creates detailed JSON reports of all operations
- ✅ **API Key Authentication**: Secure authentication using Elasticsearch API keys
- ✅ **Production-Ready**: Includes retry logic, validation, and rollback capabilities

## Requirements

- Python 3.8 or higher
- `requests` library
- Elasticsearch 7.x or 8.x cluster
- API key with appropriate permissions (manage_security privilege)

## Installation

1. Clone or download the files:
   ```bash
   # Download the files
   curl -O https://your-repo/es_role_manager_utils.py
   curl -O https://your-repo/es_role_auto_update.py
   curl -O https://your-repo/es_role_selective_update.py
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Make scripts executable (optional):
   ```bash
   chmod +x es_role_auto_update.py
   chmod +x es_role_selective_update.py
   ```

## Creating an API Key

You need an API key with `manage_security` cluster privilege:

```bash
# Using curl
curl -X POST "https://your-es-cluster:9200/_security/api_key" \
  -H "Content-Type: application/json" \
  -u elastic:your-password \
  -d '{
    "name": "role-manager-key",
    "role_descriptors": {
      "role-manager": {
        "cluster": ["manage_security", "manage"],
        "indices": [
          {
            "names": ["*"],
            "privileges": ["read", "monitor"]
          }
        ]
      }
    }
  }'
```

Or using Kibana Dev Tools:
```
POST /_security/api_key
{
  "name": "role-manager-key",
  "role_descriptors": {
    "role-manager": {
      "cluster": ["manage_security", "manage"],
      "indices": [
        {
          "names": ["*"],
          "privileges": ["read", "monitor"]
        }
      ]
    }
  }
}
```

Save the returned API key in a secure location.

## Usage

### Script 1: Automatic Update (All Roles)

Updates all roles that need updating automatically.

#### Basic Usage

```bash
# Dry run to see what would change
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --dry-run

# Actually update roles
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY
```

#### Advanced Options

```bash
# Custom backup and log directories
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --backup-dir /path/to/backups \
  --log-dir /path/to/logs \
  --log-level DEBUG

# Generate report only (no updates)
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --report-only

# Skip backup (not recommended for production)
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --no-backup
```

### Script 2: Selective Update (Specific Roles)

Updates only the roles you specify.

#### Basic Usage

```bash
# Update specific roles (command line)
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --roles ELK-Dev-600-Role ELK-AppSupport-GL-290-Role \
  --dry-run

# Update roles from a file
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --role-file roles_to_update.txt
```

#### Role File Format

Create a text file with one role name per line:

```
# roles_to_update.txt
# Lines starting with # are comments

ELK-Dev-600-Role
ELK-AppSupport-GL-290-Role
elastic_rw_file
ELK-PPM-690-Role
```

#### Advanced Options

```bash
# Continue updating even if one role fails
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --roles role1 role2 role3 \
  --continue-on-error

# Force update even if role appears current
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --roles problematic-role \
  --force

# Skip verification (faster, but less safe)
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --roles role1 \
  --no-verify
```

## Command Line Options

### Common Options (Both Scripts)

| Option | Description | Default |
|--------|-------------|---------|
| `--es-url` | Elasticsearch URL (required) | - |
| `--api-key` | API key for authentication (required) | - |
| `--backup-dir` | Directory for role backups | `./backups` |
| `--log-dir` | Directory for log files | `./logs` |
| `--dry-run` | Preview changes without updating | `False` |
| `--no-backup` | Skip backup creation | `False` |
| `--verify-ssl` | Verify SSL certificates | `False` |
| `--log-level` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |

### Auto Update Specific Options

| Option | Description | Default |
|--------|-------------|---------|
| `--report-only` | Generate report without updating | `False` |

### Selective Update Specific Options

| Option | Description | Default |
|--------|-------------|---------|
| `--roles` | Space-separated list of role names | - |
| `--role-file` | File containing role names | - |
| `--no-verify` | Skip verification after update | `False` |
| `--continue-on-error` | Continue if a role update fails | `False` |
| `--force` | Force update even if not needed | `False` |

## Output Files

### Backups

Backups are stored in timestamped JSON files:
```
backups/
  └── roles_backup_20241128_143022.json
```

### Logs

Detailed logs are created for each run:
```
logs/
  ├── role_auto_update_20241128_143022.log
  └── role_selective_update_20241128_143530.log
```

### Reports

JSON reports detail what was changed:
```
logs/
  ├── role_update_report_20241128_143022.json
  └── role_update_status_20241128_143530.json
```

## Example Workflows

### Workflow 1: Safe Production Update

```bash
# 1. Generate report to see what needs updating
python es_role_auto_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --report-only

# 2. Review the report
cat logs/role_update_report_*.json

# 3. Dry run to preview changes
python es_role_auto_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --dry-run

# 4. Execute actual updates
python es_role_auto_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY

# 5. Verify logs
tail -100 logs/role_auto_update_*.log
```

### Workflow 2: Update Specific Roles After Review

```bash
# 1. Get list of roles with remote patterns
python es_role_auto_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --report-only

# 2. Create a file with roles to update
cat > roles_to_update.txt << EOF
ELK-Dev-600-Role
ELK-PPM-690-Role
elastic_rw_file
EOF

# 3. Dry run with selected roles
python es_role_selective_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --role-file roles_to_update.txt \
  --dry-run

# 4. Execute updates
python es_role_selective_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --role-file roles_to_update.txt
```

### Workflow 3: Troubleshooting a Failed Update

```bash
# 1. Update with maximum logging
python es_role_selective_update.py \
  --es-url https://prod-es:9200 \
  --api-key $ES_API_KEY \
  --roles problematic-role \
  --log-level DEBUG \
  --force

# 2. Check detailed logs
cat logs/role_selective_update_*.log | grep ERROR

# 3. Restore from backup if needed
# (Use Elasticsearch restore API with backup file)
```

## Understanding the Output

### Console Output

During execution, you'll see:
- ✓ Successful operations
- ✗ Failed operations
- ○ Skipped operations (no changes needed)

### Log Levels

- **INFO**: Normal operations and progress
- **WARNING**: Non-critical issues (e.g., reserved roles skipped)
- **ERROR**: Failed operations
- **DEBUG**: Detailed information for troubleshooting

### Report Structure

The JSON report includes:
```json
{
  "timestamp": "2024-11-28T14:30:22.123456",
  "total_roles": 15,
  "roles": {
    "ELK-Dev-600-Role": {
      "patterns_to_add": ["filebeat-*", "metricbeat-*"],
      "pattern_count": 2
    }
  }
}
```

## Troubleshooting

### Connection Issues

```bash
# Test with curl first
curl -H "Authorization: ApiKey YOUR_API_KEY" \
  https://your-es-cluster:9200

# If SSL issues, disable verification (not recommended for production)
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY
```

### Permission Issues

Ensure your API key has `manage_security` privilege:
```bash
# Check API key info
curl -H "Authorization: ApiKey YOUR_API_KEY" \
  https://your-es-cluster:9200/_security/_authenticate
```

### Role Not Updating

1. Check if role is reserved (will be skipped automatically)
2. Use `--force` flag to force update
3. Enable DEBUG logging: `--log-level DEBUG`
4. Check the detailed log file

### Verification Failures

If verification fails but update succeeded:
1. Check Elasticsearch cluster health
2. Wait a few seconds and manually verify in Kibana
3. Check logs for specific error messages

## Rollback Procedure

If something goes wrong, you can restore from backups:

### Using the Backup File

```python
import json
import requests

# Load backup
with open('backups/roles_backup_20241128_143022.json', 'r') as f:
    roles = json.load(f)

# Restore a specific role
role_name = 'ELK-Dev-600-Role'
role_def = roles[role_name]

# Remove metadata fields that shouldn't be restored
clean_def = {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}

# Update Elasticsearch
response = requests.put(
    f'https://your-es-cluster:9200/_security/role/{role_name}',
    headers={
        'Authorization': f'ApiKey YOUR_API_KEY',
        'Content-Type': 'application/json'
    },
    json=clean_def
)
```

## Best Practices

### For Production Environments

1. **Always run dry-run first**: Use `--dry-run` to preview changes
2. **Review reports**: Check generated reports before proceeding
3. **Keep backups**: Default backup behavior is enabled for a reason
4. **Test in non-production first**: Validate the scripts in QA/Dev
5. **Use API keys**: More secure than basic authentication
6. **Review logs**: Always check logs after updates
7. **Schedule maintenance windows**: Run updates during low-traffic periods
8. **Version control backups**: Store backup files in version control
9. **Document changes**: Keep a changelog of role updates
10. **Monitor after changes**: Watch for any access issues after updates

### Security Considerations

1. **Protect API keys**: Store in environment variables or secret managers
2. **Limit API key scope**: Use minimum required privileges
3. **Rotate keys regularly**: Change API keys periodically
4. **Audit logs**: Keep logs for compliance and auditing
5. **Restrict access**: Limit who can run these scripts

## Advanced Usage

### Using Environment Variables

```bash
# Set environment variables
export ES_URL="https://your-es-cluster:9200"
export ES_API_KEY="your-api-key-here"

# Use in script
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY"
```

### Integrating with CI/CD

```bash
#!/bin/bash
# update_roles.sh

set -euo pipefail

# Load secrets
source /path/to/secrets.env

# Update roles
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --backup-dir /backups/elasticsearch/roles \
  --log-dir /logs/elasticsearch/roles

# Check exit code
if [ $? -eq 0 ]; then
  echo "Role update successful"
  # Send notification
else
  echo "Role update failed"
  # Send alert
  exit 1
fi
```

### Scheduled Updates with Cron

```bash
# Run weekly on Sunday at 2 AM
0 2 * * 0 /usr/bin/python3 /opt/scripts/es_role_auto_update.py --es-url "$ES_URL" --api-key "$ES_API_KEY" 2>&1 | tee -a /var/log/es-role-updates.log
```

## FAQ

**Q: Will this script modify reserved roles?**
A: No, reserved roles (marked with `_reserved: true`) are automatically skipped.

**Q: What happens if the script fails midway?**
A: Each role is updated individually. Failed roles won't affect successful updates. Use `--continue-on-error` to process all roles despite failures.

**Q: Can I run this against multiple clusters?**
A: Yes, run the script separately for each cluster with different `--es-url` values.

**Q: How do I know which roles need updating?**
A: Use `--report-only` or `--dry-run` to generate a report without making changes.

**Q: Is it safe to run this in production?**
A: Yes, when following best practices: use dry-run first, keep backups, and test in non-production first.

**Q: What if I need to restore a role?**
A: Use the backup JSON file and the Elasticsearch role API to restore the original definition.

## Support and Contributions

For issues, questions, or contributions, please contact your DevOps team or create an issue in your organization's repository.

## License

Internal use only. All rights reserved.
