# Quick Start Guide

## Prerequisites

You'll need:
- Python 3.8+
- An Elasticsearch API key with `manage_security` privilege
- Network access to your Elasticsearch cluster

## Installation

```bash
# Install the required library
pip install requests
```

## Configuration

**Important:** Before running the script, edit `es_role_auto_update.py` and set your Elasticsearch URL:

```python
ELASTICSEARCH_URL = "https://es_cluster_url:9200"  # Change this to the actual cluster URL
```

## Quick Start Examples

### 1. Dry Run

```bash
python es_role_auto_update.py --api-key API_KEY --dry-run
```

This shows you what would change without actually changing anything. Always start here.

### 2. Update Everything

```bash
# Preview changes
python es_role_auto_update.py --api-key API_KEY --dry-run

# If it looks good, run for the script
python es_role_auto_update.py --api-key API_KEY
```

### 3. Update a Few Roles

```bash
# Update specific roles by name
python es_role_auto_update.py \
  --api-key API_KEY \
  --roles ELK-Dev-600-Role elastic_rw_file \
  --dry-run

# Actually update roles
python es_role_auto_update.py \
  --api-key API_KEY \
  --roles ELK-Dev-600-Role elastic_rw_file
```

### 4. Update from a File

```bash
# Create a file with the roles you want to update
cat > roles.txt << EOF
ELK-Dev-600-Role
ELK-PPM-690-Role
elastic_rw_file
EOF

# Update those roles
python es_role_auto_update.py --api-key API_KEY --role-file roles.txt
```

### 5. Just Generate a Report

```bash
# See what needs updating without changing anything
python es_role_auto_update.py --api-key API_KEY --report-only

# Check the report
cat logs/role_update_report_*.json
```

## What the Script Actually Does

Say you have a role with these index patterns:

```
prod:filebeat-*
qa:filebeat-*
dev:filebeat-*
```

Users with this role can search across clusters but can't generate CSV reports. The script fixes this by adding:

```
filebeat-*
```

Now they can generate CSV reports.

### Comma-Separated Patterns

The script also handles patterns like this:

```
prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*
```

And converts them to:

```
traces-apm*,logs-apm*,metrics-apm*
```

The order stays the same so it's easy to verify it's correct.

## Common Scenarios

### First Time Running This

```bash
# 1. Make sure it connects
python es_role_auto_update.py --api-key YOUR_KEY --report-only

# 2. See what it wants to change
python es_role_auto_update.py --api-key YOUR_KEY --dry-run

# 3. Read through the output carefully

# 4. If everything looks right, do it
python es_role_auto_update.py --api-key YOUR_KEY
```

### After adding new Roles

```bash
# Check what's new
python es_role_auto_update.py --api-key YOUR_KEY --report-only

# Update just those new roles
python es_role_auto_update.py \
  --api-key YOUR_KEY \
  --roles new-role-1 new-role-2
```

## Backup and Log Files locations

```
backups/
  └── roles_backup_TIMESTAMP.json     # Automatic backups of your roles

logs/
  ├── role_auto_update_TIMESTAMP.log  # Detailed log of what happened
  └── role_update_report_TIMESTAMP.json  # JSON report of changes
```

The script creates these automatically. I recommend keeping the log and backup files for a while

## Useful Options

### Safety First
```bash
--dry-run              # Preview without changing anything
--report-only          # Just generate a report
--log-level DEBUG      # To get more detailed logging of everything that's happening
```

### Additional options
```bash
--continue-on-error    # Don't stop if one role fails
--force                # Update even if it thinks nothing changed
```

## Validating roles update

After running the script:

```bash
# Look at the summary
# (it prints automatically at the end)

# Check for errors
grep ERROR logs/role_auto_update_*.log

# See what got updated
grep "Successfully updated" logs/role_auto_update_*.log
```

In Kibana:
1. Go to Stack Management → Security → Roles
2. Open one of the roles you updated
3. Look at the Indices section
4. You should see both the remote patterns (with cluster names) and local patterns

## Rollback role updates

Every time the script runs, it creates a backup. To restore a role, run the [rollback_es_role_update.py script](https://github.com/olajio/es_role_updates/blob/main/rollback_es_role_update.py)

For more details, check out the full [README.md](https://github.com/olajio/es_role_updates/blob/main/readme.md).
