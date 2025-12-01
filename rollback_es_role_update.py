#!/usr/bin/env python3
"""
Elasticsearch Role Manager Utilities
Shared functions for managing Elasticsearch roles with remote index patterns
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import requests
from requests.auth import HTTPBasicAuth


class ElasticsearchRoleManager:
    """Manager for Elasticsearch role operations with CCS support"""
    
    def __init__(self, es_url: str, api_key: str, verify_ssl: bool = True):
        """
        Initialize the role manager
        
        Args:
            es_url: Elasticsearch URL (e.g., https://localhost:9200)
            api_key: API key for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self.es_url = es_url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.session = self._create_session()
        self.logger = logging.getLogger(__name__)
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with appropriate headers"""
        session = requests.Session()
        session.headers.update({
            'Authorization': f'ApiKey {self.api_key}',
            'Content-Type': 'application/json'
        })
        session.verify = self.verify_ssl
        return session
    
    def test_connection(self) -> bool:
        """Test connection to Elasticsearch"""
        try:
            response = self.session.get(f'{self.es_url}/')
            response.raise_for_status()
            self.logger.info(f"Successfully connected to Elasticsearch: {response.json().get('version', {}).get('number', 'unknown')}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Elasticsearch: {e}")
            return False
    
    def get_all_roles(self) -> Dict:
        """Retrieve all roles from Elasticsearch"""
        try:
            response = self.session.get(f'{self.es_url}/_security/role')
            response.raise_for_status()
            roles = response.json()
            self.logger.info(f"Retrieved {len(roles)} roles from Elasticsearch")
            return roles
        except Exception as e:
            self.logger.error(f"Failed to retrieve roles: {e}")
            raise
    
    def get_role(self, role_name: str) -> Optional[Dict]:
        """Retrieve a specific role"""
        try:
            response = self.session.get(f'{self.es_url}/_security/role/{role_name}')
            response.raise_for_status()
            return response.json().get(role_name)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            self.logger.error(f"Failed to retrieve role {role_name}: {e}")
            raise
    
    def update_role(self, role_name: str, role_definition: Dict) -> bool:
        """Update a role in Elasticsearch"""
        try:
            # Remove metadata fields that shouldn't be updated
            clean_definition = {k: v for k, v in role_definition.items() 
                              if k not in ['_reserved', '_deprecated', '_deprecated_reason']}
            
            response = self.session.put(
                f'{self.es_url}/_security/role/{role_name}',
                json=clean_definition
            )
            response.raise_for_status()
            self.logger.info(f"Successfully updated role: {role_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update role {role_name}: {e}")
            return False
    
    def backup_roles(self, roles: Dict, backup_dir: Path) -> Path:
        """
        Backup roles to a JSON file
        
        Args:
            roles: Dictionary of roles to backup
            backup_dir: Directory to store backups
            
        Returns:
            Path to the backup file
        """
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'roles_backup_{timestamp}.json'
        
        with open(backup_file, 'w') as f:
            json.dump(roles, f, indent=2)
        
        self.logger.info(f"Backed up {len(roles)} roles to {backup_file}")
        return backup_file
    
    @staticmethod
    def normalize_pattern_for_comparison(pattern: str) -> str:
        """
        Normalize a pattern for comparison purposes
        
        Args:
            pattern: Index pattern (may contain commas)
            
        Returns:
            Normalized pattern (sorted if comma-separated)
            
        Note: This is used for comparison only. Original order is preserved for storage.
        """
        if ',' in pattern:
            # Split, strip, sort, and rejoin for consistent comparison
            parts = [p.strip() for p in pattern.split(',')]
            return ','.join(sorted(parts))
        return pattern.strip()
    
    @staticmethod
    def extract_remote_patterns(role_definition: Dict) -> Set[Tuple[str, str]]:
        """
        Extract remote index patterns from a role definition
        
        Args:
            role_definition: Role definition dictionary
            
        Returns:
            Set of tuples (cluster_prefix, index_pattern)
            e.g., {('prod', 'filebeat-*'), ('qa', 'filebeat-*')}
            
        Note: Handles comma-separated patterns like "prod:traces-apm*,prod:logs-apm*"
              by keeping them together as "traces-apm*,logs-apm*" in ORIGINAL ORDER
        """
        remote_patterns = set()
        
        # Check regular indices section
        for index_entry in role_definition.get('indices', []):
            for name in index_entry.get('names', []):
                if ':' in name:
                    # Check if this is a comma-separated list of remote patterns
                    # e.g., "prod:traces-apm*,prod:logs-apm*,prod:metrics-apm*"
                    if ',' in name:
                        # Parse comma-separated remote patterns
                        parts = name.split(',')
                        cluster_prefix = None
                        local_patterns = []
                        
                        for part in parts:
                            part = part.strip()
                            if ':' in part:
                                # Extract cluster prefix and pattern
                                cluster, pattern = part.split(':', 1)
                                if cluster_prefix is None:
                                    cluster_prefix = cluster
                                elif cluster != cluster_prefix:
                                    # Mixed clusters in comma-separated list - treat separately
                                    cluster_prefix = None
                                    break
                                local_patterns.append(pattern)
                        
                        if cluster_prefix and local_patterns:
                            # All patterns have same cluster prefix
                            # Keep them together as comma-separated IN ORIGINAL ORDER
                            combined_pattern = ','.join(local_patterns)
                            remote_patterns.add((cluster_prefix, combined_pattern))
                        else:
                            # Mixed clusters or parsing failed - treat each separately
                            for part in parts:
                                part = part.strip()
                                if ':' in part:
                                    cluster, pattern = part.split(':', 1)
                                    remote_patterns.add((cluster, pattern))
                    else:
                        # Simple remote pattern like "prod:filebeat-*"
                        parts = name.split(':', 1)
                        if len(parts) == 2:
                            cluster_prefix, pattern = parts
                            remote_patterns.add((cluster_prefix, pattern))
        
        # Check remote_indices section (if exists)
        for index_entry in role_definition.get('remote_indices', []):
            for name in index_entry.get('names', []):
                # Remote indices don't have cluster prefix in the name
                # but have clusters list
                for cluster in index_entry.get('clusters', []):
                    remote_patterns.add((cluster, name))
        
        return remote_patterns
    
    @staticmethod
    def get_base_patterns(remote_patterns: Set[Tuple[str, str]]) -> Set[str]:
        """
        Extract base patterns from remote patterns
        
        Args:
            remote_patterns: Set of (cluster, pattern) tuples
            
        Returns:
            Set of base patterns (without cluster prefix), preserving original order
            
        Note: Preserves original order of comma-separated patterns for readability.
              Uses normalization only for deduplication.
        """
        base_patterns = set()
        seen_normalized = set()  # Track normalized versions to avoid duplicates
        
        for _, pattern in remote_patterns:
            pattern = pattern.strip()
            normalized = ElasticsearchRoleManager.normalize_pattern_for_comparison(pattern)
            
            # Only add if we haven't seen this pattern before (using normalized comparison)
            if normalized not in seen_normalized:
                base_patterns.add(pattern)  # Add original order version
                seen_normalized.add(normalized)
        
        return base_patterns
    
    @staticmethod
    def get_existing_local_patterns(role_definition: Dict) -> Set[str]:
        """
        Get existing local index patterns from a role
        
        Args:
            role_definition: Role definition dictionary
            
        Returns:
            Set of local index patterns in their original form
            
        Note: Returns patterns as they appear in the role (original order preserved)
        """
        local_patterns = set()
        
        for index_entry in role_definition.get('indices', []):
            for name in index_entry.get('names', []):
                # Local patterns don't have cluster prefix (no colon)
                if ':' not in name:
                    local_patterns.add(name.strip())
        
        return local_patterns
    
    @staticmethod
    def get_existing_local_patterns_normalized(role_definition: Dict) -> Set[str]:
        """
        Get existing local index patterns from a role in normalized form for comparison
        
        Args:
            role_definition: Role definition dictionary
            
        Returns:
            Set of normalized local index patterns (for comparison)
            
        Note: Normalizes comma-separated patterns by sorting for consistent comparison
        """
        local_patterns = set()
        
        for index_entry in role_definition.get('indices', []):
            for name in index_entry.get('names', []):
                # Local patterns don't have cluster prefix (no colon)
                if ':' not in name:
                    normalized = ElasticsearchRoleManager.normalize_pattern_for_comparison(name)
                    local_patterns.add(normalized)
        
        return local_patterns
    
    def needs_update(self, role_name: str, role_definition: Dict) -> Tuple[bool, Set[str]]:
        """
        Check if a role needs updating
        
        Args:
            role_name: Name of the role
            role_definition: Role definition dictionary
            
        Returns:
            Tuple of (needs_update, patterns_to_add)
            patterns_to_add preserves original order of comma-separated patterns
        """
        # Skip reserved roles
        if role_definition.get('metadata', {}).get('_reserved'):
            self.logger.debug(f"Skipping reserved role: {role_name}")
            return False, set()
        
        remote_patterns = self.extract_remote_patterns(role_definition)
        
        if not remote_patterns:
            self.logger.debug(f"Role {role_name} has no remote patterns")
            return False, set()
        
        base_patterns = self.get_base_patterns(remote_patterns)
        existing_local_normalized = self.get_existing_local_patterns_normalized(role_definition)
        
        # Compare using normalized patterns, but keep original order for patterns_to_add
        patterns_to_add = set()
        for pattern in base_patterns:
            normalized = self.normalize_pattern_for_comparison(pattern)
            if normalized not in existing_local_normalized:
                patterns_to_add.add(pattern)  # Keep original order
        
        if patterns_to_add:
            self.logger.info(f"Role {role_name} needs {len(patterns_to_add)} patterns added: {patterns_to_add}")
            return True, patterns_to_add
        
        return False, set()
    
    def add_local_patterns_to_role(self, role_definition: Dict, patterns_to_add: Set[str]) -> Dict:
        """
        Add local patterns to a role definition
        
        Args:
            role_definition: Original role definition
            patterns_to_add: Set of patterns to add (may include comma-separated patterns)
            
        Returns:
            Updated role definition
            
        Note: Comma-separated patterns are kept as single entries to match
              the format of remote patterns. Original order is preserved for readability.
        """
        # Create a deep copy to avoid modifying the original
        updated_role = json.loads(json.dumps(role_definition))
        
        if not updated_role.get('indices'):
            updated_role['indices'] = []
        
        # Find an existing entry to use as a template for privileges
        template_entry = None
        for index_entry in updated_role.get('indices', []):
            for name in index_entry.get('names', []):
                if ':' in name:
                    template_entry = index_entry
                    break
            if template_entry:
                break
        
        # If no template found, use a default
        if not template_entry:
            template_entry = {
                'names': [],
                'privileges': ['read', 'view_index_metadata', 'read_cross_cluster'],
                'allow_restricted_indices': False
            }
        
        # Convert set to list preserving insertion order (no sorting)
        patterns_list = list(patterns_to_add)
        
        # Create new entry for local patterns
        new_entry = {
            'names': patterns_list,
            'privileges': template_entry.get('privileges', ['read', 'view_index_metadata']),
            'allow_restricted_indices': template_entry.get('allow_restricted_indices', False)
        }
        
        # Copy field_security if it exists
        if 'field_security' in template_entry:
            new_entry['field_security'] = template_entry['field_security']
        
        # Add the new entry
        updated_role['indices'].append(new_entry)
        
        return updated_role


def setup_logging(log_file: Optional[Path] = None, log_level: str = 'INFO') -> logging.Logger:
    """
    Setup logging configuration
    
    Args:
        log_file: Optional path to log file
        log_level: Logging level
        
    Returns:
        Configured logger
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def generate_update_report(roles_to_update: Dict[str, Set[str]], output_file: Path):
    """
    Generate a report of roles that need updating
    
    Args:
        roles_to_update: Dictionary mapping role names to patterns that need to be added
        output_file: Path to save the report
    """
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_roles': len(roles_to_update),
        'roles': {}
    }
    
    for role_name, patterns in sorted(roles_to_update.items()):
        report['roles'][role_name] = {
            'patterns_to_add': sorted(list(patterns)),
            'pattern_count': len(patterns)
        }
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report
