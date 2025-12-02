# Elasticsearch Role Auto-Updater
---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Solution Architecture](#solution-architecture)
4. [Components](#components)
5. [Requirements](#requirements)
6. [Installation & Setup](#installation--setup)
7. [Configuration](#configuration)
8. [Usage - Role Updates](#usage---role-updates)
9. [Usage - Role Rollback](#usage---role-rollback)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)
12. [Security Considerations](#security-considerations)
13. [Support & Contact](#support--contact)

---

## Overview

The Elasticsearch Role Auto-Updater is a Python-based automation tool designed to manage Elasticsearch roles in Cross-Cluster Search (CCS) environments. It automatically identifies and updates roles that require local index access patterns for CSV report generation functionality.

**Key Capabilities:**
- Automatically identifies roles with remote index access patterns
- Adds corresponding local index patterns to enable CSV report generation
- Supports bulk updates or selective role updates
- Includes comprehensive rollback capabilities
- Provides detailed logging and audit trails
- Creates automatic backups before any changes

**Use Cases:**
- Enabling CSV report generation for users with CCS remote access
- Bulk role updates after cluster migrations or reorganizations
- Maintaining consistent role configurations across environments
- Recovering from accidental role modifications

---

## Problem Statement

### The Issue

In Elasticsearch Cross-Cluster Search (CCS) deployments, roles configured with remote index access patterns (e.g., `prod:filebeat-*`, `qa:metricbeat-*`, `dev:logs-*`) allow users to search and visualize data across clusters. However, due to how Kibana's CSV export functionality works, users with only remote index access cannot generate CSV reports.

**Technical Root Cause:**

When Kibana generates CSV reports, it needs to resolve index patterns locally within the current cluster context. Remote index patterns (with cluster prefixes like `prod:filebeat-*`) are not resolved for CSV generation, even though they work fine for search queries.

**Impact:**

- Users cannot export search results to CSV
- Reporting workflows are broken
- Manual workarounds are time-consuming and error-prone
- Affects potentially hundreds of roles across multiple environments

### The Solution

The tool automatically adds corresponding local index patterns alongside existing remote patterns. For example:

```
Before:
  - prod:filebeat-*
  - qa:filebeat-*
  - dev:filebeat-*

After:
  - prod:filebeat-*
  - qa:filebeat-*
  - dev:filebeat-*
  - filebeat-*           ← Added automatically
```

This enables CSV generation while maintaining all existing remote access capabilities.

---

## Solution Architecture

### Design Principles

1. **Safety First**: Automatic backups, dry-run mode, verification steps
2. **Idempotent**: Can be run multiple times safely without creating duplicates
3. **Transparent**: Detailed logging of all operations
4. **Flexible**: Supports multiple update modes and scenarios
5. **Recoverable**: Built-in rollback capabilities

### Workflow Diagram

```
┌─────────────────┐
│   Start Script  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Test Connection│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Retrieve Roles │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Create Backup  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Analyze Roles  │
│  - Extract      │
│    remote       │
│    patterns     │
│  - Identify     │
│    missing      │
│    local        │
│    patterns     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Update Roles   │
│  - Add local    │
│    patterns     │
│  - Preserve     │
│    privileges   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Verify Updates │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Generate      │
│   Report        │
└─────────────────┘
```

---

## Components

### Primary Scripts

#### 1. es_role_auto_update.py

**Purpose:** Main automation script for updating roles

**Functions:**
- Connects to Elasticsearch cluster
- Analyzes roles for remote index patterns
- Adds corresponding local patterns
- Creates backups and logs
- Verifies changes

**Update Modes:**
- **All Roles Mode**: Updates every role that needs updating
- **Selective Mode**: Updates only specified roles (via command line or file)
- **Report Only Mode**: Generates analysis without making changes
- **Dry Run Mode**: Shows what would change without actually changing it

#### 2. es_role_manager_utils.py

**Purpose:** Core utility library

**Key Functions:**
- `extract_remote_patterns()`: Identifies remote index patterns
- `get_base_patterns()`: Extracts local equivalents
- `needs_update()`: Determines if a role requires updates
- `add_local_patterns_to_role()`: Adds local patterns to role definition
- Pattern normalization and deduplication logic

**Features:**
- Handles simple patterns: `prod:filebeat-*`
- Handles comma-separated patterns: `prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*`
- Preserves original pattern order for readability
- Prevents duplicate pattern additions
- Maintains role privilege structures

#### 3. es_role_rollback.py

**Purpose:** Restores roles from backup files

**Capabilities:**
- Single role restoration
- Multiple role restoration
- Bulk restoration from file
- Full backup restoration (all roles)
- Dry-run mode for testing
- Validation and error handling

### Supporting Files

#### example_roles_to_update.txt
Template file showing role list format for selective updates

#### requirements.txt
Python dependencies (currently just `requests`)

#### Documentation Files
- **README.md**: Comprehensive user guide
- **QUICK_START.md**: Quick reference for common tasks
- **ROLLBACK_GUIDE.md**: Detailed rollback procedures

### Generated Files

#### Backups
- Location: `./backups/`
- Format: `roles_backup_YYYYMMDD_HHMMSS.json`
- Content: Complete snapshot of roles before changes
- Retention: Recommended 30+ days

#### Logs
- Location: `./logs/`
- Format: `role_auto_update_YYYYMMDD_HHMMSS.log`
- Content: Detailed operation logs, errors, debug info
- Retention: Recommended 90 days

#### Reports
- Location: `./logs/`
- Format: `role_update_report_YYYYMMDD_HHMMSS.json`
- Content: Structured data about changes made
- Use: Audit trails, change tracking, compliance

---

## Requirements

### System Requirements

- **Python Version**: 3.8 or higher
- **Operating System**: Linux, macOS, or Windows with Python
- **Network**: HTTP/HTTPS access to Elasticsearch cluster
- **Disk Space**: Minimal (backups typically < 10MB)

### Elasticsearch Requirements

- **Version**: 7.x or 8.x
- **Cluster Type**: Cross-Cluster Search (CCS) configuration
- **API Access**: HTTPS endpoint accessible
- **Authentication**: API key with appropriate privileges

### API Key Requirements

The API key must have the following privileges:

```json
{
  "cluster": ["manage_security"],
  "indices": [
    {
      "names": ["*"],
      "privileges": ["read", "monitor"]
    }
  ]
}
```

**Creating the API Key:**

Via Kibana Dev Tools:
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

**Important**: Save the returned API key securely. It cannot be retrieved later.

### Python Dependencies

```bash
pip install requests
```

---

## Installation & Setup

### Step 1: Obtain the Scripts

Download or clone the scripts from the internal repository:

```bash
# Clone from internal repo
git clone https://github.com/your-org/elasticsearch-role-manager.git
cd elasticsearch-role-manager

# Or download directly
curl -O https://internal-repo/es_role_auto_update.py
curl -O https://internal-repo/es_role_manager_utils.py
curl -O https://internal-repo/es_role_rollback.py
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install requests
```

### Step 3: Verify Files

Ensure you have the required files:
```bash
ls -1
es_role_auto_update.py
es_role_manager_utils.py
es_role_rollback.py
example_roles_to_update.txt
README.md
QUICK_START.md
ROLLBACK_GUIDE.md
```

### Step 4: Test Python Version

```bash
python --version
# Should show 3.8 or higher
```

---

## Configuration

### Primary Configuration: Elasticsearch URL

**Location:** Inside each Python script (lines 20-25 typically)

**What to Configure:**

```python
# In es_role_auto_update.py
ELASTICSEARCH_URL = "https://localhost:9200"

# In es_role_rollback.py
ELASTICSEARCH_URL = "https://localhost:9200"
```

**Change to your actual cluster URL:**

```python
# Production cluster
ELASTICSEARCH_URL = "https://prod-es.company.com:9200"

# QA cluster
ELASTICSEARCH_URL = "https://qa-es.company.com:9200"

# Elastic Cloud
ELASTICSEARCH_URL = "https://my-deployment.es.us-east-1.aws.found.io:9243"
```

### Multi-Environment Setup

For managing multiple environments, create environment-specific copies:

```bash
# Create copies for each environment
cp es_role_auto_update.py es_role_auto_update_prod.py
cp es_role_auto_update.py es_role_auto_update_qa.py
cp es_role_auto_update.py es_role_auto_update_dev.py

# Edit each file and set the appropriate ELASTICSEARCH_URL
# Repeat for rollback script if needed
```

### Directory Structure

The scripts will automatically create these directories:

```
project_root/
├── es_role_auto_update.py
├── es_role_manager_utils.py
├── es_role_rollback.py
├── backups/                    ← Created automatically
│   ├── roles_backup_20241129_140530.json
│   └── roles_backup_20241129_160245.json
└── logs/                       ← Created automatically
    ├── role_auto_update_20241129_140530.log
    └── role_update_report_20241129_140530.json
```

### Optional Configuration

**Backup Directory:** Default is `./backups`, can be changed with `--backup-dir`

**Log Directory:** Default is `./logs`, can be changed with `--log-dir`

**SSL Verification:** Set `verify_ssl = False` in the scripts if you have SSL issues (not recommended for production)

---

## Usage - Role Updates

### Quick Reference

```bash
# See what needs updating
python es_role_auto_update.py --api-key KEY --report-only

# Dry run (preview changes)
python es_role_auto_update.py --api-key KEY --dry-run

# Update all roles
python es_role_auto_update.py --api-key KEY

# Update specific roles
python es_role_auto_update.py --api-key KEY --roles Role1 Role2

# Update from file
python es_role_auto_update.py --api-key KEY --role-file roles.txt
```

### Detailed Usage Scenarios

#### Scenario 1: First-Time Production Deployment

**Objective:** Update all roles that need local patterns

**Steps:**

1. **Generate a report to see what's out there**
   ```bash
   python es_role_auto_update.py --api-key $API_KEY --report-only
   ```

2. **Review the report**
   ```bash
   cat logs/role_update_report_*.json
   ```

3. **Run a dry run to preview changes**
   ```bash
   python es_role_auto_update.py --api-key $API_KEY --dry-run
   ```

4. **Review the output carefully**
   - How many roles will be updated?
   - Do the patterns make sense?
   - Any unexpected roles showing up?

5. **Execute the actual update**
   ```bash
   python es_role_auto_update.py --api-key $API_KEY
   ```

6. **Review logs and verify**
   ```bash
   # Check for errors
   grep ERROR logs/role_auto_update_*.log
   
   # View summary
   tail -50 logs/role_auto_update_*.log
   ```

**Expected Results:**
```
======================================================================
SUMMARY
======================================================================
Update mode: ALL ROLES
Total roles analyzed: 150
Successfully updated: 47
Failed to update: 0
Verified successfully: 47/47

Backup location: backups/roles_backup_20241129_140530.json
Log file: logs/role_auto_update_20241129_140530.log
```

#### Scenario 2: Update Specific Roles After Creation

**Objective:** Update only newly created roles

**Steps:**

1. **Identify the new roles**
   ```bash
   # Get list of roles that need updating
   python es_role_auto_update.py --api-key $API_KEY --report-only
   
   # Review report to identify new roles
   cat logs/role_update_report_*.json | jq '.roles | keys'
   ```

2. **Update specific roles**
   ```bash
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --roles ELK-New-Role-1 ELK-New-Role-2 \
     --dry-run
   
   # If looks good, run without dry-run
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --roles ELK-New-Role-1 ELK-New-Role-2
   ```

#### Scenario 3: Bulk Update from List

**Objective:** Update a curated list of roles

**Steps:**

1. **Create a role list file**
   ```bash
   cat > roles_to_update.txt << 'EOF'
   # Development roles
   ELK-Dev-600-Role
   ELK-Dev-FE-619-Role
   
   # Application Support
   ELK-AppSupport-GL-290-Role
   ELK-AppSupport-Core-Services-210-Role
   
   # Infrastructure
   elastic_rw_file
   elastic_ro_metric
   EOF
   ```

2. **Test with dry-run**
   ```bash
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --role-file roles_to_update.txt \
     --dry-run
   ```

3. **Execute the update**
   ```bash
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --role-file roles_to_update.txt
   ```

#### Scenario 4: Troubleshooting a Problematic Role

**Objective:** Update a role that keeps failing

**Steps:**

1. **Enable debug logging**
   ```bash
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --roles Problematic-Role \
     --log-level DEBUG \
     --dry-run
   ```

2. **Review detailed logs**
   ```bash
   cat logs/role_auto_update_*.log | grep -A 10 "Problematic-Role"
   ```

3. **Force the update if needed**
   ```bash
   python es_role_auto_update.py \
     --api-key $API_KEY \
     --roles Problematic-Role \
     --force
   ```

### Command-Line Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--api-key KEY` | Elasticsearch API key (required) | - |
| `--roles ROLE1 ROLE2` | Update specific roles | All roles |
| `--role-file FILE` | Update roles from file | - |
| `--dry-run` | Preview changes without updating | False |
| `--report-only` | Generate report only | False |
| `--backup-dir DIR` | Custom backup directory | ./backups |
| `--log-dir DIR` | Custom log directory | ./logs |
| `--log-level LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |
| `--continue-on-error` | Continue if one role fails | False |
| `--force` | Update even if appears current | False |
| `--no-backup` | Skip backup creation | False |

---

## Usage - Role Rollback

### Quick Reference

```bash
# Restore a single role
python es_role_rollback.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --roles Role1

# Restore multiple roles
python es_role_rollback.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --roles Role1 Role2 Role3

# Restore from file
python es_role_rollback.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --role-file roles.txt

# Dry run first
python es_role_rollback.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --roles Role1 \
  --dry-run
```

### Rollback Scenarios

#### Scenario 1: Undo Recent Changes to One Role

**Problem:** A role was updated incorrectly and needs to be restored

**Steps:**

1. **Find the appropriate backup**
   ```bash
   ls -lt backups/
   # Identify the backup from before the bad change
   ```

2. **Dry run the restore**
   ```bash
   python es_role_rollback.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --roles ELK-Dev-600-Role \
     --dry-run
   ```

3. **Review the output**
   - Does the backup contain the correct version?
   - Are the index patterns what you expect?

4. **Perform the restore**
   ```bash
   python es_role_rollback.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --roles ELK-Dev-600-Role
   ```

5. **Verify in Kibana**
   - Stack Management → Security → Roles
   - Open the role and verify it looks correct

#### Scenario 2: Bulk Rollback After Failed Update

**Problem:** An update went wrong and multiple roles need to be restored

**Steps:**

1. **Identify affected roles**
   ```bash
   # Check the log from the failed update
   grep "Failed to update" logs/role_auto_update_*.log
   ```

2. **Create rollback file**
   ```bash
   cat > roles_to_restore.txt << EOF
   ELK-Dev-600-Role
   ELK-PPM-690-Role
   elastic_rw_file
   EOF
   ```

3. **Restore from file with error handling**
   ```bash
   python es_role_rollback.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --role-file roles_to_restore.txt \
     --continue-on-error
   ```

#### Scenario 3: Restore All Roles (Nuclear Option)

**Problem:** Major issue requires full rollback

**⚠️ WARNING:** This restores ALL roles from the backup. Use with extreme caution.

**Steps:**

1. **Verify you have the correct backup**
   ```bash
   # List all roles in the backup
   python -c "import json; print('\n'.join(json.load(open('backups/roles_backup_20241129.json')).keys()))" | head -20
   ```

2. **Dry run first (MANDATORY)**
   ```bash
   python es_role_rollback.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --all \
     --dry-run
   ```

3. **Get approval**
   - Document the reason for full restore
   - Get manager/team lead approval
   - Notify stakeholders

4. **Perform the restore**
   ```bash
   python es_role_rollback.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --all
   ```

### Rollback Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--backup FILE` | Path to backup file (required) | - |
| `--api-key KEY` | Elasticsearch API key (required) | - |
| `--roles ROLE1 ROLE2` | Restore specific roles | - |
| `--role-file FILE` | Restore roles from file | - |
| `--all` | Restore ALL roles (use with caution) | - |
| `--dry-run` | Preview without restoring | False |
| `--continue-on-error` | Continue if one role fails | False |

---

## Best Practices

### Pre-Deployment

**Planning:**
- [ ] Test in non-production environment first (QA/Dev)
- [ ] Identify all roles that will be affected
- [ ] Review role list with stakeholders
- [ ] Schedule maintenance window if required
- [ ] Prepare rollback plan and document it
- [ ] Verify backup directory has sufficient space

**Communication:**
- [ ] Notify users who will be affected
- [ ] Inform security team about role changes
- [ ] Update change management tickets
- [ ] Prepare status update templates

**Validation:**
- [ ] Test API key has correct permissions
- [ ] Verify network connectivity to cluster
- [ ] Run report-only mode to see scope
- [ ] Review generated report with team

### During Deployment

**Execution:**
- [ ] Always run dry-run first
- [ ] Review dry-run output line by line
- [ ] Keep terminal session open during execution
- [ ] Monitor cluster health during updates
- [ ] Watch for any error messages

**If Issues Occur:**
- Don't panic - each role is independent
- Use `--continue-on-error` to complete remaining roles
- Document which roles failed and why
- Prepare to rollback affected roles if needed

### Post-Deployment

**Verification:**
- [ ] Check exit code (`echo $?` should be 0)
- [ ] Review log files for errors
- [ ] Verify 2-3 roles manually in Kibana
- [ ] Test CSV report generation with real users
- [ ] Review summary statistics

**Documentation:**
- [ ] Archive log files and reports
- [ ] Update change management tickets
- [ ] Document any issues encountered
- [ ] Note any roles that need special attention

**Backup Management:**
- [ ] Verify backup file was created
- [ ] Store backup in secure location
- [ ] Keep backups for at least 30 days
- [ ] Document backup location for team

### Ongoing Maintenance

**Regular Tasks:**
- Run monthly reports to identify new roles
- Review and clean old backups (older than 90 days)
- Monitor log directory disk usage
- Update documentation with lessons learned

**After Major Changes:**
- New cluster deployments: Update ELASTICSEARCH_URL
- API key rotation: Update keys in secure storage
- Role naming convention changes: Update filters
- New CCS connections: Re-run analysis

---

## Troubleshooting

### Connection Issues

**Symptom:** "Failed to connect to Elasticsearch"

**Possible Causes:**
1. Incorrect ELASTICSEARCH_URL in script
2. Network connectivity issues
3. SSL certificate problems
4. Firewall blocking connection

**Solutions:**

```bash
# Test basic connectivity
curl https://your-cluster:9200

# Test with API key
curl -H "Authorization: ApiKey YOUR_KEY" https://your-cluster:9200

# If SSL issues, temporarily disable verification (debugging only)
# Edit script: session.verify = False
```

### Authentication Issues

**Symptom:** "Unauthorized" or "Permission denied"

**Possible Causes:**
1. Invalid API key
2. API key doesn't have required permissions
3. API key has been revoked
4. Wrong cluster URL

**Solutions:**

```bash
# Verify API key works
curl -H "Authorization: ApiKey YOUR_KEY" \
     https://cluster:9200/_security/_authenticate

# Check API key permissions
curl -H "Authorization: ApiKey YOUR_KEY" \
     https://cluster:9200/_security/user/_has_privileges \
     -H "Content-Type: application/json" \
     -d '{"cluster":["manage_security"]}'
```

### Role Not Found Issues

**Symptom:** "Role not found" during update or rollback

**For Updates:**
- Role name has a typo
- Role doesn't exist in this cluster
- Connected to wrong environment

**For Rollback:**
- Role wasn't in the backup file (created after backup)
- Wrong backup file selected
- Role name has a typo

**Solutions:**

```bash
# List all roles in cluster
curl -H "Authorization: ApiKey YOUR_KEY" \
     https://cluster:9200/_security/role | jq 'keys'

# List roles in backup file
python -c "import json; print('\n'.join(json.load(open('backup.json')).keys()))"
```

### Duplicate Pattern Issues

**Symptom:** Script says role updated but patterns look wrong

**Possible Causes:**
1. Patterns already existed in different format
2. Comma-separated patterns not handled correctly
3. Whitespace or ordering differences

**Solutions:**

```bash
# Run with debug logging
python es_role_auto_update.py \
  --api-key KEY \
  --roles ProblematicRole \
  --log-level DEBUG

# Check what patterns exist currently
curl -H "Authorization: ApiKey YOUR_KEY" \
     https://cluster:9200/_security/role/RoleName | jq '.RoleName.indices[].names'

# Force update if needed
python es_role_auto_update.py \
  --api-key KEY \
  --roles ProblematicRole \
  --force
```

### CSV Reports Still Not Working

**Symptom:** Role updated successfully but users still can't generate CSV

**Checklist:**
1. Is user actually assigned this role?
2. Do the indices actually exist?
3. Did user log out and back in?
4. Are the local patterns correct?
5. Is the user's role cache stale?

**Solutions:**

```bash
# Verify role in Kibana
# Stack Management → Security → Roles → [RoleName]

# Check user's roles
curl -H "Authorization: ApiKey YOUR_KEY" \
     https://cluster:9200/_security/user/username

# Have user clear Kibana cache
# Settings → Advanced Settings → Clear cache
```

### Performance Issues

**Symptom:** Script takes very long to run

**Common Causes:**
1. Too many roles (hundreds)
2. Network latency
3. Large role definitions
4. Cluster under heavy load

**Solutions:**

```bash
# Update in batches
python es_role_auto_update.py --api-key KEY --roles $(cat batch1.txt)
python es_role_auto_update.py --api-key KEY --roles $(cat batch2.txt)

# Use continue-on-error for large updates
python es_role_auto_update.py \
  --api-key KEY \
  --continue-on-error

# Run during off-peak hours
# Schedule via cron for overnight execution
```

### Common Error Messages

| Error | Meaning | Solution |
|-------|---------|----------|
| `Connection refused` | Can't reach ES cluster | Check URL and network |
| `Invalid API key` | Authentication failed | Verify API key is correct |
| `Permission denied` | Insufficient privileges | Check API key has manage_security |
| `Role is reserved` | Can't modify system role | This is normal, skip it |
| `Backup file not found` | Missing backup | Check path, use absolute path |
| `JSON decode error` | Corrupted backup file | Use different backup |

---

## Security Considerations

### API Key Management

**Best Practices:**
- **Never commit API keys to git**
- Store keys in environment variables or secret management systems
- Use separate keys for each environment (prod, qa, dev)
- Rotate keys regularly (quarterly recommended)
- Document key ownership and purpose
- Revoke keys immediately if compromised

**Recommended Storage:**

```bash
# Environment variable (for local use)
export ES_PROD_API_KEY="your-key-here"
python es_role_auto_update.py --api-key "$ES_PROD_API_KEY"

# HashiCorp Vault
vault kv get -field=api_key secret/elasticsearch/prod

# AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id elasticsearch/prod-api-key

# Azure Key Vault
az keyvault secret show --vault-name myvault --name es-prod-key
```

### Access Control

**Who Should Have Access:**
- Elasticsearch administrators
- Platform engineering team
- Senior DevOps engineers
- Security team (for audits)

**Access Restrictions:**
- Limit script execution to jump boxes or bastion hosts
- Require MFA for production access
- Log all script executions
- Regular access reviews

### Audit & Compliance

**Logging Requirements:**
- Keep log files for minimum 90 days
- Store in centralized logging system (Splunk, ELK, etc.)
- Include in compliance audit scope
- Tag with appropriate security labels

**Change Management:**
- All production updates require change ticket
- Document reason for update
- Record who executed and when
- Keep backup files as evidence

### Network Security

**Recommendations:**
- Use TLS/SSL for all connections (don't disable verify_ssl in prod)
- Restrict script execution to trusted networks
- Use VPN or bastion hosts for remote execution
- Consider IP whitelisting on ES cluster

---

## Support & Contact

### Getting Help

**Documentation:**
- README.md - Comprehensive user guide
- QUICK_START.md - Quick reference examples
- ROLLBACK_GUIDE.md - Rollback procedures
- This KB article

**Internal Resources:**
- Wiki: https://wiki.company.com/elasticsearch/role-manager
- Confluence: https://confluence.company.com/spaces/PLAT/role-automation
- GitHub: https://github.com/your-org/elasticsearch-role-manager

### Reporting Issues

**Before Reporting:**
1. Check this troubleshooting section
2. Review log files for specific errors
3. Verify configuration is correct
4. Test in non-production first

**What to Include:**
- Script version/commit hash
- Full error message and stack trace
- Relevant log files (sanitized)
- Environment (prod/qa/dev)
- Elasticsearch version
- What you were trying to do
- What actually happened

**Where to Report:**
- Jira Project: ELASTICSEARCH
- Issue Type: Bug or Support
- Priority: Based on impact
- Component: Role Management

### Contact Information

**Primary Support:**
- Team: Platform Engineering - Elasticsearch
- Email: elasticsearch-team@company.com
- Slack: #elasticsearch-support
- On-call: PagerDuty escalation

**Escalation Path:**
1. Elasticsearch Team (L1/L2)
2. Senior Platform Engineers (L3)
3. Platform Engineering Manager
4. Director of Infrastructure

### Training & Onboarding

**New Team Members:**
- Schedule pairing session with experienced engineer
- Review this documentation thoroughly
- Test in sandbox environment first
- Shadow a production deployment
- Perform deployment under supervision

**Training Resources:**
- Internal training videos: Learning Hub → Elasticsearch
- Brown bag sessions: First Friday monthly
- Workshop materials: Confluence → Platform Training

---

## Appendix

### Glossary

- **CCS**: Cross-Cluster Search - Elasticsearch feature for searching across multiple clusters
- **Remote Index Pattern**: Index pattern with cluster prefix (e.g., `prod:filebeat-*`)
- **Local Index Pattern**: Index pattern without cluster prefix (e.g., `filebeat-*`)
- **API Key**: Authentication credential for Elasticsearch API
- **Role**: Collection of privileges in Elasticsearch
- **Idempotent**: Can be run multiple times with same result

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Nov 2024 | Initial release with pattern handling |
| 1.1 | Nov 2024 | Added comma-separated pattern support |
| 1.2 | Nov 2024 | Added original order preservation |
| 1.3 | Nov 2024 | Added rollback script |

### Related Documentation

- Elasticsearch Security Documentation: https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html
- Cross-Cluster Search Guide: https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-cross-cluster-search.html
- API Key Management: https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html

### Sample Backup File Structure

```json
{
  "ELK-Dev-600-Role": {
    "cluster": [],
    "indices": [
      {
        "names": [
          "prod:filebeat-*",
          "qa:filebeat-*"
        ],
        "privileges": [
          "read",
          "view_index_metadata"
        ],
        "allow_restricted_indices": false
      }
    ],
    "applications": [],
    "run_as": [],
    "metadata": {},
    "transient_metadata": {
      "enabled": true
    }
  }
}
```

### Sample Log File Excerpt

```
2024-11-29 14:30:22 - INFO - Elasticsearch Role Auto-Updater
2024-11-29 14:30:22 - INFO - Testing connection to Elasticsearch...
2024-11-29 14:30:23 - INFO - Successfully connected to Elasticsearch: 8.11.0
2024-11-29 14:30:23 - INFO - Retrieving all roles...
2024-11-29 14:30:24 - INFO - Retrieved 150 roles from Elasticsearch
2024-11-29 14:30:24 - INFO - Backing up roles...
2024-11-29 14:30:25 - INFO - Backup saved to: backups/roles_backup_20241129_143022.json
2024-11-29 14:30:25 - INFO - Analyzing roles for required updates...
2024-11-29 14:30:25 - INFO - ✓ ELK-Dev-600-Role: needs 2 patterns
2024-11-29 14:30:25 - INFO - Found 47 roles that need updating
2024-11-29 14:30:25 - INFO - [1/47] Processing role: ELK-Dev-600-Role
2024-11-29 14:30:25 - INFO -   Patterns to add: filebeat-*, metricbeat-*
2024-11-29 14:30:26 - INFO -   ✓ Successfully updated ELK-Dev-600-Role
```

---

**Document Control:**

- **Last Reviewed:** November 2024
- **Next Review:** February 2025
- **Owner:** Platform Engineering Team
- **Approvers:** Infrastructure Manager, Security Team
- **Classification:** Internal Use Only

---

**Feedback:**

Have suggestions for improving this documentation? Contact the Platform Engineering team or submit a pull request to the documentation repository.
