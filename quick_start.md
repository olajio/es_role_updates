# Quick Start Guide - Elasticsearch Role Manager

## Prerequisites

1. Python 3.8+ installed
2. `requests` library: `pip install requests`
3. Elasticsearch API key with `manage_security` privilege
4. Network access to your Elasticsearch cluster

## Installation

```bash
# Install dependencies
pip install requests

# Make scripts executable (optional)
chmod +x es_role_auto_update.py
chmod +x es_role_selective_update.py
```

## Quick Start Examples

### 1. See What Needs Updating (Dry Run)

```bash
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --dry-run
```

**Expected Output:**
```
INFO - Elasticsearch Role Auto-Updater
INFO - Testing connection to Elasticsearch...
INFO - Successfully connected to Elasticsearch: 8.11.0
INFO - Retrieving all roles...
INFO - Retrieved 150 roles from Elasticsearch
INFO - Analyzing roles for required updates...
INFO - ✓ ELK-Dev-600-Role: needs 2 patterns
INFO - ✓ elastic_rw_file: needs 3 patterns
...
INFO - Found 25 roles that need updating
```

### 2. Generate Report Only

```bash
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --report-only
```

**Check the report:**
```bash
cat logs/role_update_report_*.json
```

### 3. Update All Roles (Production)

```bash
# Step 1: Dry run
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --dry-run

# Step 2: Review output and backup location

# Step 3: Actual update
python es_role_auto_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY
```

### 4. Update Specific Roles

```bash
# Update specific roles by name
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --roles ELK-Dev-600-Role elastic_rw_file \
  --dry-run
```

### 5. Update from File

```bash
# Create roles file
cat > my_roles.txt << EOF
ELK-Dev-600-Role
ELK-PPM-690-Role
elastic_rw_file
EOF

# Update roles from file
python es_role_selective_update.py \
  --es-url https://your-es-cluster:9200 \
  --api-key YOUR_API_KEY \
  --role-file my_roles.txt
```

## Common Use Cases

### Use Case 1: First Time Setup

```bash
# 1. Test connection
python es_role_auto_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY \
  --report-only

# 2. If connection works, do dry run
python es_role_auto_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY \
  --dry-run

# 3. Review the dry run output carefully

# 4. Execute actual update
python es_role_auto_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY
```

### Use Case 2: Updating After New Roles Added

```bash
# Check what's new
python es_role_auto_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY \
  --report-only

# Update just the new roles
python es_role_selective_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY \
  --roles new-role-1 new-role-2
```

### Use Case 3: Troubleshooting a Specific Role

```bash
# Update with debug logging
python es_role_selective_update.py \
  --es-url https://localhost:9200 \
  --api-key YOUR_API_KEY \
  --roles problematic-role \
  --log-level DEBUG \
  --force

# Check the logs
cat logs/role_selective_update_*.log | less
```

## Understanding What the Script Does

### Example: Role with Remote Patterns

**Before:**
```json
{
  "ELK-Dev-600-Role": {
    "indices": [
      {
        "names": ["prod:filebeat-*", "qa:filebeat-*", "dev:filebeat-*"],
        "privileges": ["read", "view_index_metadata"]
      }
    ]
  }
}
```

**After:**
```json
{
  "ELK-Dev-600-Role": {
    "indices": [
      {
        "names": ["prod:filebeat-*", "qa:filebeat-*", "dev:filebeat-*"],
        "privileges": ["read", "view_index_metadata"]
      },
      {
        "names": ["filebeat-*"],
        "privileges": ["read", "view_index_metadata"]
      }
    ]
  }
}
```

### What Gets Added

For each remote pattern like:
- `prod:filebeat-*` → adds `filebeat-*`
- `qa:metricbeat-*` → adds `metricbeat-*`
- `*:logstash-*` → adds `logstash-*`

The script:
1. Identifies the base pattern (part after the colon)
2. Checks if it already exists locally
3. Adds it if missing
4. Uses the same privileges as the remote pattern

## Important Files

