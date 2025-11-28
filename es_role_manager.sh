#!/bin/bash
#
# Elasticsearch Role Manager Wrapper Script
# Simplifies running the role update scripts with common configurations
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default configuration
ES_URL="${ES_URL:-}"
ES_API_KEY="${ES_API_KEY:-}"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/backups}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
usage() {
    cat << EOF
Elasticsearch Role Manager Wrapper

Usage: $0 [OPTIONS] COMMAND

Commands:
  report          Generate a report of roles that need updating
  auto-dry        Run auto-update in dry-run mode
  auto-update     Run auto-update (actually update roles)
  select-dry      Run selective update in dry-run mode (requires --roles or --role-file)
  select-update   Run selective update (requires --roles or --role-file)
  verify          Test connection to Elasticsearch
  restore         Restore role from backup (requires --backup-file and --role-name)

Options:
  --es-url URL           Elasticsearch URL (or set ES_URL env var)
  --api-key KEY          API key (or set ES_API_KEY env var)
  --roles ROLE1 ROLE2    Space-separated list of role names (for select commands)
  --role-file FILE       File containing role names (for select commands)
  --backup-file FILE     Backup file to restore from (for restore command)
  --role-name NAME       Role name to restore (for restore command)
  --continue-on-error    Continue updating even if a role fails
  --log-level LEVEL      Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  --help                 Show this help message

Environment Variables:
  ES_URL          Elasticsearch URL
  ES_API_KEY      Elasticsearch API key
  BACKUP_DIR      Backup directory (default: ./backups)
  LOG_DIR         Log directory (default: ./logs)

Examples:
  # Set credentials via environment
  export ES_URL="https://localhost:9200"
  export ES_API_KEY="your-api-key"
  
  # Generate report
  $0 report
  
  # Dry run auto-update
  $0 auto-dry
  
  # Actually update all roles
  $0 auto-update
  
  # Update specific roles
  $0 --roles role1 role2 select-update
  
  # Update from file
  $0 --role-file roles.txt select-dry
  
  # Restore a role
  $0 --backup-file backups/roles_backup_20241128_143022.json --role-name ELK-Dev-600-Role restore

EOF
    exit 1
}

# Function to check requirements
check_requirements() {
    if [ -z "$ES_URL" ]; then
        print_error "Elasticsearch URL not set. Use --es-url or set ES_URL environment variable"
        exit 1
    fi
    
    if [ -z "$ES_API_KEY" ]; then
        print_error "API key not set. Use --api-key or set ES_API_KEY environment variable"
        exit 1
    fi
    
    if ! python3 -c "import requests" 2>/dev/null; then
        print_error "Python 'requests' library not found. Install with: pip install requests"
        exit 1
    fi
}

# Function to test connection
test_connection() {
    print_info "Testing connection to Elasticsearch..."
    
    if curl -sf -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/" > /dev/null; then
        print_success "Connection successful!"
        return 0
    else
        print_error "Connection failed!"
        return 1
    fi
}

# Function to run auto-update report
run_report() {
    print_info "Generating role update report..."
    
    python3 "$SCRIPT_DIR/es_role_auto_update.py" \
        --es-url "$ES_URL" \
        --api-key "$ES_API_KEY" \
        --backup-dir "$BACKUP_DIR" \
        --log-dir "$LOG_DIR" \
        --log-level "${LOG_LEVEL:-INFO}" \
        --report-only
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "Report generated successfully!"
        print_info "Check logs directory for report: $LOG_DIR"
    else
        print_error "Report generation failed with exit code: $exit_code"
    fi
    
    return $exit_code
}

# Function to run auto-update
run_auto_update() {
    local dry_run=$1
    
    if [ "$dry_run" = "true" ]; then
        print_info "Running auto-update in DRY RUN mode..."
        extra_args="--dry-run"
    else
        print_warning "Running auto-update - this will modify roles!"
        extra_args=""
    fi
    
    python3 "$SCRIPT_DIR/es_role_auto_update.py" \
        --es-url "$ES_URL" \
        --api-key "$ES_API_KEY" \
        --backup-dir "$BACKUP_DIR" \
        --log-dir "$LOG_DIR" \
        --log-level "${LOG_LEVEL:-INFO}" \
        $extra_args
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "Auto-update completed successfully!"
    else
        print_error "Auto-update failed with exit code: $exit_code"
    fi
    
    return $exit_code
}

