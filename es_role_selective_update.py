#!/usr/bin/env python3
"""
Elasticsearch Role Selective Updater
Update specific Elasticsearch roles with remote index patterns to include local patterns

Usage:
    python es_role_selective_update.py --es-url https://localhost:9200 --api-key <key> --roles role1 role2 [options]
    python es_role_selective_update.py --es-url https://localhost:9200 --api-key <key> --role-file roles.txt [options]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List
import logging

from es_role_manager_utils import (
    ElasticsearchRoleManager,
    setup_logging,
    generate_update_report
)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Selectively update Elasticsearch roles with remote index patterns',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update specific roles (dry run)
  python es_role_selective_update.py --es-url https://localhost:9200 --api-key <key> \\
    --roles ELK-Dev-600-Role ELK-AppSupport-GL-290-Role --dry-run
  
  # Update roles from a file
  python es_role_selective_update.py --es-url https://localhost:9200 --api-key <key> \\
    --role-file roles_to_update.txt
  
  # Update and skip verification
  python es_role_selective_update.py --es-url https://localhost:9200 --api-key <key> \\
    --roles elastic_rw_file --no-verify
        """
    )
    
    parser.add_argument(
        '--es-url',
        required=True,
        help='Elasticsearch URL (e.g., https://localhost:9200)'
    )
    
    parser.add_argument(
        '--api-key',
        required=True,
        help='API key for authentication'
    )
    
    # Role selection - mutually exclusive
    role_group = parser.add_mutually_exclusive_group(required=True)
    role_group.add_argument(
        '--roles',
        nargs='+',
        help='Space-separated list of role names to update'
    )
    role_group.add_argument(
        '--role-file',
        type=Path,
        help='File containing role names (one per line)'
    )
    
    parser.add_argument(
        '--backup-dir',
        type=Path,
        default=Path('./backups'),
        help='Directory to store role backups (default: ./backups)'
    )
    
    parser.add_argument(
        '--log-dir',
        type=Path,
        default=Path('./logs'),
        help='Directory to store log files (default: ./logs)'
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
        '--no-verify',
        action='store_true',
        help='Skip verification after update'
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
        '--continue-on-error',
        action='store_true',
        help='Continue updating other roles if one fails'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Update role even if it appears not to need updating'
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


def analyze_selected_roles(
    manager: ElasticsearchRoleManager,
    role_names: List[str],
    all_roles: Dict,
    force: bool = False
) -> Dict[str, Set[str]]:
    """
    Analyze selected roles to find which ones need updating
    
    Args:
        manager: ElasticsearchRoleManager instance
        role_names: List of role names to analyze
        all_roles: Dictionary of all roles
        force: If True, include roles even if they don't need updating
        
    Returns:
        Dictionary mapping role names to patterns that need to be added
    """
    logger = logging.getLogger(__name__)
    roles_to_update = {}
    
    logger.info(f"\nAnalyzing {len(role_names)} selected roles...")
    
    for role_name in role_names:
        role_def = all_roles[role_name]
        
        # Check if reserved
        if role_def.get('metadata', {}).get('_reserved'):
            logger.warning(f"✗ {role_name}: Reserved role, skipping")
            continue
        
        needs_update, patterns_to_add = manager.needs_update(role_name, role_def)
        
        if needs_update or (force and manager.extract_remote_patterns(role_def)):
            if not patterns_to_add and force:
                # Force mode: add all remote patterns even if they exist locally
                remote_patterns = manager.extract_remote_patterns(role_def)
                patterns_to_add = manager.get_base_patterns(remote_patterns)
            
            roles_to_update[role_name] = patterns_to_add
            logger.info(f"✓ {role_name}: {len(patterns_to_add)} patterns to add")
        else:
            logger.info(f"○ {role_name}: No update needed")
    
    return roles_to_update


def update_role_with_retry(
    manager: ElasticsearchRoleManager,
    role_name: str,
    role_def: Dict,
    patterns_to_add: Set[str],
    max_retries: int = 3
) -> bool:
    """
    Update a role with retry logic
    
    Args:
        manager: ElasticsearchRoleManager instance
        role_name: Name of the role
        role_def: Current role definition
        patterns_to_add: Patterns to add
        max_retries: Maximum number of retry attempts
        
    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    for attempt in range(max_retries):
        try:
            updated_role = manager.add_local_patterns_to_role(role_def, patterns_to_add)
            success = manager.update_role(role_name, updated_role)
            
            if success:
                return True
            
            if attempt < max_retries - 1:
                logger.warning(f"  Retry {attempt + 1}/{max_retries - 1} for {role_name}")
                
        except Exception as e:
            logger.error(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.warning(f"  Retrying...")
    
    return False


def update_selected_roles(
    manager: ElasticsearchRoleManager,
    all_roles: Dict,
    roles_to_update: Dict[str, Set[str]],
    dry_run: bool = False,
    continue_on_error: bool = False
) -> Dict[str, bool]:
    """
    Update selected roles with missing local patterns
    
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
            role_def = all_roles[role_name]
            success = update_role_with_retry(manager, role_name, role_def, patterns_to_add)
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
    roles_to_update: Dict[str, Set[str]],
    update_results: Dict[str, bool]
) -> Dict[str, bool]:
    """
    Verify that updates were applied correctly
    
    Args:
        manager: ElasticsearchRoleManager instance
        roles_to_update: Dictionary of roles that were updated
        update_results: Results of update attempts
        
    Returns:
        Dictionary mapping role names to verification status
    """
    logger = logging.getLogger(__name__)
    logger.info("\n" + "="*70)
    logger.info("VERIFYING UPDATES")
    logger.info("="*70)
    
    verification_results = {}
    
    # Only verify roles that were successfully updated
    roles_to_verify = [role for role, success in update_results.items() if success]
    
    for role_name in roles_to_verify:
        expected_patterns = roles_to_update[role_name]
        
        try:
            updated_role = manager.get_role(role_name)
            
            if not updated_role:
                logger.error(f"✗ {role_name}: Role not found after update")
                verification_results[role_name] = False
                continue
            
            local_patterns = manager.get_existing_local_patterns(updated_role)
            missing_patterns = expected_patterns - local_patterns
            
            if missing_patterns:
                logger.error(f"✗ {role_name}: Missing patterns: {missing_patterns}")
                verification_results[role_name] = False
            else:
                logger.info(f"✓ {role_name}: All patterns verified")
                verification_results[role_name] = True
                
        except Exception as e:
            logger.error(f"✗ {role_name}: Verification error: {e}")
            verification_results[role_name] = False
    
    return verification_results


