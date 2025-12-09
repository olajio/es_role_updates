#!/usr/bin/env python3
"""
Elasticsearch Role Auto-Updater
Automatically updates all roles (or specific roles) with:
1. Remote index patterns converted to local patterns (CCS support)
2. Required local patterns injection (partial-*, restored-*)
3. Pattern sync from a reference file (e.g., prod cluster roles)

Usage:
    python es_role_auto_update.py --api-key <key> [options]
    python es_role_auto_update.py --api-key <key> --roles role1 role2 [options]
    python es_role_auto_update.py --api-key <key> --role-file roles.txt [options]
    python es_role_auto_update.py --api-key <key> --reference-file prod_roles.json [options]
"""

import argparse
import sys
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple
import logging

from es_role_manager_utils import (
    ElasticsearchRoleManager,
    setup_logging,
    generate_update_report
)

# ============================================================================
# CONFIGURATION - Update these values for your environment
# ============================================================================

# Elasticsearch cluster endpoint (CCS cluster)
ELASTICSEARCH_URL = "https://localhost:9200"

# Patterns to inject into ALL roles regardless of remote patterns
# These will be added if they don't already exist
REQUIRED_LOCAL_PATTERNS = {"partial-*", "restored-*"}

# You can also configure these default paths if desired
DEFAULT_BACKUP_DIR = "./backups"
DEFAULT_LOG_DIR = "./logs"

# ============================================================================


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Automatically update Elasticsearch roles with remote index patterns, required patterns, and reference file sync',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed (all roles)
  python es_role_auto_update.py --api-key <key> --dry-run
  
  # Actually update all roles (includes partial-* and restored-* injection)
  python es_role_auto_update.py --api-key <key>
  
  # Update specific roles only
  python es_role_auto_update.py --api-key <key> --roles role1 role2 --dry-run
  
  # Update roles from a file
  python es_role_auto_update.py --api-key <key> --role-file roles.txt
  
  # Sync patterns from a reference file (e.g., prod cluster roles)
  python es_role_auto_update.py --api-key <key> --reference-file prod_elk_roles.json
  
  # Inject additional custom patterns
  python es_role_auto_update.py --api-key <key> --inject-patterns custom-* archive-*
  
  # Skip required pattern injection (only do CCS pattern analysis)
  python es_role_auto_update.py --api-key <key> --skip-inject
  
  # Skip CCS analysis (only inject patterns and sync from reference)
  python es_role_auto_update.py --api-key <key> --skip-ccs-analysis
  
  # Update with custom backup directory
  python es_role_auto_update.py --api-key <key> --backup-dir /path/to/backups
  