# Function to run selective update
run_selective_update() {
    local dry_run=$1
    
    if [ -z "${ROLES:-}" ] && [ -z "${ROLE_FILE:-}" ]; then
        print_error "Must specify either --roles or --role-file"
        exit 1
    fi
    
    if [ "$dry_run" = "true" ]; then
        print_info "Running selective update in DRY RUN mode..."
        extra_args="--dry-run"
    else
        print_warning "Running selective update - this will modify roles!"
        extra_args=""
    fi
    
    local role_args=""
    if [ -n "${ROLES:-}" ]; then
        role_args="--roles $ROLES"
    elif [ -n "${ROLE_FILE:-}" ]; then
        role_args="--role-file $ROLE_FILE"
    fi
    
    if [ -n "${CONTINUE_ON_ERROR:-}" ]; then
        extra_args="$extra_args --continue-on-error"
    fi
    
    python3 "$SCRIPT_DIR/es_role_selective_update.py" \
        --es-url "$ES_URL" \
        --api-key "$ES_API_KEY" \
        --backup-dir "$BACKUP_DIR" \
        --log-dir "$LOG_DIR" \
        --log-level "${LOG_LEVEL:-INFO}" \
        $role_args \
        $extra_args
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "Selective update completed successfully!"
    else
        print_error "Selective update failed with exit code: $exit_code"
    fi
    
    return $exit_code
}

# Function to restore a role from backup
restore_role() {
    if [ -z "${BACKUP_FILE:-}" ]; then
        print_error "Must specify --backup-file"
        exit 1
    fi
    
    if [ -z "${ROLE_NAME:-}" ]; then
        print_error "Must specify --role-name"
        exit 1
    fi
    
    if [ ! -f "$BACKUP_FILE" ]; then
        print_error "Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    print_info "Restoring role $ROLE_NAME from $BACKUP_FILE..."
    
    python3 << EOF
import json
import requests
import sys

try:
    # Load backup
    with open('$BACKUP_FILE', 'r') as f:
        roles = json.load(f)
    
    if '$ROLE_NAME' not in roles:
        print('ERROR: Role $ROLE_NAME not found in backup file')
        sys.exit(1)
    
    role_def = roles['$ROLE_NAME']
    
    # Clean metadata
    clean_def = {k: v for k, v in role_def.items() 
                if k not in ['_reserved', '_deprecated', '_deprecated_reason']}
    
    # Update Elasticsearch
    response = requests.put(
        '$ES_URL/_security/role/$ROLE_NAME',
        headers={
            'Authorization': 'ApiKey $ES_API_KEY',
            'Content-Type': 'application/json'
        },
        json=clean_def,
        verify=False
    )
    
    if response.status_code in [200, 201]:
        print('SUCCESS: Role restored successfully')
        sys.exit(0)
    else:
        print(f'ERROR: Failed to restore role: {response.status_code}')
        print(response.text)
        sys.exit(1)
        
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
EOF
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "Role restored successfully!"
    else
        print_error "Role restoration failed"
    fi
    
    return $exit_code
}

# Parse command line arguments
COMMAND=""
ROLES=""
ROLE_FILE=""
BACKUP_FILE=""
ROLE_NAME=""
CONTINUE_ON_ERROR=""
LOG_LEVEL="INFO"

while [[ $# -gt 0 ]]; do
    case $1 in
        --es-url)
            ES_URL="$2"
            shift 2
            ;;
        --api-key)
            ES_API_KEY="$2"
            shift 2
            ;;
        --roles)
            shift
            ROLES=""
            while [[ $# -gt 0 ]] && [[ ! $1 =~ ^-- ]]; do
                ROLES="$ROLES $1"
                shift
            done
            ;;
        --role-file)
            ROLE_FILE="$2"
            shift 2
            ;;
        --backup-file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        --role-name)
            ROLE_NAME="$2"
            shift 2
            ;;
        --continue-on-error)
            CONTINUE_ON_ERROR="true"
            shift
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        report|auto-dry|auto-update|select-dry|select-update|verify|restore)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Check if command was provided
if [ -z "$COMMAND" ]; then
    print_error "No command specified"
    usage
fi

# Main execution
case "$COMMAND" in
    verify)
        check_requirements
        test_connection
        ;;
    report)
        check_requirements
        run_report
        ;;
    auto-dry)
        check_requirements
        run_auto_update true
        ;;
    auto-update)
        check_requirements
        run_auto_update false
        ;;
    select-dry)
        check_requirements
        run_selective_update true
        ;;
    select-update)
        check_requirements
        run_selective_update false
        ;;
    restore)
        check_requirements
        restore_role
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        usage
        ;;
esac

exit $?
