#!/usr/bin/env python3
"""
Elasticsearch Role Auto-Updater (Multi-Cluster Version)

Automatically updates roles in both PROD and CCS clusters:
1. Adds required patterns (partial-*, restored-*) to PROD roles if missing
2. Adds required patterns (partial-*, restored-*) to CCS roles if missing
3. Syncs index patterns from PROD roles to corresponding CCS roles

Usage:
    python es_role_auto_update.py --config config.json --roles role1 role2 [options]
    python es_role_auto_update.py --config config.json --role-file roles.txt [options]
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple
import logging

from es_role_manager_utils import (
    ElasticsearchRoleManager,
    setup_logging,
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Patterns to inject into ALL roles if missing
REQUIRED_LOCAL_PATTERNS = {"partial-*", "restored-*"}

# Default paths
DEFAULT_BACKUP_DIR = "./backups"
DEFAULT_LOG_DIR = "./logs"
DEFAULT_CONFIG_FILE = "./es_clusters_config.json"

# ============================================================================


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Update Elasticsearch roles in PROD and CCS clusters with required patterns and sync',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed
  python es_role_auto_update.py --config es_clusters_config.json --roles Role1 Role2 --dry-run
  
  # Update specific roles
  python es_role_auto_update.py --config es_clusters_config.json --roles Role1 Role2
  
  # Update roles from a file
  python es_role_auto_update.py --config es_clusters_config.json --role-file roles.txt
  
  # Update all matching roles (roles that exist in both clusters)
  python es_role_auto_update.py --config es_clusters_config.json --all-matching
  
  # Skip PROD updates (only update CCS)
  python es_role_auto_update.py --config es_clusters_config.json --roles Role1 --skip-prod
  
  # Skip CCS updates (only update PROD)
  python es_role_auto_update.py --config es_clusters_config.json --roles Role1 --skip-ccs

Config file format (es_clusters_config.json):
  {
    "prod": {
      "url": "https://prod-elasticsearch:9200",
      "api_key": "YOUR_PROD_API_KEY",
      "verify_ssl": false
    },
    "ccs": {
      "url": "https://ccs-elasticsearch:9200", 
      "api_key": "YOUR_CCS_API_KEY",
      "verify_ssl": false
    }
  }
        """
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        default=Path(DEFAULT_CONFIG_FILE),
        help=f'Path to cluster configuration file (default: {DEFAULT_CONFIG_FILE})'
    )
    
    # Role selection
    role_group = parser.add_mutually_exclusive_group(required=True)
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
    role_group.add_argument(
        '--all-matching',
        action='store_true',
        help='Update all roles that exist in both PROD and CCS clusters'
    )
    
    parser.add_argument(
        '--inject-patterns',
        nargs='+',
        help='Additional patterns to inject (default: partial-*, restored-*)'
    )
    
    parser.add_argument(
        '--skip-inject',
        action='store_true',
        help='Skip injecting required patterns (partial-*, restored-*)'
    )
    
    parser.add_argument(
        '--skip-prod',
        action='store_true',
        help='Skip updating PROD cluster (only update CCS)'
    )
    
    parser.add_argument(
        '--skip-ccs',
        action='store_true',
        help='Skip updating CCS cluster (only update PROD)'
    )
    
    parser.add_argument(
        '--skip-sync',
        action='store_true',
        help='Skip syncing patterns from PROD to CCS'
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
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--report-only',
        action='store_true',
        help='Only generate a report without making any changes'
    )
    
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue updating other roles if one fails'
    )
    
    return parser.parse_args()


