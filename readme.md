# Elasticsearch Role Manager for Cross-Cluster Search

Thisn script automatically fixes Elasticsearch roles so users can generate CSV reports when working with Cross-Cluster Search (CCS) remote indices.

## The Problem

Users with access to remote indices like `prod:filebeat-*` or `qa:metrics-*` can search across clusters just fine, but they can't generate CSV reports in Kibana. This is because Elasticsearch needs the role to also have access to the local equivalent (like `filebeat-*`) for CSV generation to work.

Manually adding these local patterns to dozens or hundreds of roles is tedious and error-prone. This tool does it for you.

## What It Does

The script:
1. Connects to your Elasticsearch cluster
2. Finds all roles with remote index access patterns (anything with `:` in the pattern)
3. Figures out what local patterns are needed
4. Adds those local patterns to the roles
5. Creates backups and logs everything along the way

It's smart about comma-separated patterns too - if you have `prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*`, it converts that to `traces-apm*,logs-apm*,metrics-apm*` while preserving the order so you can easily verify it worked.

## Requirements

- Python 3.8 or newer
- The `requests` library (`pip install requests`)
- An Elasticsearch API key with `manage_security` privilege
- Network access to your Elasticsearch cluster

## Installation

```bash
# Get the files (download from your repo/shared drive/wherever)
# You need: es_role_auto_update.py and es_role_manager_utils.py

# Install the dependency
pip install requests

# Done!
```

## Configuration

Before you run anything, open `es_role_auto_update.py` and set your Elasticsearch URL:

```python
# Look for this around line 23
ELASTICSEARCH_URL = "https://localhost:9200"
```

Change `localhost:9200` to your actual cluster address. Examples:
- `"https://prod-es.company.com:9200"`
- `"https://10.1.2.3:9200"`
- `"https://my-cluster.us-east-1.aws.found.io:9243"`

If you manage multiple clusters, just make copies of the script with different URLs configured. See the [Multi-Cluster Setup](#multi-cluster-setup) section.

## Getting an API Key

You need an API key that can manage roles. Run this in Kibana Dev Tools:

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

Save the key as you won't be able to retrieve it after the first time the key is displayed.

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

### Just Generate a Report

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
python es_role_auto_update.py --api-key $API_KEY --report-only

# Step 2: Review the report
cat logs/role_update_report_*.json

# Step 3: Test run to see what would happen
python es_role_auto_update.py --api-key $API_KEY --dry-run

# Step 4: Read the output carefully validate that it all make sense. It is recommended to run this script on a test role before applying it to all the other roles in the production environment

# Step 5: If yes, do it
python es_role_auto_update.py --api-key $API_KEY

# Step 6: Check the logs
tail -100 logs/role_auto_update_*.log
```

### Example 2: New Roles Just Got Created

```bash
# See if the new roles need updating
python es_role_auto_update.py --api-key $API_KEY --report-only

# Update just those specific roles
python es_role_auto_update.py \
  --api-key $API_KEY \
  --roles new-role-1 new-role-2 new-role-3
```

### Example 3: Something's Not Right with One Role

```bash
# Turn on debug logging and force an update
python es_role_auto_update.py \
  --api-key $API_KEY \
  --roles problematic-role \
  --log-level DEBUG \
  --force

# Check what happened
cat logs/role_auto_update_*.log | grep -A 5 "problematic-role"
```

## Understanding the Output

When you run the script, you'll see output like this:

```
INFO - Elasticsearch Role Auto-Updater
INFO - Elasticsearch URL: https://your-cluster:9200
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

4. **Actually test CSV report generation**
   - Log in as a user with one of the updated roles
   - Go to Discover, search for some data
   - Try to generate a CSV report
   - It should work now

## Rolling Back

Every run creates a backup. If something goes wrong, here's how to restore a role:

```python
import json
import requests

# Load the backup file
with open('backups/roles_backup_20241129_140530.json', 'r') as f:
    roles = json.load(f)

# Get the role you want to restore
role_name = 'Role1'
role_def = roles[role_name]

# Clean out the metadata fields that shouldn't be in the update
clean_def = {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}

# Put it back
response = requests.put(
    f'https://your-cluster:9200/_security/role/{role_name}',
    headers={
        'Authorization': f'ApiKey YOUR_API_KEY',
        'Content-Type': 'application/json'
    },
    json=clean_def,
    verify=False  # only if you have SSL issues
)

print(f"Status: {response.status_code}")  # Should be 200
```

## Multi-Cluster Setup

If you manage multiple Elasticsearch clusters, make environment-specific copies of the script:

```bash
# Make copies for each environment
cp es_role_auto_update.py es_role_auto_update_prod.py
cp es_role_auto_update.py es_role_auto_update_qa.py
cp es_role_auto_update.py es_role_auto_update_dev.py

# Edit each one and set the right URL
# In es_role_auto_update_prod.py:
#   ELASTICSEARCH_URL = "https://prod-es.company.com:9200"
#
# In es_role_auto_update_qa.py:
#   ELASTICSEARCH_URL = "https://qa-es.company.com:9200"
#
# And so on...

# Now you can run them separately
python es_role_auto_update_prod.py --api-key $PROD_KEY
python es_role_auto_update_qa.py --api-key $QA_KEY
python es_role_auto_update_dev.py --api-key $DEV_KEY
```

## Troubleshooting

### "Failed to connect to Elasticsearch"

Check:
- Is the ELASTICSEARCH_URL in the script correct?
- Can you reach that host from where you're running the script?
- Try: `curl https://your-cluster:9200`
- If it's an SSL error, you might need to set `verify_ssl = False` in the script (but try to fix the SSL issue instead)

### "Permission denied" or "Unauthorized"

Check:
- Is your API key valid? `curl -H "Authorization: ApiKey API_KEY" https://cluster:9200/_security/_authenticate`
- Does the API key have `manage_security` privilege?
- Did you accidentally include quotes around the API key value?

### "Role not found"

- You have a typo in the role name
- The role doesn't exist in this cluster (maybe you're pointed at the wrong cluster?)
- List all roles: `curl -H "Authorization: ApiKey API_KEY" https://cluster:9200/_security/role`

