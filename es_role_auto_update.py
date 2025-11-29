#!/usr/bin/env python3
"""
Elasticsearch Role Auto-Updater
Automatically updates all roles (or specific roles) with remote index patterns to include local patterns

Usage:
    python es_role_auto_update.py --api-key <key> [options]
    python es_role_auto_update.py --api-key <key> --roles role1 role2 [options]
    python es_role_auto_update.py --api-key <key> --role-file roles.txt [options]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List, Optional
import logging

from es_role_manager_utils import (
    ElasticsearchRoleManager,
    setup_logging,
    generate_update_report
)

# ============================================================================
# CONFIGURATION - Update these values for your environment
# ============================================================================

# Elasticsearch cluster endpoint
ELASTICSEARCH_URL = "https://localhost:9200"

# You can also configure these default paths if desired
DEFAULT_BACKUP_DIR = "./backups"
DEFAULT_LOG_DIR = "./logs"

# ============================================================================


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Automatically update Elasticsearch roles with remote index patterns',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed (all roles)
  python es_role_auto_update.py --api-key <key> --dry-run
  
  # Actually update all roles
  python es_role_auto_update.py --api-key <key>
  
  # Update specific roles only
  python es_role_auto_update.py --api-key <key> --roles role1 role2 --dry-run
  
  # Update roles from a file
  python es_role_auto_update.py --api-key <key> --role-file roles.txt
  
  # Update with custom backup directory
  python es_role_auto_update.py --api-key <key> --backup-dir /path/to/backups
  
Note: The Elasticsearch URL is configured in the script (currently: """ + ELASTICSEARCH_URL + """)
        """
    )
    
    parser.add_argument(
        '--api-key',
        required=True,
        help='API key for authentication'
    )
    
    # Role selection - mutually exclusive with all-roles mode
    role_group = parser.add_mutually_exclusive_group()
    role_group.add_argument(
        '--roles',
        nargs='+',
        help='Space-separated list of specific role names to update'
    )
    role_group.add_argument(
        '--role-file',
        type=Path,
        help='File containing role names (one per line) to update'
    )
    
    parser.add_argument(
        '--backup-dir',
        type=Path,
        default=Path(DEFAULT_BACKUP_DIR),
        help=f'Directory to store role backups (default: {DEFAULT_BACKUP_DIR})'
    )
    
    parser.add_argument(
        '--log-dir',
        type=Path,
        default=Path(DEFAULT_LOG_DIR),
        help=f'Directory to store log files (default: {DEFAULT_LOG_DIR})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making actual changes'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup creation (not recommended)'
    )
    
    parser.add_argument(
        '--verify-ssl',
        action='store_true',
        default=False,
        help='Verify SSL certificates (default: False)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--report-only',
        action='store_true',
        help='Only generate a report of roles that need updating, without updating'
    )
    
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue updating other roles if one fails'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force update even if role appears not to need updating'
    )
    
    return parser.parse_args()


def load_roles_from_file(file_path: Path) -> List[str]:
    """
    Load role names from a file
    
    Args:
        file_path: Path to file containing role names
        
    Returns:
        List of role names
    """
    logger = logging.getLogger(__name__)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Role file not found: {file_path}")
    
    roles = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                roles.append(line)
    
    logger.info(f"Loaded {len(roles)} role names from {file_path}")
    return roles


def validate_roles(
    manager: ElasticsearchRoleManager,
    role_names: List[str],
    all_roles: Dict
) -> tuple[List[str], List[str]]:
    """
    Validate that role names exist
    
    Args:
        manager: ElasticsearchRoleManager instance
        role_names: List of role names to validate
        all_roles: Dictionary of all roles from Elasticsearch
        
    Returns:
        Tuple of (valid_roles, invalid_roles)
    """
    logger = logging.getLogger(__name__)
    
    valid_roles = []
    invalid_roles = []
    
    for role_name in role_names:
        if role_name in all_roles:
            valid_roles.append(role_name)
        else:
            logger.warning(f"Role not found: {role_name}")
            invalid_roles.append(role_name)
    
    return valid_roles, invalid_roles