def load_config(config_path: Path) -> Dict:
    """
    Load cluster configuration from JSON file
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    logger = logging.getLogger(__name__)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Validate required fields
    required_clusters = ['prod', 'ccs']
    required_fields = ['url', 'api_key']
    
    for cluster in required_clusters:
        if cluster not in config:
            raise ValueError(f"Missing '{cluster}' configuration in config file")
        for field in required_fields:
            if field not in config[cluster]:
                raise ValueError(f"Missing '{field}' in '{cluster}' configuration")
    
    logger.info(f"Loaded configuration from: {config_path}")
    logger.info(f"  PROD: {config['prod']['url']}")
    logger.info(f"  CCS: {config['ccs']['url']}")
    
    return config


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


def get_patterns_from_role(role_def: Dict) -> Set[str]:
    """
    Extract all local index patterns from a role definition
    
    Args:
        role_def: Role definition dictionary
        
    Returns:
        Set of index patterns (excluding remote patterns with ':')
    """
    patterns = set()
    
    for index_entry in role_def.get('indices', []):
        for name in index_entry.get('names', []):
            # Only include local patterns (no cluster prefix)
            if ':' not in name:
                patterns.add(name.strip())
    
    return patterns


def analyze_role_for_updates(
    role_name: str,
    role_def: Dict,
    inject_patterns: Set[str],
    manager: ElasticsearchRoleManager
) -> Tuple[bool, Set[str]]:
    """
    Analyze a single role to determine what patterns need to be added
    
    Args:
        role_name: Name of the role
        role_def: Role definition
        inject_patterns: Set of patterns to inject if missing
        manager: ElasticsearchRoleManager instance
        
    Returns:
        Tuple of (needs_update, patterns_to_add)
    """
    logger = logging.getLogger(__name__)
    
    # Skip reserved roles
    if role_def.get('metadata', {}).get('_reserved'):
        logger.debug(f"Skipping reserved role: {role_name}")
        return False, set()
    
    # Get existing patterns (normalized for comparison)
    existing_patterns = manager.get_existing_local_patterns(role_def)
    existing_normalized = {
        manager.normalize_pattern_for_comparison(p) for p in existing_patterns
    }
    
    patterns_to_add = set()
    
    # Check each inject pattern
    for pattern in inject_patterns:
        normalized = manager.normalize_pattern_for_comparison(pattern)
        if normalized not in existing_normalized:
            patterns_to_add.add(pattern)
    
    return bool(patterns_to_add), patterns_to_add


def analyze_ccs_role_for_sync(
    role_name: str,
    ccs_role_def: Dict,
    prod_role_def: Dict,
    inject_patterns: Set[str],
    manager: ElasticsearchRoleManager,
    skip_sync: bool = False
) -> Dict:
    """
    Analyze a CCS role to determine all patterns that need to be added
    
    Args:
        role_name: Name of the role
        ccs_role_def: CCS role definition
        prod_role_def: PROD role definition
        inject_patterns: Set of patterns to inject if missing
        manager: ElasticsearchRoleManager instance
        skip_sync: If True, skip syncing patterns from PROD
        
    Returns:
        Dictionary with patterns_to_add and sources breakdown
    """
    logger = logging.getLogger(__name__)
    
    # Skip reserved roles
    if ccs_role_def.get('metadata', {}).get('_reserved'):
        logger.debug(f"Skipping reserved role: {role_name}")
        return {'patterns_to_add': set(), 'sources': {'inject': set(), 'sync': set()}}
    
    # Get existing CCS patterns (normalized for comparison)
    existing_patterns = manager.get_existing_local_patterns(ccs_role_def)
    existing_normalized = {
        manager.normalize_pattern_for_comparison(p) for p in existing_patterns
    }
    
    patterns_to_add = set()
    sources = {'inject': set(), 'sync': set()}
    
    # 1. Check inject patterns
    for pattern in inject_patterns:
        normalized = manager.normalize_pattern_for_comparison(pattern)
        if normalized not in existing_normalized:
            patterns_to_add.add(pattern)
            sources['inject'].add(pattern)
            existing_normalized.add(normalized)  # Track as added
    
    # 2. Sync patterns from PROD (if not skipping)
    if not skip_sync and prod_role_def:
        prod_patterns = get_patterns_from_role(prod_role_def)
        for pattern in prod_patterns:
            normalized = manager.normalize_pattern_for_comparison(pattern)
            if normalized not in existing_normalized:
                patterns_to_add.add(pattern)
                sources['sync'].add(pattern)
                existing_normalized.add(normalized)  # Track as added
    
    return {
        'patterns_to_add': patterns_to_add,
        'sources': sources
    }


def update_single_role(
    manager: ElasticsearchRoleManager,
    role_name: str,
    role_def: Dict,
    patterns_to_add: Set[str],
    cluster_name: str,
    dry_run: bool = False
) -> bool:
    """
    Update a single role with new patterns
    
    Args:
        manager: ElasticsearchRoleManager instance
        role_name: Name of the role
        role_def: Current role definition
        patterns_to_add: Set of patterns to add
        cluster_name: Name of the cluster (for logging)
        dry_run: If True, don't actually update
        
    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    if dry_run:
        logger.info(f"  [{cluster_name}] [DRY RUN] Would add {len(patterns_to_add)} patterns")
        return True
    
    try:
        updated_role = manager.add_local_patterns_to_role(role_def, patterns_to_add)
        success = manager.update_role(role_name, updated_role)
        
        if success:
            logger.info(f"  [{cluster_name}] ✓ Successfully updated {role_name}")
        else:
            logger.error(f"  [{cluster_name}] ✗ Failed to update {role_name}")
        
        return success
    except Exception as e:
        logger.error(f"  [{cluster_name}] ✗ Error updating {role_name}: {e}")
        return False


