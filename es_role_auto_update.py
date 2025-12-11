#!/usr/bin/env python3
"""
Elasticsearch Role Auto-Updater (Multi-Cluster Version)

Automatically updates roles across multiple Elasticsearch clusters:
1. Adds required patterns (partial-*, restored-*) to source cluster roles
2. Syncs index patterns from source clusters to CCS cluster roles

Supports any number of clusters defined in the configuration file.

Usage:
    # Add patterns to prod, qa, dev and sync to CCS
    python es_role_auto_update.py --config config.json --roles role1 role2 \
        --source-clusters prod qa dev --ccs-cluster ccs

    # Only update prod and sync to CCS
    python es_role_auto_update.py --config config.json --role-file roles.txt \
        --source-clusters prod --ccs-cluster ccs

    # Only add patterns to source clusters (no CCS sync)
    python es_role_auto_update.py --config config.json --roles role1 \
        --source-clusters prod qa dev --skip-ccs
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

# Default patterns to inject into ALL roles if missing
DEFAULT_INJECT_PATTERNS = {"partial-*", "restored-*"}

# Default paths
DEFAULT_BACKUP_DIR = "./backups"
DEFAULT_LOG_DIR = "./logs"
DEFAULT_CONFIG_FILE = "./es_clusters_config.json"

# ============================================================================


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Update Elasticsearch roles across multiple clusters with required patterns and sync to CCS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available clusters in config
  python es_role_auto_update.py --config es_clusters_config.json --list-clusters

  # Dry run: update prod, qa, dev and sync to CCS
  python es_role_auto_update.py --config es_clusters_config.json \\
      --roles Role1 Role2 \\
      --source-clusters prod qa dev \\
      --ccs-cluster ccs \\
      --dry-run

  # Update only prod cluster (no CCS)
  python es_role_auto_update.py --config es_clusters_config.json \\
      --roles Role1 \\
      --source-clusters prod \\
      --skip-ccs

  # Update CCS only (sync from prod, qa, dev)
  python es_role_auto_update.py --config es_clusters_config.json \\
      --roles Role1 \\
      --source-clusters prod qa dev \\
      --ccs-cluster ccs \\
      --skip-source

  # Use roles from file
  python es_role_auto_update.py --config es_clusters_config.json \\
      --role-file roles.txt \\
      --source-clusters prod qa dev \\
      --ccs-cluster ccs

Config file format (es_clusters_config.json):
  {
    "clusters": {
      "prod": {
        "url": "https://prod-elasticsearch:9200",
        "api_key": "YOUR_API_KEY",
        "verify_ssl": false
      },
      "qa": { ... },
      "dev": { ... },
      "ccs": { ... }
    },
    "defaults": {
      "inject_patterns": ["partial-*", "restored-*"],
      "source_clusters": ["prod", "qa", "dev"],
      "ccs_cluster": "ccs"
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
    
    parser.add_argument(
        '--list-clusters',
        action='store_true',
        help='List available clusters from config and exit'
    )
    
    # Role selection
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
    role_group.add_argument(
        '--all-matching',
        action='store_true',
        help='Update all roles that exist in all specified clusters'
    )
    
    # Cluster selection
    parser.add_argument(
        '--source-clusters',
        nargs='+',
        help='Source clusters to update with required patterns (e.g., prod qa dev)'
    )
    
    parser.add_argument(
        '--ccs-cluster',
        help='CCS cluster to sync patterns to (e.g., ccs)'
    )
    
    parser.add_argument(
        '--skip-source',
        action='store_true',
        help='Skip updating source clusters (only update CCS)'
    )
    
    parser.add_argument(
        '--skip-ccs',
        action='store_true',
        help='Skip updating CCS cluster (only update source clusters)'
    )
    
    # Pattern options
    parser.add_argument(
        '--inject-patterns',
        nargs='+',
        help='Patterns to inject (default: partial-*, restored-*)'
    )
    
    parser.add_argument(
        '--skip-inject',
        action='store_true',
        help='Skip injecting required patterns'
    )
    
    # Operational options
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
    
    # Support both old format (prod/ccs at root) and new format (clusters dict)
    if 'clusters' not in config:
        # Convert old format to new format
        logger.info("Converting old config format to new format...")
        new_config = {
            'clusters': {},
            'defaults': {
                'inject_patterns': list(DEFAULT_INJECT_PATTERNS),
                'source_clusters': [],
                'ccs_cluster': None
            }
        }
        for key, value in config.items():
            if isinstance(value, dict) and 'url' in value:
                new_config['clusters'][key] = value
                if key == 'ccs':
                    new_config['defaults']['ccs_cluster'] = key
                else:
                    new_config['defaults']['source_clusters'].append(key)
        config = new_config
    
    # Validate clusters exist
    if not config.get('clusters'):
        raise ValueError("No clusters defined in configuration file")
    
    # Validate each cluster has required fields
    required_fields = ['url', 'api_key']
    for cluster_name, cluster_config in config['clusters'].items():
        for field in required_fields:
            if field not in cluster_config:
                raise ValueError(f"Missing '{field}' in cluster '{cluster_name}' configuration")
    
    logger.info(f"Loaded configuration from: {config_path}")
    logger.info(f"Available clusters: {', '.join(config['clusters'].keys())}")
    
    return config


def list_clusters(config: Dict):
    """Print available clusters and exit"""
    print("\nAvailable clusters in configuration:")
    print("-" * 50)
    
    for name, cluster in config['clusters'].items():
        description = cluster.get('description', 'No description')
        url = cluster['url']
        print(f"  {name:15} - {url}")
        print(f"  {' '*15}   {description}")
        print()
    
    if 'defaults' in config:
        print("Default settings:")
        defaults = config['defaults']
        if defaults.get('source_clusters'):
            print(f"  Source clusters: {', '.join(defaults['source_clusters'])}")
        if defaults.get('ccs_cluster'):
            print(f"  CCS cluster: {defaults['ccs_cluster']}")
        if defaults.get('inject_patterns'):
            print(f"  Inject patterns: {', '.join(defaults['inject_patterns'])}")


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


def analyze_role_for_injection(
    role_name: str,
    role_def: Dict,
    inject_patterns: Set[str],
    manager: ElasticsearchRoleManager
) -> Tuple[bool, Set[str]]:
    """
    Analyze a single role to determine what patterns need to be injected
    
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
    source_roles: Dict[str, Dict],  # cluster_name -> role_def
    inject_patterns: Set[str],
    manager: ElasticsearchRoleManager,
    skip_inject: bool = False
) -> Dict:
    """
    Analyze a CCS role to determine all patterns that need to be added
    
    Args:
        role_name: Name of the role
        ccs_role_def: CCS role definition
        source_roles: Dict mapping cluster name to role definition
        inject_patterns: Set of patterns to inject if missing
        manager: ElasticsearchRoleManager instance
        skip_inject: If True, skip injecting patterns
        
    Returns:
        Dictionary with patterns_to_add and sources breakdown
    """
    logger = logging.getLogger(__name__)
    
    # Skip reserved roles
    if ccs_role_def.get('metadata', {}).get('_reserved'):
        logger.debug(f"Skipping reserved role: {role_name}")
        return {'patterns_to_add': set(), 'sources': {'inject': set(), 'sync': {}}}
    
    # Get existing CCS patterns (normalized for comparison)
    existing_patterns = manager.get_existing_local_patterns(ccs_role_def)
    existing_normalized = {
        manager.normalize_pattern_for_comparison(p) for p in existing_patterns
    }
    
    patterns_to_add = set()
    sources = {'inject': set(), 'sync': {}}  # sync is dict: cluster_name -> patterns
    
    # 1. Check inject patterns (if not skipped)
    if not skip_inject:
        for pattern in inject_patterns:
            normalized = manager.normalize_pattern_for_comparison(pattern)
            if normalized not in existing_normalized:
                patterns_to_add.add(pattern)
                sources['inject'].add(pattern)
                existing_normalized.add(normalized)  # Track as added
    
    # 2. Sync patterns from each source cluster
    for cluster_name, role_def in source_roles.items():
        if role_def is None:
            continue
        
        source_patterns = get_patterns_from_role(role_def)
        cluster_sync = set()
        
        for pattern in source_patterns:
            normalized = manager.normalize_pattern_for_comparison(pattern)
            if normalized not in existing_normalized:
                patterns_to_add.add(pattern)
                cluster_sync.add(pattern)
                existing_normalized.add(normalized)  # Track as added
        
        if cluster_sync:
            sources['sync'][cluster_name] = cluster_sync
    
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
    source_updates: Dict[str, Dict[str, Dict]],  # cluster -> role -> info
    ccs_updates: Dict[str, Dict],
    output_file: Path,
    inject_patterns: Set[str],
    source_clusters: List[str],
    ccs_cluster: str
):
    """Generate a detailed JSON report"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'inject_patterns': sorted(list(inject_patterns)),
            'source_clusters': source_clusters,
            'ccs_cluster': ccs_cluster
        },
        'summary': {
            'source_clusters_updated': {
                cluster: len(updates) for cluster, updates in source_updates.items()
            },
            'ccs_roles_to_update': len(ccs_updates)
        },
        'source_updates': {},
        'ccs_updates': {}
    }
    
    # Source cluster updates
    for cluster_name, updates in sorted(source_updates.items()):
        report['source_updates'][cluster_name] = {}
        for role_name, info in sorted(updates.items()):
            report['source_updates'][cluster_name][role_name] = {
                'patterns_to_add': sorted(list(info['patterns_to_add'])),
                'count': len(info['patterns_to_add'])
            }
    
    # CCS updates
    for role_name, info in sorted(ccs_updates.items()):
        sync_sources = {}
        for cluster, patterns in info['sources'].get('sync', {}).items():
            sync_sources[cluster] = sorted(list(patterns))
        
        report['ccs_updates'][role_name] = {
            'patterns_to_add': sorted(list(info['patterns_to_add'])),
            'count': len(info['patterns_to_add']),
            'sources': {
                'inject': sorted(list(info['sources']['inject'])),
                'sync': sync_sources
            }
        }
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def print_summary(
    source_updates: Dict[str, Dict[str, Dict]],
    ccs_updates: Dict[str, Dict],
    source_results: Dict[str, Dict[str, bool]],
    ccs_results: Dict[str, bool],
    dry_run: bool,
    skip_source: bool,
    skip_ccs: bool,
    inject_patterns: Set[str],
    source_clusters: List[str],
    ccs_cluster: str
):
    """Print summary of operations"""
    logger = logging.getLogger(__name__)
    
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    if dry_run:
        logger.info("Mode: DRY RUN (no changes made)")
    
    logger.info(f"\nRequired patterns: {', '.join(sorted(inject_patterns))}")
    logger.info(f"Source clusters: {', '.join(source_clusters)}")
    logger.info(f"CCS cluster: {ccs_cluster}")
    
    # Source Cluster Summaries
    for cluster_name in source_clusters:
        logger.info(f"\n--- {cluster_name.upper()} CLUSTER ---")
        if skip_source:
            logger.info("  SKIPPED")
        else:
            updates = source_updates.get(cluster_name, {})
            results = source_results.get(cluster_name, {})
            
            logger.info(f"  Roles to update: {len(updates)}")
            if not dry_run and results:
                successful = sum(1 for s in results.values() if s)
                logger.info(f"  Successfully updated: {successful}")
                logger.info(f"  Failed: {len(results) - successful}")
            
            if updates:
                for role_name, info in sorted(updates.items()):
                    status = ""
                    if not dry_run and role_name in results:
                        status = " ✓" if results[role_name] else " ✗"
                    patterns = info['patterns_to_add']
                    logger.info(f"    {role_name}{status}: +{len(patterns)} → {', '.join(sorted(patterns))}")
    
    # CCS Summary
    logger.info(f"\n--- {ccs_cluster.upper()} CLUSTER (CCS) ---")
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
                for cluster, sync_patterns in sources.get('sync', {}).items():
                    source_tags.append(f"{cluster.upper()}:{len(sync_patterns)}")
                
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
    
    try:
        # Load configuration first (needed for --list-clusters)
        logger.info(f"Loading configuration from: {args.config}")
        config = load_config(args.config)
        
        # Handle --list-clusters
        if args.list_clusters:
            list_clusters(config)
            return 0
        
        logger.info("="*70)
        logger.info("Elasticsearch Role Auto-Updater (Multi-Cluster)")
        logger.info("="*70)
        
        # Get defaults from config
        defaults = config.get('defaults', {})
        
        # Determine source clusters
        source_clusters = args.source_clusters or defaults.get('source_clusters', [])
        if not source_clusters and not args.skip_source:
            logger.error("No source clusters specified. Use --source-clusters or set defaults in config.")
            return 1
        
        # Validate source clusters exist
        for cluster in source_clusters:
            if cluster not in config['clusters']:
                logger.error(f"Source cluster '{cluster}' not found in configuration.")
                logger.error(f"Available clusters: {', '.join(config['clusters'].keys())}")
                return 1
        
        # Determine CCS cluster
        ccs_cluster = args.ccs_cluster or defaults.get('ccs_cluster')
        if not ccs_cluster and not args.skip_ccs:
            logger.error("No CCS cluster specified. Use --ccs-cluster or set defaults in config.")
            return 1
        
        if ccs_cluster and ccs_cluster not in config['clusters']:
            logger.error(f"CCS cluster '{ccs_cluster}' not found in configuration.")
            logger.error(f"Available clusters: {', '.join(config['clusters'].keys())}")
            return 1
        
        # Build inject patterns set
        inject_patterns = set()
        if not args.skip_inject:
            if args.inject_patterns:
                inject_patterns.update(args.inject_patterns)
            elif defaults.get('inject_patterns'):
                inject_patterns.update(defaults['inject_patterns'])
            else:
                inject_patterns.update(DEFAULT_INJECT_PATTERNS)
        
        logger.info(f"\nPatterns to inject: {', '.join(sorted(inject_patterns)) if inject_patterns else 'NONE'}")
        logger.info(f"Source clusters: {', '.join(source_clusters)}")
        logger.info(f"CCS cluster: {ccs_cluster if not args.skip_ccs else 'SKIPPED'}")
        logger.info(f"Update sources: {'SKIP' if args.skip_source else 'YES'}")
        logger.info(f"Update CCS: {'SKIP' if args.skip_ccs else 'YES'}")
        logger.info(f"Dry run: {args.dry_run}")
        logger.info(f"Log file: {log_file}")
        
        # Get role names to update
        if args.roles:
            role_names = args.roles
            logger.info(f"\nRoles specified via command line: {len(role_names)}")
        elif args.role_file:
            role_names = load_roles_from_file(args.role_file)
            logger.info(f"\nRoles loaded from file: {args.role_file}")
        elif args.all_matching:
            role_names = None  # Will be determined after fetching roles
            logger.info(f"\nMode: Update all matching roles")
        else:
            logger.error("No roles specified. Use --roles, --role-file, or --all-matching.")
            return 1
        
        # Initialize managers and fetch roles
        logger.info("\n" + "-"*70)
        logger.info("CONNECTING TO CLUSTERS")
        logger.info("-"*70)
        
        source_managers = {}  # cluster_name -> manager
        source_all_roles = {}  # cluster_name -> {role_name -> role_def}
        
        # Connect to source clusters
        if not args.skip_source or not args.skip_ccs:
            for cluster_name in source_clusters:
                cluster_config = config['clusters'][cluster_name]
                logger.info(f"\nConnecting to {cluster_name.upper()} cluster...")
                
                manager = ElasticsearchRoleManager(
                    cluster_config['url'],
                    cluster_config['api_key'],
                    cluster_config.get('verify_ssl', False)
                )
                
                if not manager.test_connection():
                    logger.error(f"Failed to connect to {cluster_name} cluster. Exiting.")
                    return 1
                
                logger.info(f"Retrieving roles from {cluster_name}...")
                all_roles = manager.get_all_roles()
                logger.info(f"Retrieved {len(all_roles)} roles from {cluster_name}")
                
                source_managers[cluster_name] = manager
                source_all_roles[cluster_name] = all_roles
        
        # Connect to CCS cluster
        ccs_manager = None
        ccs_all_roles = {}
        
        if not args.skip_ccs and ccs_cluster:
            cluster_config = config['clusters'][ccs_cluster]
            logger.info(f"\nConnecting to {ccs_cluster.upper()} (CCS) cluster...")
            
            ccs_manager = ElasticsearchRoleManager(
                cluster_config['url'],
                cluster_config['api_key'],
                cluster_config.get('verify_ssl', False)
            )
            
            if not ccs_manager.test_connection():
                logger.error(f"Failed to connect to {ccs_cluster} cluster. Exiting.")
                return 1
            
            logger.info(f"Retrieving roles from {ccs_cluster}...")
            ccs_all_roles = ccs_manager.get_all_roles()
            logger.info(f"Retrieved {len(ccs_all_roles)} roles from {ccs_cluster}")
        
        # Determine roles to process (if --all-matching)
        if args.all_matching:
            # Find roles that exist in all clusters
            all_role_sets = [set(roles.keys()) for roles in source_all_roles.values()]
            if ccs_all_roles:
                all_role_sets.append(set(ccs_all_roles.keys()))
            
            if all_role_sets:
                common_roles = set.intersection(*all_role_sets)
                # Filter out reserved roles
                role_names = []
                for role in common_roles:
                    is_reserved = False
                    for cluster_roles in source_all_roles.values():
                        if cluster_roles.get(role, {}).get('metadata', {}).get('_reserved'):
                            is_reserved = True
                            break
                    if not is_reserved:
                        role_names.append(role)
                logger.info(f"\nFound {len(role_names)} non-reserved roles in all clusters")
            else:
                role_names = []
        
        # Validate role names across clusters
        valid_roles = []
        invalid_roles = []
        
        for role_name in role_names:
            is_valid = True
            
            # Check in source clusters
            if not args.skip_source:
                for cluster_name in source_clusters:
                    if role_name not in source_all_roles.get(cluster_name, {}):
                        logger.warning(f"Role not found in {cluster_name}: {role_name}")
                        invalid_roles.append(f"{role_name} (not in {cluster_name})")
                        is_valid = False
                        break
            
            # Check in CCS cluster
            if is_valid and not args.skip_ccs and ccs_all_roles:
                if role_name not in ccs_all_roles:
                    logger.warning(f"Role not found in {ccs_cluster}: {role_name}")
                    invalid_roles.append(f"{role_name} (not in {ccs_cluster})")
                    is_valid = False
            
            if is_valid:
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
            
            if not args.skip_source:
                for cluster_name, manager in source_managers.items():
                    roles_to_backup = {k: v for k, v in source_all_roles[cluster_name].items() if k in valid_roles}
                    backup_file = manager.backup_roles(
                        roles_to_backup,
                        args.backup_dir / cluster_name
                    )
                    logger.info(f"{cluster_name.upper()} backup: {backup_file}")
            
            if ccs_manager and not args.skip_ccs:
                roles_to_backup = {k: v for k, v in ccs_all_roles.items() if k in valid_roles}
                backup_file = ccs_manager.backup_roles(
                    roles_to_backup,
                    args.backup_dir / ccs_cluster
                )
                logger.info(f"{ccs_cluster.upper()} backup: {backup_file}")
        
        # Analyze roles
        logger.info("\n" + "-"*70)
        logger.info("ANALYZING ROLES")
        logger.info("-"*70)
        
        source_updates = {cluster: {} for cluster in source_clusters}  # cluster -> {role -> info}
        ccs_updates = {}  # role -> info
        
        for role_name in valid_roles:
            logger.info(f"\nAnalyzing: {role_name}")
            
            # Analyze source cluster roles
            if not args.skip_source:
                for cluster_name in source_clusters:
                    if role_name in source_all_roles.get(cluster_name, {}):
                        role_def = source_all_roles[cluster_name][role_name]
                        needs_update, patterns_to_add = analyze_role_for_injection(
                            role_name, role_def, inject_patterns, source_managers[cluster_name]
                        )
                        if needs_update:
                            source_updates[cluster_name][role_name] = {'patterns_to_add': patterns_to_add}
                            logger.info(f"  [{cluster_name.upper()}] Needs {len(patterns_to_add)} patterns: {', '.join(sorted(patterns_to_add))}")
                        else:
                            logger.info(f"  [{cluster_name.upper()}] Already has all required patterns")
            
            # Analyze CCS role
            if not args.skip_ccs and role_name in ccs_all_roles:
                ccs_role_def = ccs_all_roles[role_name]
                
                # Get source role definitions for sync
                source_role_defs = {}
                for cluster_name in source_clusters:
                    source_role_defs[cluster_name] = source_all_roles.get(cluster_name, {}).get(role_name)
                
                analysis = analyze_ccs_role_for_sync(
                    role_name, ccs_role_def, source_role_defs,
                    inject_patterns, ccs_manager, args.skip_inject
                )
                
                if analysis['patterns_to_add']:
                    ccs_updates[role_name] = analysis
                    sources = analysis['sources']
                    logger.info(f"  [{ccs_cluster.upper()}] Needs {len(analysis['patterns_to_add'])} patterns:")
                    if sources['inject']:
                        logger.info(f"    From injection: {', '.join(sorted(sources['inject']))}")
                    for cluster, patterns in sources.get('sync', {}).items():
                        logger.info(f"    From {cluster} sync: {', '.join(sorted(patterns))}")
                else:
                    logger.info(f"  [{ccs_cluster.upper()}] Already has all required patterns")
        
        # Check if any updates needed
        total_source_updates = sum(len(updates) for updates in source_updates.values())
        if not total_source_updates and not ccs_updates:
            logger.info("\n✓ No roles need updating. All roles are up to date.")
            print_summary(
                source_updates, ccs_updates, {}, {},
                args.dry_run, args.skip_source, args.skip_ccs,
                inject_patterns, source_clusters, ccs_cluster or "N/A"
            )
            return 0
        
        logger.info(f"\nRoles needing updates:")
        for cluster_name in source_clusters:
            logger.info(f"  {cluster_name.upper()}: {len(source_updates.get(cluster_name, {}))}")
        if ccs_cluster:
            logger.info(f"  {ccs_cluster.upper()} (CCS): {len(ccs_updates)}")
        
        # Generate report
        report_file = args.log_dir / f'role_update_report_{timestamp}.json'
        generate_report(
            source_updates, ccs_updates, report_file,
            inject_patterns, source_clusters, ccs_cluster or "N/A"
        )
        logger.info(f"Report saved to: {report_file}")
        
        # If report-only mode, exit here
        if args.report_only:
            logger.info("\nReport-only mode: exiting without making changes")
            print_summary(
                source_updates, ccs_updates, {}, {},
                True, args.skip_source, args.skip_ccs,
                inject_patterns, source_clusters, ccs_cluster or "N/A"
            )
            return 0
        
        # Perform updates
        logger.info("\n" + "="*70)
        logger.info("UPDATING ROLES")
        logger.info("="*70)
        
        source_results = {cluster: {} for cluster in source_clusters}
        ccs_results = {}
        
        # Update source cluster roles
        if not args.skip_source:
            for cluster_name in source_clusters:
                updates = source_updates.get(cluster_name, {})
                if not updates:
                    continue
                
                logger.info(f"\n--- Updating {cluster_name.upper()} Cluster ---")
                manager = source_managers[cluster_name]
                
                for idx, (role_name, info) in enumerate(updates.items(), 1):
                    logger.info(f"\n[{idx}/{len(updates)}] {role_name}")
                    logger.info(f"  Adding: {', '.join(sorted(info['patterns_to_add']))}")
                    
                    success = update_single_role(
                        manager, role_name, source_all_roles[cluster_name][role_name],
                        info['patterns_to_add'], cluster_name.upper(), args.dry_run
                    )
                    source_results[cluster_name][role_name] = success
                    
                    if not success and not args.continue_on_error:
                        logger.error("Stopping due to error (use --continue-on-error to continue)")
                        break
        
        # Update CCS roles
        if ccs_updates and not args.skip_ccs:
            logger.info(f"\n--- Updating {ccs_cluster.upper()} (CCS) Cluster ---")
            for idx, (role_name, info) in enumerate(ccs_updates.items(), 1):
                logger.info(f"\n[{idx}/{len(ccs_updates)}] {role_name}")
                logger.info(f"  Adding: {', '.join(sorted(info['patterns_to_add']))}")
                
                success = update_single_role(
                    ccs_manager, role_name, ccs_all_roles[role_name],
                    info['patterns_to_add'], ccs_cluster.upper(), args.dry_run
                )
                ccs_results[role_name] = success
                
                if not success and not args.continue_on_error:
                    logger.error("Stopping due to error (use --continue-on-error to continue)")
                    break
        
        # Print summary
        print_summary(
            source_updates, ccs_updates,
            source_results, ccs_results,
            args.dry_run, args.skip_source, args.skip_ccs,
            inject_patterns, source_clusters, ccs_cluster or "N/A"
        )
        
        # Return appropriate exit code
        if args.dry_run:
            return 0
        
        all_source_success = all(
            all(results.values()) if results else True
            for results in source_results.values()
        )
        all_ccs_success = all(ccs_results.values()) if ccs_results else True
        
        return 0 if (all_source_success and all_ccs_success) else 1
        
    except KeyboardInterrupt:
        logger.warning("\nOperation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
