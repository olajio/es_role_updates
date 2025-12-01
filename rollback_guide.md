# Elasticsearch Role Rollback Script - Usage Guide

## Quick Start

### Restore a Single Role

```bash
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key API_KEY \
  --roles Role1
```

### Restore Multiple Roles

```bash
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key API_KEY \
  --roles Role1 Role2 Role3
```

### Restore from a File

```bash
# Create a file with role names
cat > roles_to_restore.txt << EOF
Role1
Role2
Role4
EOF

# Restore those roles
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key API_KEY \
  --role-file roles_to_restore.txt
```

### Dry Run (Test Before Restoring)

```bash
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key API_KEY \
  --roles Role1 \
  --dry-run
```

## All Options

```
Required Arguments:
  --backup FILE         Path to backup file
  --api-key KEY         Elasticsearch API key

Role Selection (choose one):
  --roles ROLE1 ROLE2   Restore specific roles (space-separated)
  --role-file FILE      Restore roles listed in file (one per line)
  --all                 Restore ALL roles from backup (use with caution!)

Optional:
  --dry-run             Preview changes without actually restoring
  --continue-on-error   Keep going even if one role fails
```

## Configuration

Before running, edit the script and set your Elasticsearch URL:

```python
# Around line 34 in rollback_es_role_update.py
ELASTICSEARCH_URL = "https://localhost:9200"
```

## Common Scenarios

### Scenario 1: Undo Recent Changes to One Role

```bash
# Find the most recent backup
ls -lt backups/

# Dry run to see what would be restored
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --roles Role1 \
  --dry-run

# If it looks good, restore it
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --roles Role1
```

### Scenario 2: Restore Multiple Roles That Got Messed Up

```bash
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --roles Role1 Role3 Role2 \
  --continue-on-error
```

### Scenario 3: Restore All Roles (Nuclear Option)

```bash
# This restores EVERYTHING from the backup
# Use with caution!

python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --all \
  --dry-run

# If you're really sure...
python rollback_es_role_update.py \
  --backup backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --all
```

## Output Example

```
======================================================================
ELASTICSEARCH ROLE ROLLBACK
======================================================================

Elasticsearch URL: https://your-cluster:9200
Backup file: backups/roles_backup_20241129_140530.json

Testing connection...
✓ Connected to Elasticsearch
  Authenticated as: api_key_user

Loading backup file...
✓ Loaded backup file: backups/roles_backup_20241129_140530.json
  Total roles in backup: 150

Validating 3 role(s)...

Roles to restore: 3
  • Role1
  • Role2
  • Role3

Proceed with restore? (yes/no): yes

======================================================================
RESTORING ROLES
======================================================================

[1/3] Restoring: Role1
✓ Successfully restored: Role1

[2/3] Restoring: Role2
✓ Successfully restored: Role2

[3/3] Restoring: Role3
✓ Successfully restored: Role3

======================================================================
SUMMARY
======================================================================
Mode: LIVE RESTORE
Total roles processed: 3
Successfully restored: 3
Failed to restore: 0
```

## Role File Format

When using `--role-file`, the file should have one role name per line:

```
# roles_to_restore.txt
# Lines starting with # are comments

Role1
Role2
Role4

# You can add comments anywhere
Role3
```

## Safety Features

1. **Connection Test** - Verifies API key works before doing anything
2. **Backup Validation** - Checks that roles exist in the backup file
3. **Dry Run** - See what would be restored without making changes
4. **Confirmation Prompt** - Asks for confirmation before restoring (unless using --all)
5. **Detailed Output** - Shows exactly what's happening

## Common Errors

### "Backup file not found"

```bash
# Check the path is correct
ls -l backups/roles_backup_20241129_140530.json

# Use absolute path if needed
python rollback_es_role_update.py \
  --backup /full/path/to/backups/roles_backup_20241129_140530.json \
  --api-key $API_KEY \
  --roles Role1
```

### "Role not found in backup"

The role you're trying to restore doesn't exist in that backup file. Either:
- You have a typo in the role name
- The role was created after that backup was made
- You're using the wrong backup file

```bash
# List all roles in a backup
python -c "import json; f=open('backups/roles_backup_20241129.json'); print('\n'.join(sorted(json.load(f).keys())))"
```

### "Authentication failed"

Your API key is invalid or doesn't have the right permissions.

```bash
# Test your API key
curl -H "Authorization: ApiKey YOUR_KEY" https://cluster:9200/_security/_authenticate
```

## Best Practices

1. **Always dry-run first** - Use `--dry-run` to see what would happen
2. **Keep backups** - Don't delete old backups for at least 30 days
3. **Test in QA first** - If you have a QA environment, test there
4. **Verify after restore** - Check the role in Kibana to make sure it looks right
5. **Document why** - Keep notes on why you restored (incident log)

## Verifying the Restore

After restoring:

1. **Check in Kibana**
   - Stack Management → Security → Roles
   - Open the restored role
   - Verify it looks correct

2. **Test with a user**
   - Have someone with that role try to do their work
   - Verify they have the expected permissions

3. **Check the role via API**
   ```bash
   curl -H "Authorization: ApiKey YOUR_KEY" \
        https://cluster:9200/_security/role/Role1
   ```

## Multiple Clusters

Like the update script, just make copies for each environment:

```bash
# Create environment-specific copies
cp rollback_es_role_update.py es_role_rollback_prod.py
cp rollback_es_role_update.py es_role_rollback_qa.py

# Edit each with the right URL
# Then use:
python es_role_rollback_prod.py --backup backups/prod_backup.json --api-key $PROD_KEY --roles Role1
python es_role_rollback_qa.py --backup backups/qa_backup.json --api-key $QA_KEY --roles Role1
```

## Troubleshooting

**Script says role restored but it looks wrong in Kibana**
- Clear your browser cache and refresh
- Log out and back in
- Check if you used the right backup file

**Some roles restore, others fail**
- Use `--continue-on-error` to restore as many as possible
- Check the error messages for each failed role
- Look at the log output to see which ones succeeded

**Want to restore a role to its state from a specific time**
- Find the backup file from that time: `ls -lt backups/`
- Use that backup file in the command
- The script will restore the role exactly as it was when that backup was made

## Need Help?

```bash
# Show all options
python rollback_es_role_update.py --help
```