def analyze_roles(
    manager: ElasticsearchRoleManager, 
    all_roles: Dict,
    specific_roles: Optional[List[str]] = None,
    force: bool = False
) -> Dict[str, Set[str]]:
    """
    Analyze roles to find which ones need updating
    
    Args:
        manager: ElasticsearchRoleManager instance
        all_roles: Dictionary of all roles
        specific_roles: Optional list of specific roles to analyze. If None, analyzes all roles
        force: If True, include roles even if they don't need updating
        
    Returns:
        Dictionary mapping role names to patterns that need to be added
    """
    logger = logging.getLogger(__name__)
    
    # Determine which roles to analyze
    if specific_roles:
        roles_to_analyze = {k: v for k, v in all_roles.items() if k in specific_roles}
        logger.info(f"Analyzing {len(roles_to_analyze)} specified roles...")
    else:
        roles_to_analyze = all_roles
        logger.info(f"Analyzing all {len(roles_to_analyze)} roles...")
    
    roles_to_update = {}
    
    for role_name, role_def in roles_to_analyze.items():
        # Check if reserved
        if role_def.get('metadata', {}).get('_reserved'):
            logger.debug(f"Skipping reserved role: {role_name}")
            continue
        
        needs_update, patterns_to_add = manager.needs_update(role_name, role_def)
        
        if needs_update or (force and manager.extract_remote_patterns(role_def)):
            if not patterns_to_add and force:
                # Force mode: add all remote patterns even if they exist locally
                remote_patterns = manager.extract_remote_patterns(role_def)
                patterns_to_add = manager.get_base_patterns(remote_patterns)
            
            if patterns_to_add:
                roles_to_update[role_name] = patterns_to_add
                logger.info(f"✓ {role_name}: needs {len(patterns_to_add)} patterns")
            else:
                logger.debug(f"○ {role_name}: no update needed")
        else:
            logger.debug(f"○ {role_name}: no update needed")
    
    return roles_to_update


def update_roles(
    manager: ElasticsearchRoleManager,
    all_roles: Dict,
    roles_to_update: Dict[str, Set[str]],
    dry_run: bool = False,
    continue_on_error: bool = False
) -> Dict[str, bool]:
    """
    Update roles with missing local patterns
    
    Args:
        manager: ElasticsearchRoleManager instance
        all_roles: Dictionary of all roles
        roles_to_update: Dictionary of roles that need updating
        dry_run: If True, only show what would be changed
        continue_on_error: If True, continue even if a role fails
        
    Returns:
        Dictionary mapping role names to update success status
    """
    logger = logging.getLogger(__name__)
    results = {}
    
    total_roles = len(roles_to_update)
    
    for idx, (role_name, patterns_to_add) in enumerate(roles_to_update.items(), 1):
        logger.info(f"\n[{idx}/{total_roles}] Processing role: {role_name}")
        logger.info(f"  Patterns to add: {', '.join(sorted(patterns_to_add))}")
        
        if dry_run:
            logger.info(f"  [DRY RUN] Would add {len(patterns_to_add)} patterns")
            results[role_name] = True
            continue
        
        try:
            # Get current role definition
            role_def = all_roles[role_name]
            
            # Add local patterns
            updated_role = manager.add_local_patterns_to_role(role_def, patterns_to_add)
            
            # Update in Elasticsearch
            success = manager.update_role(role_name, updated_role)
            results[role_name] = success
            
            if success:
                logger.info(f"  ✓ Successfully updated {role_name}")
            else:
                logger.error(f"  ✗ Failed to update {role_name}")
                if not continue_on_error:
                    logger.error("  Stopping due to error (use --continue-on-error to continue)")
                    break
                
        except Exception as e:
            logger.error(f"  ✗ Error updating {role_name}: {e}")
            results[role_name] = False
            if not continue_on_error:
                logger.error("  Stopping due to error (use --continue-on-error to continue)")
                break
    
    return results


