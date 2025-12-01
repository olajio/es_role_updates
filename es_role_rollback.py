#!/usr/bin/env python3
"""
Elasticsearch Role Rollback Script

Restores roles from a backup file created by es_role_auto_update.py

Usage:
    # Restore a single role
    python es_role_rollback.py --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1
    
    # Restore multiple roles
    python es_role_rollback.py --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1 Role2 Role3
    
    # Restore from file
    python es_role_rollback.py --backup backups/roles_backup_20241129.json --api-key KEY --role-file roles.txt
    
    # Dry run (see what would be restored)
    python es_role_rollback.py --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1 --dry-run
"""

import json
import requests
import argparse
import sys
import os
from typing import List, Dict, Set
import urllib3

# Disable SSL warnings if needed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================================
# CONFIGURATION - Update these values for your environment
# ============================================================================
ELASTICSEARCH_URL = "https://localhost:9200"
# ============================================================================


def load_roles_from_file(file_path: str) -> List[str]:
    """Load role names from a text file (one per line)"""
    if not os.path.exists(file_path):
        print(f"ERROR: Role file not found: {file_path}")
        sys.exit(1)
    
    roles = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                roles.append(line)
    
    return roles


def load_backup(backup_file: str) -> Dict:
    """Load roles from backup file"""
    if not os.path.exists(backup_file):
        print(f"ERROR: Backup file not found: {backup_file}")
        sys.exit(1)
    
    try:
        with open(backup_file, 'r') as f:
            roles = json.load(f)
        print(f"✓ Loaded backup file: {backup_file}")
        print(f"  Total roles in backup: {len(roles)}")
        return roles
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in backup file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to load backup file: {e}")
        sys.exit(1)


def validate_roles(role_names: List[str], backup_roles: Dict) -> tuple:
    """Validate that requested roles exist in backup"""
    valid_roles = []
    invalid_roles = []
    
    for role_name in role_names:
        if role_name in backup_roles:
            valid_roles.append(role_name)
        else:
            invalid_roles.append(role_name)
    
    return valid_roles, invalid_roles


def clean_role_definition(role_def: Dict) -> Dict:
    """Remove metadata fields that shouldn't be in the update"""
    return {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}


def restore_role(role_name: str, role_def: Dict, api_key: str, dry_run: bool = False) -> bool:
    """Restore a single role to Elasticsearch"""
    clean_def = clean_role_definition(role_def)
    
    if dry_run:
        print(f"\n[DRY RUN] Would restore role: {role_name}")
        print(f"  Cluster privileges: {role_def.get('cluster', [])}")
        print(f"  Index entries: {len(role_def.get('indices', []))}")
        return True
    
    try:
        response = requests.put(
            f'{ELASTICSEARCH_URL}/_security/role/{role_name}',
            headers={
                'Authorization': f'ApiKey {api_key}',
                'Content-Type': 'application/json'
            },
            json=clean_def,
            verify=False
        )
        
        if response.status_code == 200:
            print(f"✓ Successfully restored: {role_name}")
            return True
        else:
            print(f"✗ Failed to restore {role_name}: HTTP {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error restoring {role_name}: {e}")
        return False


