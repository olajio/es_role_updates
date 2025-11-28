#!/usr/bin/env python3
"""
Elasticsearch Role Auto-Updater
Automatically updates all roles with remote index patterns to include local patterns

Usage:
    python es_role_auto_update.py --es-url https://localhost:9200 --api-key <key> [options]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Set
import logging

from es_role_manager_utils import (
    ElasticsearchRoleManager,
    setup_logging,
    generate_update_report
)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Automatically update Elasticsearch roles with remote index patterns',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed
  python es_role_auto_update.py --es-url https://localhost:9200 --api-key <key> --dry-run
  
  # Actually update roles
  python es_role_auto_update.py --es-url https://localhost:9200 --api-key <key>
  
  # Update with custom backup directory
  python es_role_auto_update.py --es-url https://localhost:9200 --api-key <key> --backup-dir /path/to/backups
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
    
    return parser.parse_args()


def analyze_roles(manager: ElasticsearchRoleManager, all_roles: Dict) -> Dict[str, Set[str]]:
    """
    Analyze roles to find which ones need updating
    
    Args:
        manager: ElasticsearchRoleManager instance
        all_roles: Dictionary of all roles
        
    Returns:
        Dictionary mapping role names to patterns that need to be added
    """
    logger = logging.getLogger(__name__)
    roles_to_update = {}
    
    logger.info(f"Analyzing {len(all_roles)} roles...")
    
    for role_name, role_def in all_roles.items():
        needs_update, patterns_to_add = manager.needs_update(role_name, role_def)
        
        if needs_update:
            roles_to_update[role_name] = patterns_to_add
            logger.info(f"✓ {role_name}: needs {len(patterns_to_add)} patterns")
        else:
            logger.debug(f"○ {role_name}: no update needed")
    
    return roles_to_update


def update_roles(
    manager: ElasticsearchRoleManager,
    all_roles: Dict,
    roles_to_update: Dict[str, Set[str]],
    dry_run: bool = False
) -> Dict[str, bool]:
    """
    Update roles with missing local patterns
    
    Args:
        manager: ElasticsearchRoleManager instance
        all_roles: Dictionary of all roles
        roles_to_update: Dictionary of roles that need updating
        dry_run: If True, only show what would be changed
        
    Returns:
        Dictionary mapping role names to update success status
    """
    logger = logging.getLogger(__name__)
    results = {}
    
    for role_name, patterns_to_add in roles_to_update.items():
        logger.info(f"\nProcessing role: {role_name}")
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
                
        except Exception as e:
            logger.error(f"  ✗ Error updating {role_name}: {e}")
            results[role_name] = False
    
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
    dry_run: bool = False
):
    """Print summary of operations"""
    logger = logging.getLogger(__name__)
    
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    if dry_run:
        logger.info(f"Mode: DRY RUN (no changes made)")
    
    logger.info(f"Total roles analyzed: {len(roles_to_update)}")
    
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
    logger.info(f"Elasticsearch URL: {args.es_url}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Backup enabled: {not args.no_backup}")
    logger.info(f"Log file: {log_file}")
    logger.info("")
    
    try:
        # Initialize manager
        manager = ElasticsearchRoleManager(
            args.es_url,
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
        
        # Backup roles (unless --no-backup is specified)
        if not args.no_backup:
            logger.info("\nBacking up roles...")
            backup_file = manager.backup_roles(all_roles, args.backup_dir)
            logger.info(f"Backup saved to: {backup_file}")
        
        # Analyze roles
        logger.info("\nAnalyzing roles for required updates...")
        roles_to_update = analyze_roles(manager, all_roles)
        
        if not roles_to_update:
            logger.info("\n✓ No roles need updating. All roles are up to date.")
            return 0
        
        logger.info(f"\nFound {len(roles_to_update)} roles that need updating")
        
        # Generate report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        report = generate_update_report(roles_to_update, report_file)
        logger.info(f"Update report saved to: {report_file}")
        
        # If report-only mode, exit here
        if args.report_only:
            logger.info("\nReport-only mode: exiting without making changes")
            print_summary(roles_to_update, {}, dry_run=True)
            return 0
        
        # Update roles
        logger.info("\n" + "="*70)
        logger.info("UPDATING ROLES")
        logger.info("="*70)
        
        update_results = update_roles(
            manager,
            all_roles,
            roles_to_update,
            dry_run=args.dry_run
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
            args.dry_run
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
