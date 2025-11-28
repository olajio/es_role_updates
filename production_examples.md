# Production Examples and Best Practices

This document provides real-world examples and best practices for using the Elasticsearch Role Manager in production environments.

## Production Deployment Scenarios

### Scenario 1: Initial Deployment to Production

**Goal**: First-time deployment to production cluster with 150+ roles

**Steps**:

```bash
# 1. Set up credentials securely
export ES_URL="https://prod-es.company.com:9200"
export ES_API_KEY="$(cat /secure/path/to/api-key.txt)"

# 2. Generate initial report
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --report-only \
  --log-dir /var/log/elasticsearch/role-manager

# 3. Review report
REPORT_FILE=$(ls -t /var/log/elasticsearch/role-manager/role_update_report_*.json | head -1)
echo "Reviewing: $REPORT_FILE"
python3 -m json.tool "$REPORT_FILE" | less

# 4. Dry run to verify changes
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --dry-run \
  --backup-dir /backups/elasticsearch/roles \
  --log-dir /var/log/elasticsearch/role-manager

# 5. If dry run looks good, execute
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --backup-dir /backups/elasticsearch/roles \
  --log-dir /var/log/elasticsearch/role-manager

# 6. Verify results
LOG_FILE=$(ls -t /var/log/elasticsearch/role-manager/role_auto_update_*.log | head -1)
echo "Checking results in: $LOG_FILE"
grep -E "(Successfully updated|Failed to update|SUMMARY)" "$LOG_FILE"

# 7. Test with a few users
echo "Test CSV report generation with affected users"
```

**Expected Duration**: 30-60 minutes for 150 roles

**Rollback Plan**: Keep backup file location and use restore procedure

---

### Scenario 2: Weekly Maintenance Update

**Goal**: Regular maintenance to keep roles updated as new indices are added

**Cron Job** (`/etc/cron.d/es-role-update`):

```bash
# Run every Sunday at 2 AM
0 2 * * 0 /usr/bin/python3 /opt/scripts/es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --backup-dir /backups/elasticsearch/roles \
  --log-dir /var/log/elasticsearch/role-manager \
  2>&1 | logger -t es-role-update
```

**Monitoring Script** (`check_role_update.sh`):

```bash
#!/bin/bash
# Check if last role update was successful

LAST_LOG=$(ls -t /var/log/elasticsearch/role-manager/role_auto_update_*.log 2>/dev/null | head -1)

if [ -z "$LAST_LOG" ]; then
    echo "ERROR: No log files found"
    exit 2
fi

# Check if log is recent (within 7 days)
if [ $(find "$LAST_LOG" -mtime -7 | wc -l) -eq 0 ]; then
    echo "WARNING: Last update is more than 7 days old"
    exit 1
fi

# Check for errors
if grep -q "Failed to update" "$LAST_LOG"; then
    echo "ERROR: Some roles failed to update"
    grep "Failed to update" "$LAST_LOG"
    exit 1
fi

echo "OK: Role update completed successfully"
exit 0
```

---

### Scenario 3: Emergency Rollback

**Goal**: Quickly restore roles after an unsuccessful update

**Rollback Script** (`rollback_roles.sh`):

```bash
#!/bin/bash
set -euo pipefail

# Usage: ./rollback_roles.sh <backup_file> [role1 role2 ...]

BACKUP_FILE="$1"
shift

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

ROLES_TO_RESTORE=("$@")

if [ ${#ROLES_TO_RESTORE[@]} -eq 0 ]; then
    echo "Restoring ALL roles from backup..."
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted"
        exit 0
    fi
fi

python3 << EOF
import json
import requests
import sys

# Load backup
with open('$BACKUP_FILE', 'r') as f:
    roles = json.load(f)

roles_to_restore = ${ROLES_TO_RESTORE[@]@Q} if ${#ROLES_TO_RESTORE[@]} > 0 else roles.keys()

failed = []
for role_name in roles_to_restore:
    if role_name not in roles:
        print(f'WARNING: Role {role_name} not in backup')
        continue
    
    role_def = roles[role_name]
    clean_def = {k: v for k, v in role_def.items() 
                if k not in ['_reserved', '_deprecated', '_deprecated_reason']}
    
    try:
        response = requests.put(
            f'$ES_URL/_security/role/{role_name}',
            headers={
                'Authorization': f'ApiKey $ES_API_KEY',
                'Content-Type': 'application/json'
            },
            json=clean_def,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            print(f'✓ Restored: {role_name}')
        else:
            print(f'✗ Failed: {role_name} - {response.status_code}')
            failed.append(role_name)
    except Exception as e:
        print(f'✗ Error restoring {role_name}: {e}')
        failed.append(role_name)

if failed:
    print(f'\nFailed to restore {len(failed)} roles:')
    for role in failed:
        print(f'  - {role}')
    sys.exit(1)
else:
    print('\n✓ All roles restored successfully')
    sys.exit(0)
EOF
```

