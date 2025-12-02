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

#### 3. rollback_es_role_update.py.py

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
curl -O https://internal-repo/rollback_es_role_update.py.py
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
rollback_es_role_update.py.py
example_roles_to_update.txt
README.md
QUICK_START.md
ROLLBACK_GUIDE.md
```

## Configuration

### Directory Structure

The scripts will automatically create these directories:

```
project_root/
├── es_role_auto_update.py
├── es_role_manager_utils.py
├── rollback_es_role_update.py.py
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

### Usage Scenarios

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

## Usage - Rollback Role Update

### Quick Reference

```bash
# Restore a single role
python rollback_es_role_update.py.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --roles Role1

# Restore multiple roles
python rollback_es_role_update.py.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --roles Role1 Role2 Role3

# Restore from file
python rollback_es_role_update.py.py \
  --backup backups/roles_backup_20241129.json \
  --api-key KEY \
  --role-file roles.txt

# Dry run first
python rollback_es_role_update.py.py \
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
   python rollback_es_role_update.py.py \
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
   python rollback_es_role_update.py.py \
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
   python rollback_es_role_update.py.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --role-file roles_to_restore.txt \
     --continue-on-error
   ```

#### Scenario 3: Restore All Roles

**Problem:** Major issue requires full rollback

** WARNING:** This restores ALL roles from the backup. Use with extreme caution.

**Steps:**

1. **Verify you have the correct backup**
   ```bash
   # List all roles in the backup
   python -c "import json; print('\n'.join(json.load(open('backups/roles_backup_20241129.json')).keys()))" | head -20
   ```

2. **Dry run first (MANDATORY)**
   ```bash
   python rollback_es_role_update.py.py \
     --backup backups/roles_backup_20241129_140530.json \
     --api-key $API_KEY \
     --all \
     --dry-run
   ```

3. **Perform the restore**
   ```bash
   python rollback_es_role_update.py.py \
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

### Getting Help

**Documentation:**
- README.md - Comprehensive user guide
- QUICK_START.md - Quick reference examples
- ROLLBACK_GUIDE.md - Rollback procedures