def verify_updates(
    manager: ElasticsearchRoleManager,
    roles_to_update: Dict[str, Set[str]]
) -> Dict[str, bool]:
    """
    Verify that updates were applied correctly
    
    Args:
        manager: ElasticsearchRoleManager instance
        roles_to_update: Dictionary of roles that were updated
        
    Returns:
        Dictionary mapping role names to verification status
    """
    logger = logging.getLogger(__name__)
    logger.info("\nVerifying updates...")
    
    verification_results = {}
    
    for role_name, expected_patterns in roles_to_update.items():
        try:
            # Fetch updated role
            updated_role = manager.get_role(role_name)
            
            if not updated_role:
                logger.error(f"  ✗ {role_name}: Role not found after update")
                verification_results[role_name] = False
                continue
            
            # Check if patterns were added
            local_patterns = manager.get_existing_local_patterns(updated_role)
            missing_patterns = expected_patterns - local_patterns
            
            if missing_patterns:
                logger.error(f"  ✗ {role_name}: Missing patterns: {missing_patterns}")
                verification_results[role_name] = False
            else:
                logger.info(f"  ✓ {role_name}: All patterns verified")
                verification_results[role_name] = True
                
        except Exception as e:
            logger.error(f"  ✗ {role_name}: Verification error: {e}")
            verification_results[role_name] = False
    
    return verification_results