---

### Scenario 4: Phased Rollout

**Goal**: Update roles in phases to minimize risk

**Phase 1 - Test Roles** (Day 1):

```bash
# Update only test/dev roles first
python es_role_selective_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --roles ELK-Dev-600-Role ELK-Dev-QA-680-Role \
  --backup-dir /backups/elasticsearch/roles/phase1 \
  --log-dir /var/log/elasticsearch/role-manager/phase1
```

**Phase 2 - Internal Users** (Day 3, after monitoring):

```bash
# Update roles used by internal teams
cat > internal_roles.txt << EOF
ELK-AppSupport-GL-290-Role
ELK-TechOps-798-Role
ELK-PlatEng-730-Role
EOF

python es_role_selective_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --role-file internal_roles.txt \
  --backup-dir /backups/elasticsearch/roles/phase2 \
  --log-dir /var/log/elasticsearch/role-manager/phase2
```

**Phase 3 - All Remaining** (Day 7, after validation):

```bash
# Update all remaining roles
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --backup-dir /backups/elasticsearch/roles/phase3 \
  --log-dir /var/log/elasticsearch/role-manager/phase3
```

---

## Integration Examples

### Integration with Slack Notifications

**Wrapper Script with Slack** (`run_with_slack.sh`):

```bash
#!/bin/bash
set -euo pipefail

SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

send_slack() {
    local message="$1"
    local color="$2"
    
    curl -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d '{
            "attachments": [{
                "color": "'"$color"'",
                "text": "'"$message"'",
                "footer": "ES Role Manager",
                "ts": '$(date +%s)'
            }]
        }'
}

# Start notification
send_slack "🔄 Starting Elasticsearch role update..." "#0000FF"

# Run update
if python es_role_auto_update.py \
    --es-url "$ES_URL" \
    --api-key "$ES_API_KEY" \
    --backup-dir /backups/elasticsearch/roles \
    --log-dir /var/log/elasticsearch/role-manager; then
    
    # Success
    LOG_FILE=$(ls -t /var/log/elasticsearch/role-manager/role_auto_update_*.log | head -1)
    SUMMARY=$(grep "SUMMARY" -A 10 "$LOG_FILE" | head -15)
    send_slack "✅ Role update completed successfully\n\`\`\`$SUMMARY\`\`\`" "good"
else
    # Failure
    LOG_FILE=$(ls -t /var/log/elasticsearch/role-manager/role_auto_update_*.log | head -1)
    ERRORS=$(grep ERROR "$LOG_FILE" | tail -10)
    send_slack "❌ Role update failed\n\`\`\`$ERRORS\`\`\`" "danger"
fi
```

---

### Integration with Ansible

**Ansible Playbook** (`update_es_roles.yml`):

```yaml
---
- name: Update Elasticsearch Roles
  hosts: localhost
  vars:
    es_url: "{{ lookup('env', 'ES_URL') }}"
    es_api_key: "{{ lookup('env', 'ES_API_KEY') }}"
    script_dir: "/opt/scripts/es-role-manager"
    backup_dir: "/backups/elasticsearch/roles"
    log_dir: "/var/log/elasticsearch/role-manager"
  
  tasks:
    - name: Ensure directories exist
      file:
        path: "{{ item }}"
        state: directory
        mode: '0755'
      loop:
        - "{{ backup_dir }}"
        - "{{ log_dir }}"
    
    - name: Run role update report
      command: >
        python3 {{ script_dir }}/es_role_auto_update.py
        --es-url {{ es_url }}
        --api-key {{ es_api_key }}
        --backup-dir {{ backup_dir }}
        --log-dir {{ log_dir }}
        --report-only
      register: report_result
      changed_when: false
    
    - name: Display report result
      debug:
        var: report_result.stdout_lines
    
    - name: Prompt for confirmation
      pause:
        prompt: "Review the report. Continue with update? (yes/no)"
      register: confirmation
      when: report_result.rc == 0
    
    - name: Run role update
      command: >
        python3 {{ script_dir }}/es_role_auto_update.py
        --es-url {{ es_url }}
        --api-key {{ es_api_key }}
        --backup-dir {{ backup_dir }}
        --log-dir {{ log_dir }}
      register: update_result
      when: 
        - report_result.rc == 0
        - confirmation.user_input == 'yes'
    
    - name: Display update result
      debug:
        var: update_result.stdout_lines
      when: update_result is defined
    
    - name: Check for errors
      fail:
        msg: "Role update failed"
      when: 
        - update_result is defined
        - update_result.rc != 0
```

