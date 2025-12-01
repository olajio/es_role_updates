# Elasticsearch Role Manager for Cross-Cluster Search

Thisn script automatically fixes Elasticsearch roles so users can generate CSV reports when working with Cross-Cluster Search (CCS) remote indices.

## The Problem

Users with access to remote indices like `prod:filebeat-*` or `qa:metrics-*` can search across clusters just fine, but they can't generate CSV reports in Kibana. This is because Elasticsearch needs the role to also have access to the local equivalent (like `filebeat-*`) for CSV generation to work.

Manually adding these local patterns to dozens or hundreds of roles is tedious and error-prone. This tool does it for you.

## Script Workflow

The script:
1. Connects to the Elasticsearch cluster
2. Finds all roles with remote index access patterns (anything with `:` in the pattern. For example, `prod:filebeat-*`)
3. Creates backup of the roles
4. Figures out what corresponsding local patterns are needed (For example, `filebeat-*`)
5. Adds those local patterns to the roles
6. Logs everything along the way

It's smart about comma-separated patterns too - if you have `prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*`, it converts that to `traces-apm*,logs-apm*,metrics-apm*` while preserving the order so you can easily verify it worked.

## Requirements

- Python 3.8 or newer
- The `requests` library (`pip install requests`)
- An Elasticsearch API key with `manage_security` privilege

## Installation

```bash
# Get the script files (download from this repo)
# You need: es_role_auto_update.py and es_role_manager_utils.py

# Install the dependency
pip install requests

# Done!
```

## Configuration

Before you run anything, open `es_role_auto_update.py` and set the Elasticsearch URL:

```python
# Look for this around line 31
ELASTICSEARCH_URL = "https://es_cluster_url"
```


## Usage

The script has two modes: update everything, or update specific roles.

### Update All Roles

This goes through every role and adds the needed local patterns.

```bash
# Always start with a dry run to see what would change
python es_role_auto_update.py --api-key API_KEY --dry-run

# If that looks good, run it for real
python es_role_auto_update.py --api-key API_KEY
```

### Update Specific Roles

Maybe you only want to fix a handful of roles. You can list them on the command line:

```bash
python es_role_auto_update.py \
  --api-key API_KEY \
  --roles Role1 Role2 Role3
```

Or put them in a file (one per line):

```bash
# Create a file with role names
cat > roles.txt << EOF
Role1
Role2
Role3
EOF

# Run the script with that file
python es_role_auto_update.py --api-key API_KEY --role-file roles.txt
```

See `example_roles_to_update.txt` for an example file with comments.

### Generate a Report roles to update only

Want to see what needs updating without changing anything?

```bash
python es_role_auto_update.py --api-key API_KEY --report-only
```

This creates a JSON report in the `logs/` directory showing which roles need updates and what patterns would be added.

## Common Options

Here are the flags you'll use most often:

```bash
--dry-run              # See what would change without actually changing it
--report-only          # Generate a report without updating anything
--roles role1 role2    # Update only these specific roles
--role-file file.txt   # Update only the roles listed in this file
--log-level DEBUG      # Turn on detailed logging for troubleshooting
--continue-on-error    # Keep going even if updating one role fails
--force                # Update a role even if the script thinks it's already good
```

## Examples

### Example 1: First Time in Production

```bash
# Step 1: See what's out there
python es_role_auto_update.py --api-key API_KEY --report-only

# Step 2: Review the report
cat logs/role_update_report_*.json

# Step 3: Test run to see what would happen
python es_role_auto_update.py --api-key API_KEY --dry-run

# Step 4: Read the output carefully validate that it all make sense. It is recommended to run this script on a test role before applying it to all the other roles in the production environment

# Step 5: If yes, run the script
python es_role_auto_update.py --api-key API_KEY

# Step 6: Check the logs
tail -100 logs/role_auto_update_*.log
```

### Example 2: New Roles Just Got Created

```bash
# See if the new roles need updating
python es_role_auto_update.py --api-key API_KEY --report-only

# Update just those specific roles
python es_role_auto_update.py \
  --api-key API_KEY \
  --roles new-role-1 new-role-2 new-role-3
```

## Understanding the Output

When you run the script, you'll see output like this:

```
INFO - Elasticsearch Role Auto-Updater
INFO - Elasticsearch URL: https://es_cluster_url
INFO - Testing connection to Elasticsearch...
INFO - Successfully connected to Elasticsearch: 8.11.0
INFO - Retrieving all roles...
INFO - Retrieved 150 roles from Elasticsearch
INFO - Analyzing roles for required updates...
INFO - ✓ Role1: needs 2 patterns
INFO - ✓ Role2: needs 3 patterns
INFO - Found 25 roles that need updating
```

Then when it updates:

```
[1/25] Processing role: Role1
  Patterns to add: filebeat-*, metricbeat-*
  ✓ Successfully updated Role1
```

At the end you get a summary:

```
======================================================================
SUMMARY
======================================================================
Update mode: ALL ROLES
Total roles analyzed: 25
Successfully updated: 25
Failed to update: 0
Verified successfully: 25/25
```

## Files the Script Creates

### Backups

Every time you run the script (unless you use `--no-backup` which you really shouldn't), it creates a backup:

```
backups/roles_backup_20241129_140530.json
```

This is a complete snapshot of all the roles before any changes. Keep these around - you'll want them if you need to roll back.

### Logs

Detailed logs go here:

```
logs/role_auto_update_20241129_140530.log
```

These have everything - what the script found, what it changed, any errors, all of it. Check these after every run, especially in production.

### Reports

JSON reports with details on what was done:

```
logs/role_update_report_20241129_140530.json
```

Good for tracking what changed over time.

## Verifying It Worked

After running the script:

1. **Check the exit code**
   ```bash
   echo $?  # Should be 0 for success
   ```

2. **Look for errors in the logs**
   ```bash
   grep ERROR logs/role_auto_update_*.log
   ```

3. **Spot-check a few roles in Kibana**
   - Stack Management → Security → Roles
   - Open a role that was updated
   - Look at the Indices section
   - You should see both remote patterns (with cluster prefix) and local patterns (without prefix)

4. **Test CSV report generation**
   - Log in as a user with one of the updated roles
   - Go to Discover, search for some data
   - Try to generate a CSV report
   - It should work now

## Rolling Back

Every run creates a backup. If something goes wrong, here's how to restore a role:
