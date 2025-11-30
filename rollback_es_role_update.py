import json
import requests

# Load the backup file
with open('backups/roles_backup_20241129_140530.json', 'r') as f:
    roles = json.load(f)

# Get the role you want to restore
role_name = 'Role1'
role_def = roles[role_name]

# Clean out the metadata fields that shouldn't be in the update
clean_def = {k: v for k, v in role_def.items() 
            if k not in ['_reserved', '_deprecated', '_deprecated_reason']}

# Put it back
response = requests.put(
    f'https://es_cluster_url:9200/_security/role/{role_name}',
    headers={
        'Authorization': f'ApiKey YOUR_API_KEY',
        'Content-Type': 'application/json'
    },
    json=clean_def,
    verify=False  # only if you have SSL issues
)

print(f"Status: {response.status_code}")  # Should be 200