Note: The Elasticsearch URL is configured in the script (currently: """ + ELASTICSEARCH_URL + """)
      Required local patterns (injected by default): """ + ', '.join(sorted(REQUIRED_LOCAL_PATTERNS)) + """
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
        '--reference-file',
        type=Path,
        help='JSON file containing reference roles (e.g., from prod cluster) to sync patterns from'
    )
    
    parser.add_argument(
        '--inject-patterns',
        nargs='+',
        help='Additional patterns to inject into all roles (e.g., custom-* archive-*)'
    )
    
    parser.add_argument(
        '--skip-inject',
        action='store_true',
        help='Skip injecting REQUIRED_LOCAL_PATTERNS (partial-*, restored-*)'
    )
    
    parser.add_argument(
        '--skip-ccs-analysis',
        action='store_true',
        help='Skip CCS remote-to-local pattern analysis'
    )
    
    parser.add_argument(
        '--skip-reference-sync',
        action='store_true',
        help='Skip syncing patterns from reference file (even if --reference-file is provided)'
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


def parse_reference_roles_file(file_path: Path) -> Dict[str, Dict]:
    """
    Parse a reference roles file (like prod_elk_roles.json)
    
    The file format is expected to be:
    # 1: GET _security/role/RoleName 200 OK
    {
      "RoleName": { ... }
    }
    # 2: GET _security/role/AnotherRole 200 OK
    {
      "AnotherRole": { ... }
    }
    
    Args:
        file_path: Path to the reference roles file
        
    Returns:
        Dictionary mapping role names to their definitions
    """
    logger = logging.getLogger(__name__)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Reference file not found: {file_path}")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Try to parse as pure JSON first (in case it's a standard JSON file)
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # Check if it's already in role_name: definition format
            first_key = next(iter(data.keys()), None)
            if first_key and isinstance(data.get(first_key), dict):
                # Check if it has role-like structure
                if 'indices' in data[first_key] or 'cluster' in data[first_key]:
                    logger.info(f"Loaded {len(data)} roles from JSON file: {file_path}")
                    return data
        logger.debug("File is not a standard roles JSON, trying custom format parser")
    except json.JSONDecodeError:
        logger.debug("File is not valid JSON, trying custom format parser")
    
    # Parse custom format with GET comments
    roles = {}
    
    # Split content by the comment lines and extract JSON
    lines = content.split('\n')
    current_json = []
    brace_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Skip comment lines
        if stripped.startswith('#'):
            # If we have accumulated JSON, try to parse it
            if current_json:
                try:
                    json_str = '\n'.join(current_json)
                    role_data = json.loads(json_str)
                    if isinstance(role_data, dict):
                        for role_name, role_def in role_data.items():
                            roles[role_name] = role_def
                except json.JSONDecodeError as e:
                    logger.debug(f"Failed to parse JSON block: {e}")
                current_json = []
                brace_count = 0
            continue
        
        # Skip empty lines outside of JSON
        if not stripped and brace_count == 0:
            continue
        
        # Track braces to know when JSON block ends
        brace_count += stripped.count('{') - stripped.count('}')
        current_json.append(line)
        
        # If braces are balanced and we have content, try to parse
        if brace_count == 0 and current_json:
            try:
                json_str = '\n'.join(current_json)
                role_data = json.loads(json_str)
                if isinstance(role_data, dict):
                    for role_name, role_def in role_data.items():
                        roles[role_name] = role_def
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON block: {e}")
            current_json = []
    
    # Handle any remaining JSON
    if current_json:
        try:
            json_str = '\n'.join(current_json)
            role_data = json.loads(json_str)
            if isinstance(role_data, dict):
                for role_name, role_def in role_data.items():
                    roles[role_name] = role_def
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse final JSON block: {e}")
    
    logger.info(f"Loaded {len(roles)} roles from reference file: {file_path}")
    return roles


def get_patterns_from_reference_role(role_def: Dict) -> Set[str]:
    """
    Extract all index patterns from a reference role definition
    
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


def validate_roles(
    manager: ElasticsearchRoleManager,
    role_names: List[str],
    all_roles: Dict
) -> Tuple[List[str], List[str]]:
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
    force: bool = False,
    inject_patterns: Optional[Set[str]] = None,
    reference_roles: Optional[Dict[str, Dict]] = None,
    skip_ccs_analysis: bool = False
) -> Dict[str, Dict]:
    """
    Analyze roles to find which ones need updating
    
    Args:
        manager: ElasticsearchRoleManager instance
        all_roles: Dictionary of all roles from CCS cluster
        specific_roles: Optional list of specific roles to analyze. If None, analyzes all roles
        force: If True, include roles even if they don't need updating
        inject_patterns: Optional set of patterns to inject into ALL roles if missing
        reference_roles: Optional dict of reference roles to sync patterns from
        skip_ccs_analysis: If True, skip the CCS remote-to-local pattern analysis
        
    Returns:
        Dictionary mapping role names to update info:
        {
            'role_name': {
                'patterns_to_add': set(),
                'sources': {
                    'ccs': set(),        # patterns from CCS analysis
                    'inject': set(),     # patterns from injection
                    'reference': set()   # patterns from reference file
                }
            }
        }
    """
    logger = logging.getLogger(__name__)
    
    # Determine which roles to analyze
    if specific_roles:
        roles_to_analyze = {k: v for k, v in all_roles.items() if k in specific_roles}
        logger.info(f"Analyzing {len(roles_to_analyze)} specified roles...")
    else:
        roles_to_analyze = all_roles
        logger.info(f"Analyzing all {len(roles_to_analyze)} roles...")
    
    if inject_patterns:
        logger.info(f"Will inject patterns if missing: {', '.join(sorted(inject_patterns))}")
    
    if reference_roles:
        logger.info(f"Will sync patterns from {len(reference_roles)} reference roles")
    
    roles_to_update = {}
    
    for role_name, role_def in roles_to_analyze.items():
        # Check if reserved
        if role_def.get('metadata', {}).get('_reserved'):
            logger.debug(f"Skipping reserved role: {role_name}")
            continue
        
        patterns_to_add = set()
        sources = {
            'ccs': set(),
            'inject': set(),
            'reference': set()
        }
        
        # Get existing local patterns (normalized for comparison)
        existing_local = manager.get_existing_local_patterns(role_def)
        existing_local_normalized = {
            manager.normalize_pattern_for_comparison(p) for p in existing_local
        }
        
        # 1. CCS Analysis: Add local patterns for remote patterns
        if not skip_ccs_analysis:
            needs_update, ccs_patterns = manager.needs_update(role_name, role_def)
            if ccs_patterns:
                for pattern in ccs_patterns:
                    normalized = manager.normalize_pattern_for_comparison(pattern)
                    if normalized not in existing_local_normalized:
                        patterns_to_add.add(pattern)
                        sources['ccs'].add(pattern)
                        existing_local_normalized.add(normalized)
        
        # 2. Required/Injected patterns
        if inject_patterns:
            for pattern in inject_patterns:
                normalized = manager.normalize_pattern_for_comparison(pattern)
                if normalized not in existing_local_normalized:
                    patterns_to_add.add(pattern)
                    sources['inject'].add(pattern)
                    existing_local_normalized.add(normalized)
        
        # 3. Reference file sync
        if reference_roles and role_name in reference_roles:
            ref_role_def = reference_roles[role_name]
            ref_patterns = get_patterns_from_reference_role(ref_role_def)
            
            for pattern in ref_patterns:
                normalized = manager.normalize_pattern_for_comparison(pattern)
                if normalized not in existing_local_normalized:
                    patterns_to_add.add(pattern)
                    sources['reference'].add(pattern)
                    existing_local_normalized.add(normalized)
        
        # Force mode handling
        if not patterns_to_add and force and manager.extract_remote_patterns(role_def):
            remote_patterns = manager.extract_remote_patterns(role_def)
            force_patterns = manager.get_base_patterns(remote_patterns)
            patterns_to_add.update(force_patterns)
            sources['ccs'].update(force_patterns)
        
        if patterns_to_add:
            roles_to_update[role_name] = {
                'patterns_to_add': patterns_to_add,
                'sources': sources
            }
            
            # Log details about what's being added
            source_details = []
            if sources['ccs']:
                source_details.append(f"CCS: {len(sources['ccs'])}")
            if sources['inject']:
                source_details.append(f"inject: {len(sources['inject'])}")
            if sources['reference']:
                source_details.append(f"reference: {len(sources['reference'])}")
            
            logger.info(f"✓ {role_name}: needs {len(patterns_to_add)} patterns ({', '.join(source_details)})")
            logger.debug(f"  Patterns: {', '.join(sorted(patterns_to_add))}")
        else:
            logger.debug(f"○ {role_name}: no update needed")
    
    return roles_to_update


def update_roles(
    manager: ElasticsearchRoleManager,
    all_roles: Dict,
    roles_to_update: Dict[str, Dict],
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
    
    for idx, (role_name, update_info) in enumerate(roles_to_update.items(), 1):
        patterns_to_add = update_info['patterns_to_add']
        sources = update_info['sources']
        
        logger.info(f"\n[{idx}/{total_roles}] Processing role: {role_name}")
        logger.info(f"  Patterns to add: {', '.join(sorted(patterns_to_add))}")
        
        # Show source breakdown
        if sources['ccs']:
            logger.info(f"    From CCS analysis: {', '.join(sorted(sources['ccs']))}")
        if sources['inject']:
            logger.info(f"    From injection: {', '.join(sorted(sources['inject']))}")
        if sources['reference']:
            logger.info(f"    From reference file: {', '.join(sorted(sources['reference']))}")
        
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
    roles_to_update: Dict[str, Dict]
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
    
    for role_name, update_info in roles_to_update.items():
        expected_patterns = update_info['patterns_to_add']
        
        try:
            # Fetch updated role
            updated_role = manager.get_role(role_name)
            
            if not updated_role:
                logger.error(f"  ✗ {role_name}: Role not found after update")
                verification_results[role_name] = False
                continue
            
            # Check if patterns were added
            local_patterns = manager.get_existing_local_patterns(updated_role)
            # Normalize for comparison
            local_patterns_normalized = {
                manager.normalize_pattern_for_comparison(p) for p in local_patterns
            }
            expected_normalized = {
                manager.normalize_pattern_for_comparison(p) for p in expected_patterns
            }
            missing_patterns = expected_normalized - local_patterns_normalized
            
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
    roles_to_update: Dict[str, Dict],
    update_results: Dict[str, bool],
    verification_results: Dict[str, bool] = None,
    dry_run: bool = False,
    invalid_roles: List[str] = None,
    mode: str = "all",
    inject_patterns: Set[str] = None,
    reference_file: Path = None,
    skip_ccs: bool = False
):
    """
    Print summary of operations
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
    
    # Feature status
    logger.info(f"\nFeatures enabled:")
    logger.info(f"  CCS analysis: {'DISABLED' if skip_ccs else 'ENABLED'}")
    if inject_patterns:
        logger.info(f"  Pattern injection: {', '.join(sorted(inject_patterns))}")
    else:
        logger.info(f"  Pattern injection: DISABLED")
    if reference_file:
        logger.info(f"  Reference file sync: {reference_file}")
    else:
        logger.info(f"  Reference file sync: DISABLED")
    
    logger.info(f"\nTotal roles to update: {len(roles_to_update)}")
    
    if invalid_roles:
        logger.warning(f"Invalid roles skipped: {len(invalid_roles)}")
        for role in invalid_roles:
            logger.warning(f"  - {role}")
    
    if not dry_run and update_results:
        successful = sum(1 for success in update_results.values() if success)
        failed = len(update_results) - successful
        
        logger.info(f"Successfully updated: {successful}")
        logger.info(f"Failed to update: {failed}")
        
        if verification_results:
            verified = sum(1 for v in verification_results.values() if v)
            logger.info(f"Verified successfully: {verified}/{len(verification_results)}")
    
    # Show roles that were/would be updated with details
    if roles_to_update:
        logger.info("\nRoles with updates:")
        for role_name, update_info in sorted(roles_to_update.items()):
            patterns = update_info['patterns_to_add']
            sources = update_info['sources']
            
            status = ""
            if not dry_run and role_name in update_results:
                status = " ✓" if update_results[role_name] else " ✗"
            
            source_tags = []
            if sources['ccs']:
                source_tags.append(f"CCS:{len(sources['ccs'])}")
            if sources['inject']:
                source_tags.append(f"INJ:{len(sources['inject'])}")
            if sources['reference']:
                source_tags.append(f"REF:{len(sources['reference'])}")
            
            logger.info(f"  {role_name}{status}: {len(patterns)} patterns [{', '.join(source_tags)}]")
            logger.info(f"    → {', '.join(sorted(patterns))}")
    
    logger.info("="*70)


def generate_detailed_report(
    roles_to_update: Dict[str, Dict], 
    output_file: Path,
    inject_patterns: Set[str] = None,
    reference_file: Path = None
):
    """
    Generate a detailed report of roles that need updating
    """
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_roles': len(roles_to_update),
        'config': {
            'inject_patterns': sorted(list(inject_patterns)) if inject_patterns else [],
            'reference_file': str(reference_file) if reference_file else None
        },
        'roles': {}
    }
    
    for role_name, update_info in sorted(roles_to_update.items()):
        patterns = update_info['patterns_to_add']
        sources = update_info['sources']
        
        report['roles'][role_name] = {
            'patterns_to_add': sorted(list(patterns)),
            'pattern_count': len(patterns),
            'sources': {
                'ccs': sorted(list(sources['ccs'])),
                'inject': sorted(list(sources['inject'])),
                'reference': sorted(list(sources['reference']))
            }
        }
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


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
    
    # Build set of patterns to inject
    inject_patterns = set()
    if not args.skip_inject:
        inject_patterns.update(REQUIRED_LOCAL_PATTERNS)
        logger.info(f"Required local patterns: {', '.join(sorted(REQUIRED_LOCAL_PATTERNS))}")
    else:
        logger.info("Required local pattern injection: SKIPPED (--skip-inject)")
    
    if args.inject_patterns:
        inject_patterns.update(args.inject_patterns)
        logger.info(f"Additional inject patterns from CLI: {', '.join(args.inject_patterns)}")
    
    if inject_patterns:
        logger.info(f"Total patterns to inject (if missing): {', '.join(sorted(inject_patterns))}")
    
    # Load reference roles if provided
    reference_roles = None
    if args.reference_file and not args.skip_reference_sync:
        logger.info(f"\nLoading reference roles from: {args.reference_file}")
        try:
            reference_roles = parse_reference_roles_file(args.reference_file)
            logger.info(f"Loaded {len(reference_roles)} reference roles")
        except Exception as e:
            logger.error(f"Failed to load reference file: {e}")
            return 1
    elif args.reference_file and args.skip_reference_sync:
        logger.info("Reference file sync: SKIPPED (--skip-reference-sync)")
    
    logger.info(f"\nCCS analysis: {'SKIPPED' if args.skip_ccs_analysis else 'ENABLED'}")
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
        logger.info("\nRetrieving all roles from CCS cluster...")
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
            force=args.force,
            inject_patterns=inject_patterns if inject_patterns else None,
            reference_roles=reference_roles,
            skip_ccs_analysis=args.skip_ccs_analysis
        )
        
        if not roles_to_update:
            logger.info("\n✓ No roles need updating. All roles are up to date.")
            print_summary(
                {}, 
                {}, 
                dry_run=args.dry_run, 
                mode=update_mode,
                inject_patterns=inject_patterns if inject_patterns else None,
                reference_file=args.reference_file,
                skip_ccs=args.skip_ccs_analysis
            )
            return 0
        
        logger.info(f"\nFound {len(roles_to_update)} roles that need updating")
        
        # Generate detailed report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        report = generate_detailed_report(
            roles_to_update, 
            report_file,
            inject_patterns=inject_patterns,
            reference_file=args.reference_file
        )
        logger.info(f"Update report saved to: {report_file}")
        
        # If report-only mode, exit here
        if args.report_only:
            logger.info("\nReport-only mode: exiting without making changes")
            print_summary(
                roles_to_update, 
                {}, 
                dry_run=True, 
                invalid_roles=invalid_roles,
                mode=update_mode,
                inject_patterns=inject_patterns if inject_patterns else None,
                reference_file=args.reference_file,
                skip_ccs=args.skip_ccs_analysis
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
            mode=update_mode,
            inject_patterns=inject_patterns if inject_patterns else None,
            reference_file=args.reference_file,
            skip_ccs=args.skip_ccs_analysis
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
