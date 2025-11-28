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
    def extract_remote_patterns(role_definition: Dict) -> Set[Tuple[str, str]]:
        """
        Extract remote index patterns from a role definition
        
        Args:
            role_definition: Role definition dictionary
            
        Returns:
            Set of tuples (cluster_prefix, index_pattern)
            e.g., {('prod', 'filebeat-*'), ('qa', 'filebeat-*')}
        """
        remote_patterns = set()
        
        # Check regular indices section
        for index_entry in role_definition.get('indices', []):
            for name in index_entry.get('names', []):
                if ':' in name:
                    # Split on first colon only
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
            Set of base patterns (without cluster prefix)
        """
        return {pattern for _, pattern in remote_patterns}
    
    @staticmethod
    def get_existing_local_patterns(role_definition: Dict) -> Set[str]:
        """
        Get existing local index patterns from a role
        
        Args:
            role_definition: Role definition dictionary
            
        Returns:
            Set of local index patterns
        """
        local_patterns = set()
        
        for index_entry in role_definition.get('indices', []):
            for name in index_entry.get('names', []):
                # Local patterns don't have cluster prefix
                if ':' not in name:
                    local_patterns.add(name)
        
        return local_patterns
    
    def needs_update(self, role_name: str, role_definition: Dict) -> Tuple[bool, Set[str]]:
        """
        Check if a role needs updating
        
        Args:
            role_name: Name of the role
            role_definition: Role definition dictionary
            
        Returns:
            Tuple of (needs_update, patterns_to_add)
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
        existing_local = self.get_existing_local_patterns(role_definition)
        
        patterns_to_add = base_patterns - existing_local
        
        if patterns_to_add:
            self.logger.info(f"Role {role_name} needs {len(patterns_to_add)} patterns added: {patterns_to_add}")
            return True, patterns_to_add
        
        return False, set()
    
    def add_local_patterns_to_role(self, role_definition: Dict, patterns_to_add: Set[str]) -> Dict:
        """
        Add local patterns to a role definition
        
        Args:
            role_definition: Original role definition
            patterns_to_add: Set of patterns to add
            
        Returns:
            Updated role definition
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
        
        # Create new entry for local patterns
        new_entry = {
            'names': sorted(list(patterns_to_add)),
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