def print_summary(
    roles_to_update: Dict[str, Set[str]],
    update_results: Dict[str, bool],
    verification_results: Dict[str, bool] = None,
    dry_run: bool = False,
    invalid_roles: List[str] = None,
    mode: str = "all"
):
    """
    Print summary of operations
    
    Args:
        roles_to_update: Dictionary mapping role names to patterns
        update_results: Dictionary mapping role names to update success
        verification_results: Optional verification results
        dry_run: Whether this was a dry run
        invalid_roles: Optional list of invalid role names
        mode: Mode of operation ("all" or "selective")
    """
    logger = logging.getLogger(__name__)
    
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    if dry_run:
        logger.info(f"Mode: DRY RUN (no changes made)")
    
    if mode == "selective":
        logger.info(f"Update mode: SELECTIVE (specific roles only)")
    else:
        logger.info(f"Update mode: ALL ROLES")
    
    logger.info(f"Total roles analyzed: {len(roles_to_update)}")
    
    if invalid_roles:
        logger.warning(f"Invalid roles skipped: {len(invalid_roles)}")
        for role in invalid_roles:
            logger.warning(f"  - {role}")
    
    if not dry_run:
        successful = sum(1 for success in update_results.values() if success)
        failed = len(update_results) - successful
        
        logger.info(f"Successfully updated: {successful}")
        logger.info(f"Failed to update: {failed}")
        
        if verification_results:
            verified = sum(1 for v in verification_results.values() if v)
            logger.info(f"Verified successfully: {verified}/{len(verification_results)}")
    
    # Show roles that were/would be updated
    logger.info("\nRoles with updates:")
    for role_name, patterns in sorted(roles_to_update.items()):
        status = ""
        if not dry_run and role_name in update_results:
            status = " ✓" if update_results[role_name] else " ✗"
        logger.info(f"  {role_name}{status}: {len(patterns)} patterns")
    
    logger.info("="*70)


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Setup logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = args.log_dir / f'role_auto_update_{timestamp}.log'
    logger = setup_logging(log_file, args.log_level)
    
    logger.info("="*70)
    logger.info("Elasticsearch Role Auto-Updater")
    logger.info("="*70)
    logger.info(f"Elasticsearch URL: {ELASTICSEARCH_URL}")
    
    # Determine update mode
    if args.roles or args.role_file:
        update_mode = "selective"
        logger.info(f"Update mode: SELECTIVE (specific roles only)")
    else:
        update_mode = "all"
        logger.info(f"Update mode: ALL ROLES")
    
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Backup enabled: {not args.no_backup}")
    logger.info(f"Continue on error: {args.continue_on_error}")
    logger.info(f"Force update: {args.force}")
    logger.info(f"Log file: {log_file}")
    logger.info("")
    
    try:
        # Get role selection if specified
        selected_roles = None
        invalid_roles = []
        
        if args.roles:
            selected_roles = args.roles
            logger.info(f"Roles specified via command line: {len(selected_roles)}")
        elif args.role_file:
            selected_roles = load_roles_from_file(args.role_file)
            logger.info(f"Roles loaded from file: {args.role_file}")
        
        # Initialize manager
        manager = ElasticsearchRoleManager(
            ELASTICSEARCH_URL,
            args.api_key,
            args.verify_ssl
        )
        
        # Test connection
        logger.info("Testing connection to Elasticsearch...")
        if not manager.test_connection():
            logger.error("Failed to connect to Elasticsearch. Exiting.")
            return 1
        
        # Get all roles
        logger.info("\nRetrieving all roles...")
        all_roles = manager.get_all_roles()
        
        # Validate selected roles if specified
        if selected_roles:
            logger.info("\nValidating role names...")
            valid_roles, invalid_roles = validate_roles(manager, selected_roles, all_roles)
            
            if not valid_roles:
                logger.error("No valid roles found. Exiting.")
                return 1
            
            if invalid_roles:
                logger.warning(f"Found {len(invalid_roles)} invalid role names:")
                for role in invalid_roles:
                    logger.warning(f"  - {role}")
            
            selected_roles = valid_roles
        
        # Backup roles (unless --no-backup is specified)
        if not args.no_backup:
            logger.info("\nBacking up roles...")
            if selected_roles:
                # Backup only selected roles
                roles_to_backup = {k: v for k, v in all_roles.items() if k in selected_roles}
                logger.info(f"Backing up {len(roles_to_backup)} selected roles...")
            else:
                # Backup all roles
                roles_to_backup = all_roles
            
            backup_file = manager.backup_roles(roles_to_backup, args.backup_dir)
            logger.info(f"Backup saved to: {backup_file}")
        
        # Analyze roles
        logger.info("\nAnalyzing roles for required updates...")
        roles_to_update = analyze_roles(
            manager, 
            all_roles, 
            specific_roles=selected_roles,
            force=args.force
        )
        
        if not roles_to_update:
            logger.info("\n✓ No roles need updating. All roles are up to date.")
            print_summary({}, {}, dry_run=args.dry_run, mode=update_mode)
            return 0
        
        logger.info(f"\nFound {len(roles_to_update)} roles that need updating")
        
        # Generate report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        report = generate_update_report(roles_to_update, report_file)
        logger.info(f"Update report saved to: {report_file}")
        
        # If report-only mode, exit here
        if args.report_only:
            logger.info("\nReport-only mode: exiting without making changes")
            print_summary(
                roles_to_update, 
                {}, 
                dry_run=True, 
                invalid_roles=invalid_roles,
                mode=update_mode
            )
            return 0
        
        # Update roles
        logger.info("\n" + "="*70)
        logger.info("UPDATING ROLES")
        logger.info("="*70)
        
        update_results = update_roles(
            manager,
            all_roles,
            roles_to_update,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error
        )
        
        # Verify updates (unless dry run)
        verification_results = None
        if not args.dry_run:
            verification_results = verify_updates(manager, roles_to_update)
        
        # Print summary
        print_summary(
            roles_to_update,
            update_results,
            verification_results,
            args.dry_run,
            invalid_roles,
            mode=update_mode
        )
        
        # Return appropriate exit code
        if args.dry_run:
            return 0
        
        all_successful = all(update_results.values())
        if verification_results:
            all_verified = all(verification_results.values())
            return 0 if (all_successful and all_verified) else 1
        
        return 0 if all_successful else 1
        
    except KeyboardInterrupt:
        logger.warning("\nOperation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