---

### Integration with GitOps

**GitHub Actions Workflow** (`.github/workflows/update-es-roles.yml`):

```yaml
name: Update Elasticsearch Roles

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday at 2 AM UTC
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Run in dry-run mode'
        required: false
        default: 'true'

jobs:
  update-roles:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install requests
      
      - name: Run role update
        env:
          ES_URL: ${{ secrets.ES_URL }}
          ES_API_KEY: ${{ secrets.ES_API_KEY }}
        run: |
          if [ "${{ github.event.inputs.dry_run }}" = "true" ]; then
            EXTRA_ARGS="--dry-run"
          else
            EXTRA_ARGS=""
          fi
          
          python es_role_auto_update.py \
            --es-url "$ES_URL" \
            --api-key "$ES_API_KEY" \
            --backup-dir ./backups \
            --log-dir ./logs \
            $EXTRA_ARGS
      
      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: role-update-logs
          path: logs/
      
      - name: Upload backups
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: role-backups
          path: backups/
      
      - name: Notify on failure
        if: failure()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Elasticsearch role update failed'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## Advanced Use Cases

### Use Case 1: Multi-Cluster Update

**Script** (`update_all_clusters.sh`):

```bash
#!/bin/bash
set -euo pipefail

# Define clusters
declare -A CLUSTERS=(
    ["prod"]="https://prod-es.company.com:9200"
    ["qa"]="https://qa-es.company.com:9200"
    ["dev"]="https://dev-es.company.com:9200"
)

declare -A API_KEYS=(
    ["prod"]="$(cat /secure/prod-api-key.txt)"
    ["qa"]="$(cat /secure/qa-api-key.txt)"
    ["dev"]="$(cat /secure/dev-api-key.txt)"
)

# Update each cluster
for cluster in "${!CLUSTERS[@]}"; do
    echo "========================================="
    echo "Updating cluster: $cluster"
    echo "========================================="
    
    python es_role_auto_update.py \
        --es-url "${CLUSTERS[$cluster]}" \
        --api-key "${API_KEYS[$cluster]}" \
        --backup-dir "/backups/elasticsearch/roles/$cluster" \
        --log-dir "/var/log/elasticsearch/role-manager/$cluster"
    
    if [ $? -eq 0 ]; then
        echo "✓ $cluster: Success"
    else
        echo "✗ $cluster: Failed"
    fi
    
    echo ""
done
```

---

### Use Case 2: Compliance Auditing

**Audit Script** (`audit_role_changes.sh`):

```bash
#!/bin/bash
set -euo pipefail

# Generate compliance report
REPORT_DATE=$(date +%Y-%m-%d)
REPORT_FILE="/reports/elasticsearch/role-audit-$REPORT_DATE.md"

cat > "$REPORT_FILE" << EOF
# Elasticsearch Role Change Audit Report
Date: $REPORT_DATE

## Summary
EOF