```
.
├── es_role_manager_utils.py      # Core functionality
├── es_role_auto_update.py        # Auto-update all roles
├── es_role_selective_update.py   # Update specific roles
├── requirements.txt               # Python dependencies
├── backups/                       # Role backups (created automatically)
│   └── roles_backup_TIMESTAMP.json
└── logs/                          # Log files (created automatically)
    ├── role_auto_update_TIMESTAMP.log
    ├── role_selective_update_TIMESTAMP.log
    ├── role_update_report_TIMESTAMP.json
    └── role_update_status_TIMESTAMP.json
```

## Checking Logs

### View recent log
```bash
tail -100 logs/role_auto_update_*.log
```

### Search for errors
```bash
grep ERROR logs/*.log
```

### View successful updates
```bash
grep "Successfully updated" logs/*.log
```

## Key Command Line Options

### Most Commonly Used

```bash
--dry-run              # Preview changes without updating
--report-only          # Generate report only (auto-update script)
--log-level DEBUG      # Enable detailed logging
--continue-on-error    # Don't stop if one role fails (selective script)
--no-verify           # Skip verification (faster but less safe)
```

### Safety Options

```bash
--no-backup           # Skip backup (NOT recommended for production)
```

## Rollback Example

If you need to restore a role:

```bash
# 1. Find the backup file
ls -lt backups/

# 2. Use Python to restore
python3 << EOF
import json
import requests

# Load backup
with open('backups/roles_backup_20241128_143022.json', 'r') as f:
    roles = json.load(f)

# Restore specific role
role_name = 'ELK-Dev-600-Role'
role_def = roles[role_name]

# Clean metadata
clean_def = {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}

# Update Elasticsearch
response = requests.put(
    'https://your-es-cluster:9200/_security/role/' + role_name,
    headers={
        'Authorization': 'ApiKey YOUR_API_KEY',
        'Content-Type': 'application/json'
    },
    json=clean_def,
    verify=False  # Only if SSL verification issues
)

print(f"Status: {response.status_code}")
print(response.json())
EOF
```

## Environment Variables Setup

For convenience, set up environment variables:

```bash
# Add to ~/.bashrc or ~/.zshrc
export ES_PROD_URL="https://prod-es.company.com:9200"
export ES_PROD_API_KEY="your-prod-api-key"
export ES_QA_URL="https://qa-es.company.com:9200"
export ES_QA_API_KEY="your-qa-api-key"

# Then use like:
python es_role_auto_update.py \
  --es-url "$ES_PROD_URL" \
  --api-key "$ES_PROD_API_KEY" \
  --dry-run
```

## Verification Checklist

After running the script:

- [ ] Check exit code: `echo $?` (should be 0 for success)
- [ ] Review the summary output
- [ ] Check log file for errors: `grep ERROR logs/*.log`
- [ ] Verify a few roles in Kibana
- [ ] Test CSV report generation with affected users
- [ ] Keep backup files for at least 30 days

## Getting Help

### Script Help

```bash
python es_role_auto_update.py --help
python es_role_selective_update.py --help
```

### Common Error Messages

**"Failed to connect to Elasticsearch"**
- Check URL is correct
- Verify network connectivity
- Check API key is valid

**"Permission denied"**
- API key needs `manage_security` privilege
- Check with: `curl -H "Authorization: ApiKey YOUR_KEY" https://es:9200/_security/_authenticate`

**"Role not found"**
- Typo in role name
- Role doesn't exist in cluster
- Check with: `curl -H "Authorization: ApiKey YOUR_KEY" https://es:9200/_security/role/ROLE_NAME`

## Next Steps

1. Review the full documentation: `ES_ROLE_MANAGER_README.md`
2. Test in a non-production environment first
3. Create a runbook for your team
4. Set up scheduled updates if needed
5. Integrate with your monitoring/alerting system

## Production Checklist

Before running in production:

- [ ] Tested in dev/QA environment
- [ ] Reviewed all roles to be updated
- [ ] Confirmed backup location is accessible
- [ ] Scheduled during maintenance window
- [ ] Stakeholders notified
- [ ] Rollback plan documented
- [ ] Monitoring in place for post-update issues

## Support

For issues or questions:
1. Check the full README: `ES_ROLE_MANAGER_README.md`
2. Review log files in `logs/` directory
3. Contact your Elasticsearch administrator
4. Create ticket with DevOps team