def generate_report(
    prod_updates: Dict[str, Dict],
    ccs_updates: Dict[str, Dict],
    output_file: Path,
    inject_patterns: Set[str]
):
    """Generate a detailed JSON report"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'inject_patterns': sorted(list(inject_patterns))
        },
        'summary': {
            'prod_roles_to_update': len(prod_updates),
            'ccs_roles_to_update': len(ccs_updates)
        },
        'prod_updates': {},
        'ccs_updates': {}
    }
    
    for role_name, info in sorted(prod_updates.items()):
        report['prod_updates'][role_name] = {
            'patterns_to_add': sorted(list(info['patterns_to_add'])),
            'count': len(info['patterns_to_add'])
        }
    
    for role_name, info in sorted(ccs_updates.items()):
        report['ccs_updates'][role_name] = {
            'patterns_to_add': sorted(list(info['patterns_to_add'])),
            'count': len(info['patterns_to_add']),
            'sources': {
                'inject': sorted(list(info['sources']['inject'])),
                'sync': sorted(list(info['sources']['sync']))
            }
        }
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def print_summary(
    prod_updates: Dict[str, Dict],
    ccs_updates: Dict[str, Dict],
    prod_results: Dict[str, bool],
    ccs_results: Dict[str, bool],
    dry_run: bool,
    skip_prod: bool,
    skip_ccs: bool,
    inject_patterns: Set[str]
):
    """Print summary of operations"""
    logger = logging.getLogger(__name__)
    
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    if dry_run:
        logger.info("Mode: DRY RUN (no changes made)")
    
    logger.info(f"\nRequired patterns: {', '.join(sorted(inject_patterns))}")
    
    # PROD Summary
    logger.info(f"\n--- PROD CLUSTER ---")
    if skip_prod:
        logger.info("  SKIPPED")
    else:
        logger.info(f"  Roles to update: {len(prod_updates)}")
        if not dry_run and prod_results:
            successful = sum(1 for s in prod_results.values() if s)
            logger.info(f"  Successfully updated: {successful}")
            logger.info(f"  Failed: {len(prod_results) - successful}")
        
        if prod_updates:
            for role_name, info in sorted(prod_updates.items()):
                status = ""
                if not dry_run and role_name in prod_results:
                    status = " ✓" if prod_results[role_name] else " ✗"
                patterns = info['patterns_to_add']
                logger.info(f"    {role_name}{status}: +{len(patterns)} → {', '.join(sorted(patterns))}")
    
    # CCS Summary
    logger.info(f"\n--- CCS CLUSTER ---")
    if skip_ccs:
        logger.info("  SKIPPED")
    else:
        logger.info(f"  Roles to update: {len(ccs_updates)}")
        if not dry_run and ccs_results:
            successful = sum(1 for s in ccs_results.values() if s)
            logger.info(f"  Successfully updated: {successful}")
            logger.info(f"  Failed: {len(ccs_results) - successful}")
        
        if ccs_updates:
            for role_name, info in sorted(ccs_updates.items()):
                status = ""
                if not dry_run and role_name in ccs_results:
                    status = " ✓" if ccs_results[role_name] else " ✗"
                patterns = info['patterns_to_add']
                sources = info['sources']
                
                source_tags = []
                if sources['inject']:
                    source_tags.append(f"INJ:{len(sources['inject'])}")
                if sources['sync']:
                    source_tags.append(f"SYNC:{len(sources['sync'])}")
                
                logger.info(f"    {role_name}{status}: +{len(patterns)} [{', '.join(source_tags)}]")
                logger.info(f"      → {', '.join(sorted(patterns))}")
    
    logger.info("="*70)


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Setup logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = args.log_dir / f'role_auto_update_{timestamp}.log'
    logger = setup_logging(log_file, args.log_level)
    
    logger.info("="*70)
    logger.info("Elasticsearch Role Auto-Updater (Multi-Cluster)")
    logger.info("="*70)
    
    try:
        # Load configuration
        logger.info(f"\nLoading configuration from: {args.config}")
        config = load_config(args.config)
        
        # Build inject patterns set
        inject_patterns = set()
        if not args.skip_inject:
            inject_patterns.update(REQUIRED_LOCAL_PATTERNS)
        if args.inject_patterns:
            inject_patterns.update(args.inject_patterns)
        
        logger.info(f"\nRequired patterns to inject: {', '.join(sorted(inject_patterns)) if inject_patterns else 'NONE'}")
        logger.info(f"Update PROD: {'SKIP' if args.skip_prod else 'YES'}")
        logger.info(f"Update CCS: {'SKIP' if args.skip_ccs else 'YES'}")
        logger.info(f"Sync PROD→CCS: {'SKIP' if args.skip_sync else 'YES'}")
        logger.info(f"Dry run: {args.dry_run}")
        logger.info(f"Log file: {log_file}")
        
        # Get role names to update
        if args.roles:
            role_names = args.roles
            logger.info(f"\nRoles specified via command line: {len(role_names)}")
        elif args.role_file:
            role_names = load_roles_from_file(args.role_file)
            logger.info(f"\nRoles loaded from file: {args.role_file}")
        else:
            role_names = None  # Will be determined by --all-matching
            logger.info(f"\nMode: Update all matching roles")
        
        # Initialize managers for both clusters
        logger.info("\n" + "-"*70)
        logger.info("CONNECTING TO CLUSTERS")
        logger.info("-"*70)
        
        # PROD Manager
        if not args.skip_prod or not args.skip_sync:
            logger.info("\nConnecting to PROD cluster...")
            prod_manager = ElasticsearchRoleManager(
                config['prod']['url'],
                config['prod']['api_key'],
                config['prod'].get('verify_ssl', False)
            )
            if not prod_manager.test_connection():
                logger.error("Failed to connect to PROD cluster. Exiting.")
                return 1
            
            logger.info("Retrieving roles from PROD...")
            prod_all_roles = prod_manager.get_all_roles()
            logger.info(f"Retrieved {len(prod_all_roles)} roles from PROD")
        else:
            prod_manager = None
            prod_all_roles = {}
        
        # CCS Manager
        if not args.skip_ccs:
            logger.info("\nConnecting to CCS cluster...")
            ccs_manager = ElasticsearchRoleManager(
                config['ccs']['url'],
                config['ccs']['api_key'],
                config['ccs'].get('verify_ssl', False)
            )
            if not ccs_manager.test_connection():
                logger.error("Failed to connect to CCS cluster. Exiting.")
                return 1
            
            logger.info("Retrieving roles from CCS...")
            ccs_all_roles = ccs_manager.get_all_roles()
            logger.info(f"Retrieved {len(ccs_all_roles)} roles from CCS")
        else:
            ccs_manager = None
            ccs_all_roles = {}
        
        # Determine which roles to process
        if args.all_matching:
            # Find roles that exist in both clusters
            common_roles = set(prod_all_roles.keys()) & set(ccs_all_roles.keys())
            # Filter out reserved roles
            role_names = [r for r in common_roles 
                         if not prod_all_roles.get(r, {}).get('metadata', {}).get('_reserved')
                         and not ccs_all_roles.get(r, {}).get('metadata', {}).get('_reserved')]
            logger.info(f"\nFound {len(role_names)} non-reserved roles in both clusters")
        
        # Validate role names
        valid_roles = []
        invalid_roles = []
        
        for role_name in role_names:
            exists_in_prod = role_name in prod_all_roles
            exists_in_ccs = role_name in ccs_all_roles
            
            if not args.skip_prod and not exists_in_prod:
                logger.warning(f"Role not found in PROD: {role_name}")
                invalid_roles.append(f"{role_name} (not in PROD)")
            elif not args.skip_ccs and not exists_in_ccs:
                logger.warning(f"Role not found in CCS: {role_name}")
                invalid_roles.append(f"{role_name} (not in CCS)")
            else:
                valid_roles.append(role_name)
        
        if not valid_roles:
            logger.error("No valid roles to update. Exiting.")
            return 1
        
        logger.info(f"\nValid roles to process: {len(valid_roles)}")
        if invalid_roles:
            logger.warning(f"Invalid/missing roles: {len(invalid_roles)}")
        
        # Create backups
        if not args.no_backup:
            logger.info("\n" + "-"*70)
            logger.info("CREATING BACKUPS")
            logger.info("-"*70)
            
            if prod_manager and not args.skip_prod:
                prod_roles_to_backup = {k: v for k, v in prod_all_roles.items() if k in valid_roles}
                prod_backup_file = prod_manager.backup_roles(
                    prod_roles_to_backup, 
                    args.backup_dir / 'prod'
                )
                logger.info(f"PROD backup: {prod_backup_file}")
            
            if ccs_manager and not args.skip_ccs:
                ccs_roles_to_backup = {k: v for k, v in ccs_all_roles.items() if k in valid_roles}
                ccs_backup_file = ccs_manager.backup_roles(
                    ccs_roles_to_backup,
                    args.backup_dir / 'ccs'
                )
                logger.info(f"CCS backup: {ccs_backup_file}")
        
        # Analyze roles
        logger.info("\n" + "-"*70)
        logger.info("ANALYZING ROLES")
        logger.info("-"*70)
        
        prod_updates = {}  # role_name -> {'patterns_to_add': set()}
        ccs_updates = {}   # role_name -> {'patterns_to_add': set(), 'sources': {...}}
        
        for role_name in valid_roles:
            logger.info(f"\nAnalyzing: {role_name}")
            
            # Analyze PROD role
            if not args.skip_prod and role_name in prod_all_roles:
                prod_role_def = prod_all_roles[role_name]
                needs_update, patterns_to_add = analyze_role_for_updates(
                    role_name, prod_role_def, inject_patterns, prod_manager
                )
                if needs_update:
                    prod_updates[role_name] = {'patterns_to_add': patterns_to_add}
                    logger.info(f"  [PROD] Needs {len(patterns_to_add)} patterns: {', '.join(sorted(patterns_to_add))}")
                else:
                    logger.info(f"  [PROD] Already has all required patterns")
            
            # Analyze CCS role
            if not args.skip_ccs and role_name in ccs_all_roles:
                ccs_role_def = ccs_all_roles[role_name]
                prod_role_def = prod_all_roles.get(role_name) if not args.skip_sync else None
                
                analysis = analyze_ccs_role_for_sync(
                    role_name, ccs_role_def, prod_role_def,
                    inject_patterns, ccs_manager, args.skip_sync
                )
                
                if analysis['patterns_to_add']:
                    ccs_updates[role_name] = analysis
                    sources = analysis['sources']
                    logger.info(f"  [CCS] Needs {len(analysis['patterns_to_add'])} patterns:")
                    if sources['inject']:
                        logger.info(f"    From injection: {', '.join(sorted(sources['inject']))}")
                    if sources['sync']:
                        logger.info(f"    From PROD sync: {', '.join(sorted(sources['sync']))}")
                else:
                    logger.info(f"  [CCS] Already has all required patterns")
        
        # Check if any updates needed
        if not prod_updates and not ccs_updates:
            logger.info("\n✓ No roles need updating. All roles are up to date.")
            print_summary(
                prod_updates, ccs_updates, {}, {},
                args.dry_run, args.skip_prod, args.skip_ccs, inject_patterns
            )
            return 0
        
        logger.info(f"\nRoles needing updates - PROD: {len(prod_updates)}, CCS: {len(ccs_updates)}")
        
        # Generate report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        generate_report(prod_updates, ccs_updates, report_file, inject_patterns)
        logger.info(f"Report saved to: {report_file}")
        
        # If report-only mode, exit here
        if args.report_only:
            logger.info("\nReport-only mode: exiting without making changes")
            print_summary(
                prod_updates, ccs_updates, {}, {},
                True, args.skip_prod, args.skip_ccs, inject_patterns
            )
            return 0
        
        # Perform updates
        logger.info("\n" + "="*70)
        logger.info("UPDATING ROLES")
        logger.info("="*70)
        
        prod_results = {}
        ccs_results = {}
        
        # Update PROD roles
        if prod_updates and not args.skip_prod:
            logger.info("\n--- Updating PROD Cluster ---")
            for idx, (role_name, info) in enumerate(prod_updates.items(), 1):
                logger.info(f"\n[{idx}/{len(prod_updates)}] {role_name}")
                logger.info(f"  Adding: {', '.join(sorted(info['patterns_to_add']))}")
                
                success = update_single_role(
                    prod_manager, role_name, prod_all_roles[role_name],
                    info['patterns_to_add'], "PROD", args.dry_run
                )
                prod_results[role_name] = success
                
                if not success and not args.continue_on_error:
                    logger.error("Stopping due to error (use --continue-on-error to continue)")
                    break
        
        # Update CCS roles
        if ccs_updates and not args.skip_ccs:
            logger.info("\n--- Updating CCS Cluster ---")
            for idx, (role_name, info) in enumerate(ccs_updates.items(), 1):
                logger.info(f"\n[{idx}/{len(ccs_updates)}] {role_name}")
                logger.info(f"  Adding: {', '.join(sorted(info['patterns_to_add']))}")
                
                success = update_single_role(
                    ccs_manager, role_name, ccs_all_roles[role_name],
                    info['patterns_to_add'], "CCS", args.dry_run
                )
                ccs_results[role_name] = success
                
                if not success and not args.continue_on_error:
                    logger.error("Stopping due to error (use --continue-on-error to continue)")
                    break
        
        # Print summary
        print_summary(
            prod_updates, ccs_updates,
            prod_results, ccs_results,
            args.dry_run, args.skip_prod, args.skip_ccs,
            inject_patterns
        )
        
        # Return appropriate exit code
        if args.dry_run:
            return 0
        
        all_prod_success = all(prod_results.values()) if prod_results else True
        all_ccs_success = all(ccs_results.values()) if ccs_results else True
        
        return 0 if (all_prod_success and all_ccs_success) else 1
        
    except KeyboardInterrupt:
        logger.warning("\nOperation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