# Get latest backup and log
LATEST_BACKUP=$(ls -t /backups/elasticsearch/roles/roles_backup_*.json | head -1)
LATEST_LOG=$(ls -t /var/log/elasticsearch/role-manager/role_auto_update_*.log | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "No recent updates found" >> "$REPORT_FILE"
    exit 0
fi

# Extract summary
echo "## Update Summary" >> "$REPORT_FILE"
grep "SUMMARY" -A 20 "$LATEST_LOG" | sed 's/^/    /' >> "$REPORT_FILE"

# List modified roles
echo "" >> "$REPORT_FILE"
echo "## Modified Roles" >> "$REPORT_FILE"
grep "Successfully updated" "$LATEST_LOG" | \
    sed 's/.*Successfully updated /- /' >> "$REPORT_FILE"

# Add backup location
echo "" >> "$REPORT_FILE"
echo "## Backup Location" >> "$REPORT_FILE"
echo "Backup file: \`$LATEST_BACKUP\`" >> "$REPORT_FILE"

# Add verification status
echo "" >> "$REPORT_FILE"
echo "## Verification" >> "$REPORT_FILE"
if grep -q "All patterns verified" "$LATEST_LOG"; then
    echo "✓ All changes verified successfully" >> "$REPORT_FILE"
else
    echo "⚠ Some verifications failed - review log" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "Generated by: $(whoami)@$(hostname)" >> "$REPORT_FILE"
echo "Log file: \`$LATEST_LOG\`" >> "$REPORT_FILE"

# Email report
mail -s "ES Role Audit Report - $REPORT_DATE" \
    compliance@company.com < "$REPORT_FILE"

echo "Audit report generated: $REPORT_FILE"
```

---

## Best Practices Checklist

### Pre-Deployment

- [ ] Test scripts in non-production environment
- [ ] Review all roles that will be updated
- [ ] Verify backup storage has sufficient space
- [ ] Confirm API key has correct permissions
- [ ] Document rollback procedure
- [ ] Schedule during maintenance window
- [ ] Notify stakeholders of planned changes

### During Deployment

- [ ] Run with --dry-run first
- [ ] Review dry-run output carefully
- [ ] Keep terminal session open during update
- [ ] Monitor Elasticsearch cluster health
- [ ] Watch for any error messages
- [ ] Verify backup creation succeeded

### Post-Deployment

- [ ] Review summary output
- [ ] Check log files for errors
- [ ] Verify a sample of updated roles in Kibana
- [ ] Test CSV report generation with affected users
- [ ] Monitor for access issues
- [ ] Keep backups for retention period (30+ days)
- [ ] Document any issues encountered
- [ ] Update runbook if needed

---

## Troubleshooting Guide

### Problem: Script hangs during execution

**Symptoms**: Script stops responding, no output

**Causes**:
- Network connectivity issues
- Elasticsearch cluster health problems
- API key expired

**Solutions**:
```bash
# Check Elasticsearch health
curl -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/_cluster/health"

# Check API key
curl -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/_security/_authenticate"

# Enable debug logging
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --log-level DEBUG
```

---

### Problem: Some roles fail to update

**Symptoms**: Update completes but some roles show errors

**Causes**:
- Reserved roles (automatically skipped)
- Malformed role definitions
- Insufficient permissions

**Solutions**:
```bash
# Check which roles failed
grep "Failed to update" logs/role_auto_update_*.log

# Try updating individually with force
python es_role_selective_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --roles failed-role-name \
  --force \
  --log-level DEBUG

# If still failing, manually inspect the role
curl -H "Authorization: ApiKey $ES_API_KEY" \
  "$ES_URL/_security/role/failed-role-name" | jq .
```

---

### Problem: Verification fails after successful update

**Symptoms**: Update succeeds but verification shows missing patterns

**Causes**:
- Elasticsearch indexing delay
- Cluster state not synchronized
- Cache not refreshed

**Solutions**:
```bash
# Wait and re-verify
sleep 10
python es_role_selective_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --roles role-name

# Manually verify in Kibana
# Navigate to: Stack Management > Security > Roles > [role-name]

# Check via API
curl -H "Authorization: ApiKey $ES_API_KEY" \
  "$ES_URL/_security/role/role-name" | \
  jq '.["role-name"].indices[] | select(.names[] | contains("filebeat"))'
```

---

## Performance Optimization

### For Large Role Sets (200+ roles)

```bash
# Run in parallel for multiple clusters
parallel -j 3 python es_role_auto_update.py \
  --es-url {} \
  --api-key "$ES_API_KEY" \
  ::: \
  https://cluster1:9200 \
  https://cluster2:9200 \
  https://cluster3:9200
```

### For Frequent Updates

```bash
# Use --report-only to identify changes without full scan
python es_role_auto_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --report-only

# Then update only affected roles
python es_role_selective_update.py \
  --es-url "$ES_URL" \
  --api-key "$ES_API_KEY" \
  --role-file roles_from_report.txt
```

---

## Security Recommendations

1. **API Key Management**:
   - Store in secure vault (HashiCorp Vault, AWS Secrets Manager)
   - Rotate every 90 days
   - Use separate keys for prod/non-prod
   - Revoke immediately if compromised

2. **Access Control**:
   - Limit script execution to specific users/groups
   - Use sudo for production updates
   - Log all executions
   - Require approval for production changes

3. **Audit Trail**:
   - Keep all logs for minimum 1 year
   - Store backups in immutable storage
   - Generate compliance reports monthly
   - Review all changes during security audits

---

## Conclusion

These examples demonstrate production-ready patterns for managing Elasticsearch roles at scale. Adapt them to your organization's specific requirements and security policies.

For additional support, refer to:
- Main documentation: `ES_ROLE_MANAGER_README.md`
- Quick start guide: `QUICK_START.md`
- Script help: `python es_role_auto_update.py --help`