def test_connection(api_key: str) -> bool:
    """Test connection to Elasticsearch"""
    try:
        response = requests.get(
            f'{ELASTICSEARCH_URL}/_security/_authenticate',
            headers={'Authorization': f'ApiKey {api_key}'},
            verify=False,
            timeout=10
        )
        
        if response.status_code == 200:
            auth_info = response.json()
            print(f"✓ Connected to Elasticsearch")
            print(f"  Authenticated as: {auth_info.get('username', 'unknown')}")
            return True
        else:
            print(f"ERROR: Authentication failed: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to connect to {ELASTICSEARCH_URL}")
        print(f"  {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Restore Elasticsearch roles from backup file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Restore a single role
  %(prog)s --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1
  
  # Restore multiple roles
  %(prog)s --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1 Role2
  
  # Restore from file
  %(prog)s --backup backups/roles_backup_20241129.json --api-key KEY --role-file roles.txt
  
  # Dry run first
  %(prog)s --backup backups/roles_backup_20241129.json --api-key KEY --roles Role1 --dry-run
  
  # Restore all roles (use with caution!)
  %(prog)s --backup backups/roles_backup_20241129.json --api-key KEY --all
        """
    )
    
    parser.add_argument(
        '--backup',
        required=True,
        help='Path to backup file (e.g., backups/roles_backup_20241129.json)'
    )
    
    parser.add_argument(
        '--api-key',
        required=True,
        help='Elasticsearch API key with manage_security privilege'
    )
    
    parser.add_argument(
        '--roles',
        nargs='+',
        help='Role names to restore (space-separated)'
    )
    
    parser.add_argument(
        '--role-file',
        help='File containing role names to restore (one per line)'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Restore ALL roles from backup (use with caution!)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be restored without making changes'
    )
    
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue restoring other roles if one fails'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not any([args.roles, args.role_file, args.all]):
        parser.error('Must specify --roles, --role-file, or --all')
    
    if args.all and (args.roles or args.role_file):
        parser.error('Cannot use --all with --roles or --role-file')
    
    # Print header
    print("=" * 70)
    print("ELASTICSEARCH ROLE ROLLBACK")
    print("=" * 70)
    print(f"\nElasticsearch URL: {ELASTICSEARCH_URL}")
    print(f"Backup file: {args.backup}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
    
    # Test connection
    print("\nTesting connection...")
    if not test_connection(args.api_key):
        sys.exit(1)
    
    # Load backup
    print("\nLoading backup file...")
    backup_roles = load_backup(args.backup)
    
    # Determine which roles to restore
    if args.all:
        role_names = list(backup_roles.keys())
        print(f"\n⚠️  WARNING: Restoring ALL {len(role_names)} roles from backup!")
        if not args.dry_run:
            response = input("Are you sure? Type 'yes' to continue: ")
            if response.lower() != 'yes':
                print("Cancelled.")
                sys.exit(0)
    else:
        # Get role names from arguments or file
        role_names = []
        if args.roles:
            role_names.extend(args.roles)
        if args.role_file:
            role_names.extend(load_roles_from_file(args.role_file))
        
        # Remove duplicates while preserving order
        role_names = list(dict.fromkeys(role_names))
    
    # Validate roles exist in backup
    print(f"\nValidating {len(role_names)} role(s)...")
    valid_roles, invalid_roles = validate_roles(role_names, backup_roles)
    
    if invalid_roles:
        print(f"\n⚠️  WARNING: {len(invalid_roles)} role(s) not found in backup:")
        for role in invalid_roles:
            print(f"  ✗ {role}")
    
    if not valid_roles:
        print("\nERROR: No valid roles to restore")
        sys.exit(1)
    
    print(f"\nRoles to restore: {len(valid_roles)}")
    for role in valid_roles:
        print(f"  • {role}")
    
    # Confirm if not dry run
    if not args.dry_run and not args.all:
        print()
        response = input("Proceed with restore? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            sys.exit(0)
    
    # Restore roles
    print("\n" + "=" * 70)
    print("RESTORING ROLES")
    print("=" * 70)
    
    success_count = 0
    fail_count = 0
    
    for i, role_name in enumerate(valid_roles, 1):
        print(f"\n[{i}/{len(valid_roles)}] Restoring: {role_name}")
        
        role_def = backup_roles[role_name]
        success = restore_role(role_name, role_def, args.api_key, args.dry_run)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
            if not args.continue_on_error:
                print("\nERROR: Stopping due to failure (use --continue-on-error to continue)")
                break
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if args.dry_run:
        print(f"Mode: DRY RUN")
    else:
        print(f"Mode: LIVE RESTORE")
    
    print(f"Total roles processed: {success_count + fail_count}")
    print(f"Successfully restored: {success_count}")
    print(f"Failed to restore: {fail_count}")
    
    if invalid_roles:
        print(f"Not found in backup: {len(invalid_roles)}")
    
    if args.dry_run:
        print("\n⚠️  This was a dry run - no actual changes were made")
        print("Remove --dry-run to perform the restore")
    
    # Exit code
    if fail_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