def print_summary(
    selected_roles: List[str],
    valid_roles: List[str],
    invalid_roles: List[str],
    roles_to_update: Dict[str, Set[str]],
    update_results: Dict[str, bool],
    verification_results: Dict[str, bool] = None,
    dry_run: bool = False
):
    """Print summary of operations"""
    logger = logging.getLogger(__name__)
    
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    if dry_run:
        logger.info(f"Mode: DRY RUN (no changes made)")
    
    logger.info(f"Total roles selected: {len(selected_roles)}")
    logger.info(f"Valid roles: {len(valid_roles)}")
    
    if invalid_roles:
        logger.warning(f"Invalid roles: {len(invalid_roles)}")
        for role in invalid_roles:
            logger.warning(f"  - {role}")
    
    logger.info(f"Roles requiring updates: {len(roles_to_update)}")
    
    if not dry_run and update_results:
        successful = sum(1 for success in update_results.values() if success)
        failed = len(update_results) - successful
        
        logger.info(f"Successfully updated: {successful}")
        logger.info(f"Failed to update: {failed}")
        
        if verification_results:
            verified = sum(1 for v in verification_results.values() if v)
            logger.info(f"Verified successfully: {verified}/{len(verification_results)}")
    
    # Show detailed results
    if roles_to_update:
        logger.info("\nDetailed results:")
        for role_name, patterns in sorted(roles_to_update.items()):
            status = ""
            if not dry_run and role_name in update_results:
                if update_results[role_name]:
                    if verification_results and role_name in verification_results:
                        status = " ✓✓" if verification_results[role_name] else " ✓✗"
                    else:
                        status = " ✓"
                else:
                    status = " ✗"
            logger.info(f"  {role_name}{status}: {len(patterns)} patterns")
    
    logger.info("="*70)


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Setup logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = args.log_dir / f'role_selective_update_{timestamp}.log'
    logger = setup_logging(log_file, args.log_level)
    
    logger.info("="*70)
    logger.info("Elasticsearch Role Selective Updater")
    logger.info("="*70)
    logger.info(f"Elasticsearch URL: {args.es_url}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Backup enabled: {not args.no_backup}")
    logger.info(f"Verification enabled: {not args.no_verify}")
    logger.info(f"Continue on error: {args.continue_on_error}")
    logger.info(f"Log file: {log_file}")
    logger.info("")
    
    try:
        # Get role names
        if args.roles:
            role_names = args.roles
            logger.info(f"Roles specified via command line: {len(role_names)}")
        else:
            role_names = load_roles_from_file(args.role_file)
            logger.info(f"Roles loaded from file: {args.role_file}")
        
        # Initialize manager
        manager = ElasticsearchRoleManager(
            args.es_url,
            args.api_key,
            args.verify_ssl
        )
        
        # Test connection
        logger.info("\nTesting connection to Elasticsearch...")
        if not manager.test_connection():
            logger.error("Failed to connect to Elasticsearch. Exiting.")
            return 1
        
        # Get all roles
        logger.info("\nRetrieving all roles from Elasticsearch...")
        all_roles = manager.get_all_roles()
        
        # Validate role names
        logger.info("\nValidating role names...")
        valid_roles, invalid_roles = validate_roles(manager, role_names, all_roles)
        
        if not valid_roles:
            logger.error("No valid roles found. Exiting.")
            return 1
        
        if invalid_roles:
            logger.warning(f"Found {len(invalid_roles)} invalid role names")
        
        # Backup roles (unless --no-backup is specified)
        if not args.no_backup:
            logger.info("\nBacking up affected roles...")
            roles_to_backup = {k: v for k, v in all_roles.items() if k in valid_roles}
            backup_file = manager.backup_roles(roles_to_backup, args.backup_dir)
            logger.info(f"Backup saved to: {backup_file}")
        
        # Analyze selected roles
        logger.info("\nAnalyzing selected roles for required updates...")
        roles_to_update = analyze_selected_roles(
            manager,
            valid_roles,
            all_roles,
            force=args.force
        )
        
        if not roles_to_update:
            logger.info("\n✓ No selected roles need updating.")
            print_summary(role_names, valid_roles, invalid_roles, {}, {}, dry_run=args.dry_run)
            return 0
        
        # Generate report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        report = generate_update_report(roles_to_update, report_file)
        logger.info(f"\nUpdate report saved to: {report_file}")
        
        # Update roles
        logger.info("\n" + "="*70)
        logger.info("UPDATING ROLES")
        logger.info("="*70)
        
        update_results = update_selected_roles(
            manager,
            all_roles,
            roles_to_update,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error
        )
        
        # Verify updates (unless dry run or --no-verify)
        verification_results = None
        if not args.dry_run and not args.no_verify:
            verification_results = verify_updates(manager, roles_to_update, update_results)
        
        # Print summary
        print_summary(
            role_names,
            valid_roles,
            invalid_roles,
            roles_to_update,
            update_results,
            verification_results,
            args.dry_run
        )
        
        # Save final status
        status_file = args.log_dir / f'role_update_status_{timestamp}.json'
        import json
        with open(status_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'dry_run': args.dry_run,
                'selected_roles': role_names,
                'valid_roles': valid_roles,
                'invalid_roles': invalid_roles,
                'roles_updated': list(update_results.keys()),
                'update_results': update_results,
                'verification_results': verification_results
            }, f, indent=2)
        logger.info(f"\nStatus saved to: {status_file}")
        
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