### Script ran but CSV reports still don't work

- Double-check the role in Kibana - are the local patterns actually there?
- Is the user assigned this role?
- Do the indices actually exist?
- Try having the user log out and back in
- Check the local patterns match what you expect

### Role keeps showing up as needing updates

- This might mean there are patterns with different ordering
- Use `--log-level DEBUG` to see exactly what the script is comparing
- Check if the local pattern already exists but in a different format (spacing, order, etc.)

## Production Best Practices

Here's what to do when running this in production:

**Before:**
- Test in dev/QA first with the same types of roles you have in prod
- Run with `--dry-run` and actually read the output
- Schedule a maintenance window (even though the script is fast, be safe)
- Let stakeholders know this is happening
- Have your rollback procedure documented and ready
- Make sure you know where the backups are going and that you can access them

**During:**
- Monitor the output as it runs
- Keep the terminal session open until it's done
- If you see a lot of errors, Ctrl+C and investigate before continuing
- Use `--continue-on-error` if you're updating a lot of roles and don't want one failure to stop everything

**After:**
- Check the exit code (`echo $?` should be 0)
- Review the summary at the end of the output
- `grep ERROR logs/role_auto_update_*.log` to see if anything failed
- Spot-check a few roles in Kibana
- Test CSV report generation with a real user
- Keep the backup file - don't delete it for at least 30 days

## Security Notes

- **API keys are sensitive** - don't hardcode them in scripts, don't commit them to git, don't share them in Slack
- Store them in environment variables or use a secrets manager
- Rotate API keys periodically
- Use separate API keys for different environments (don't use your prod key in QA)
- Keep the log files secure - they might contain role names and index patterns
- Review who has access to run this script

## FAQ

**Q: Will this change reserved roles like kibana_system?**

A: No, the script automatically skips any role with `_reserved: true`.

**Q: What if the script fails halfway through updating 100 roles?**

A: Each role is updated independently. If one fails, the others that already succeeded are still updated. Use `--continue-on-error` to keep processing the rest.

**Q: Can I run this from a cron job?**

A: Yes, but make sure you're monitoring the logs and handling failures appropriately. And please don't run it more than once a day - there's usually no need.

**Q: Does this work with Elastic Cloud?**

A: Yep! Just set the ELASTICSEARCH_URL to your cloud endpoint.

**Q: Why do I need local patterns when I have remote patterns?**

A: It's a quirk of how CSV report generation works in Kibana. The export functionality needs to resolve index patterns locally, even for remote data. Adding the local pattern lets Elasticsearch properly route the export request.

**Q: Will this affect users currently using these roles?**

A: It only adds permissions, never removes them. Users might suddenly be able to do things they couldn't before (like generate CSV reports), but they won't lose any existing access.

**Q: What if a role already has some of the local patterns but not all?**

A: The script only adds the ones that are missing. It won't duplicate patterns that already exist.

## Getting Help

Need more info?
- Run `python es_role_auto_update.py --help` for all options
- Check `QUICK_START.md` for quick examples
- Look at your log files - they're very detailed
- Check the Elasticsearch documentation on roles and CCS

Still stuck? Talk to whoever gave you this script - they probably know your specific setup better than a generic README does.

## License

This is an internal tool. Use it responsibly, don't break production, and always have backups.
