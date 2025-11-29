# Quick Start Guide

## Before You Begin

You'll need:
- Python 3.8+
- An Elasticsearch API key with `manage_security` privilege
- Network access to your Elasticsearch cluster

## Installation

```bash
# Install the required library
pip install requests

# That's it - you're ready to go
```

## Configuration

**Important:** Before running the script, edit `es_role_auto_update.py` and set your Elasticsearch URL:

```python
# Around line 23 in es_role_auto_update.py
ELASTICSEARCH_URL = "https://localhost:9200"  # Change this to your cluster URL
```

For example:
- Production: `"https://prod-es.company.com:9200"`
- QA: `"https://qa-es.company.com:9200"`
- Local: `"https://localhost:9200"`

## Creating an API Key

You need an API key with the right permissions. Use Kibana Dev Tools:

```
POST /_security/api_key
{
  "name": "role-manager-key",
  "role_descriptors": {
    "role-manager": {
      "cluster": ["manage_security"],
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

Save that API key somewhere safe - you'll need it for every run.

## Quick Start Examples

### 1. See What Needs Updating (Dry Run)

```bash
python es_role_auto_update.py --api-key YOUR_API_KEY --dry-run
```

This shows you what would change without actually changing anything. Always start here.

### 2. Update Everything

```bash
# Preview changes
python es_role_auto_update.py --api-key YOUR_API_KEY --dry-run

# If it looks good, run for real
python es_role_auto_update.py --api-key YOUR_API_KEY
```

### 3. Update Just a Few Roles

```bash
# Update specific roles by name
python es_role_auto_update.py \
  --api-key YOUR_API_KEY \
  --roles ELK-Dev-600-Role elastic_rw_file \
  --dry-run

# Looks good? Run it
python es_role_auto_update.py \
  --api-key YOUR_API_KEY \
  --roles ELK-Dev-600-Role elastic_rw_file
```

### 4. Update from a File

```bash
# Create a file with the roles you want to update
cat > my_roles.txt << EOF
ELK-Dev-600-Role
ELK-PPM-690-Role
elastic_rw_file
EOF

# Update those roles
python es_role_auto_update.py --api-key YOUR_API_KEY --role-file my_roles.txt
```

### 5. Just Generate a Report

```bash
# See what needs updating without changing anything
python es_role_auto_update.py --api-key YOUR_API_KEY --report-only

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

Now they can generate CSV reports. Simple as that.

### Comma-Separated Patterns

The script also handles patterns like this:

```
prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*
```

And converts them to:

```
traces-apm*,logs-apm*,metrics-apm*
```

The order stays the same so you can easily verify it's correct.

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

### You Just Added Some New Roles

```bash
# Check what's new
python es_role_auto_update.py --api-key YOUR_KEY --report-only

# Update just those new roles
python es_role_auto_update.py \
  --api-key YOUR_KEY \
  --roles new-role-1 new-role-2
```

### Something's Wrong with One Role

```bash
# Turn on debug logging to see what's happening
python es_role_auto_update.py \
  --api-key YOUR_KEY \
  --roles problematic-role \
  --log-level DEBUG \
  --force

# Check the log
tail -100 logs/role_auto_update_*.log
```

## Important Files to Know

```
backups/
  └── roles_backup_TIMESTAMP.json     # Automatic backups of your roles

logs/
  ├── role_auto_update_TIMESTAMP.log  # Detailed log of what happened
  └── role_update_report_TIMESTAMP.json  # JSON report of changes
```

The script creates these automatically. Keep the backups around for at least a month.

## Useful Options

### Safety First
```bash
--dry-run              # Preview without changing anything
--report-only          # Just generate a report
--log-level DEBUG      # See everything that's happening
```

### If Things Go Wrong
```bash
--continue-on-error    # Don't stop if one role fails
--force                # Update even if it thinks nothing changed
```

### Not Recommended
```bash
--no-backup           # Skip backups (seriously, don't do this in production)
```

## Checking Your Work

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

## If You Need to Undo Something

Every time the script runs, it creates a backup. Here's how to restore a role:

```python
import json
import requests

# Load the backup
with open('backups/roles_backup_TIMESTAMP.json', 'r') as f:
    roles = json.load(f)

# Get the role you want to restore
role_name = 'ELK-Dev-600-Role'
role_def = roles[role_name]

# Clean out metadata fields
clean_def = {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}

# Restore it
response = requests.put(
    f'https://your-cluster:9200/_security/role/{role_name}',
    headers={
        'Authorization': f'ApiKey YOUR_API_KEY',
        'Content-Type': 'application/json'
    },
    json=clean_def,
    verify=False  # if you have SSL issues
)

print(response.status_code)  # Should be 200
```

## Multiple Clusters?

Just make copies of the script with different configurations:

```bash
# Copy the script
cp es_role_auto_update.py es_role_auto_update_prod.py
cp es_role_auto_update.py es_role_auto_update_qa.py

# Edit each one with the right URL
# es_role_auto_update_prod.py: ELASTICSEARCH_URL = "https://prod-es:9200"
# es_role_auto_update_qa.py: ELASTICSEARCH_URL = "https://qa-es:9200"

# Run them separately
python es_role_auto_update_prod.py --api-key $PROD_KEY
python es_role_auto_update_qa.py --api-key $QA_KEY
```

## Quick Tips

- Always run `--dry-run` first in production
- Keep backups for 30+ days
- If you're updating a lot of roles, use `--continue-on-error` so one failure doesn't stop everything
- Check the logs after every run
- Test CSV report generation to make sure it actually worked

## Common Issues

**"Failed to connect"**
- Check the ELASTICSEARCH_URL in the script
- Make sure you can reach the cluster from where you're running this
- Try: `curl https://your-cluster:9200`

**"Permission denied"**
- Your API key needs `manage_security` privilege
- Check it: `curl -H "Authorization: ApiKey YOUR_KEY" https://your-cluster:9200/_security/_authenticate`

**"Role not found"**
- You probably have a typo in the role name
- List all roles: `curl -H "Authorization: ApiKey YOUR_KEY" https://your-cluster:9200/_security/role`

**Script runs but CSV reports still don't work**
- Make sure the user is actually assigned the role
- Check that the indices exist
- Look at the role in Kibana to verify the local patterns were added

## Production Checklist

Before running in production:

- [ ] Tested in dev/QA environment first
- [ ] Ran with `--dry-run` and reviewed the output
- [ ] Have a maintenance window (this is quick but be safe)
- [ ] Know where the backups are going
- [ ] Have the rollback procedure ready
- [ ] Told stakeholders this is happening

After running:

- [ ] Exit code was 0 (success)
- [ ] No errors in the logs
- [ ] Spot-checked a few roles in Kibana
- [ ] Tested CSV report generation
- [ ] Kept the backup file

## Need Help?

```bash
# Show all available options
python es_role_auto_update.py --help
```

For more details, check out the full README.md.
