# Workflow Diagram: Elasticsearch Role Auto-Updater

## High-Level Workflow

```mermaid
flowchart TD
    subgraph INIT["🚀 INITIALIZATION"]
        A[Start] --> B[Parse CLI Arguments]
        B --> C[Load Cluster Config]
        C --> D{Config Valid?}
        D -->|No| E[Exit with Error]
        D -->|Yes| F[Setup Logging]
    end

    subgraph ROLES["📋 ROLE SELECTION"]
        F --> G{Role Source?}
        G -->|--roles| H[Use CLI Role List]
        G -->|--role-file| I[Load from File]
        G -->|--all-matching| J[Find Common Roles]
        H --> K[Validate Role Names]
        I --> K
        J --> K
    end

    subgraph CONNECT["🔌 CLUSTER CONNECTIONS"]
        K --> L[Connect to PROD Cluster]
        L --> M{PROD Connected?}
        M -->|No| E
        M -->|Yes| N[Fetch All PROD Roles]
        N --> O[Connect to CCS Cluster]
        O --> P{CCS Connected?}
        P -->|No| E
        P -->|Yes| Q[Fetch All CCS Roles]
    end

    subgraph BACKUP["💾 BACKUP PHASE"]
        Q --> R{--no-backup?}
        R -->|Yes| S[Skip Backups]
        R -->|No| T[Backup PROD Roles]
        T --> U[Backup CCS Roles]
        U --> S
    end

    subgraph ANALYZE["🔍 ANALYSIS PHASE"]
        S --> V[For Each Role]
        V --> W[Analyze PROD Role]
        W --> X{Missing partial-* or restored-*?}
        X -->|Yes| Y[Mark for PROD Update]
        X -->|No| Z[PROD OK]
        Y --> AA[Analyze CCS Role]
        Z --> AA
        AA --> AB{Missing Patterns?}
        AB -->|Yes| AC[Mark for CCS Update]
        AB -->|No| AD[CCS OK]
        AC --> AE{More Roles?}
        AD --> AE
        AE -->|Yes| V
        AE -->|No| AF[Generate Report]
    end

    subgraph UPDATE["⚡ UPDATE PHASE"]
        AF --> AG{--dry-run or --report-only?}
        AG -->|Yes| AH[Show Preview Only]
        AG -->|No| AI[Update PROD Roles]
        AI --> AJ[Update CCS Roles]
        AJ --> AK[Verify Updates]
    end

    subgraph FINISH["✅ COMPLETION"]
        AH --> AL[Print Summary]
        AK --> AL
        AL --> AM[Exit]
    end

    style INIT fill:#e1f5fe
    style ROLES fill:#f3e5f5
    style CONNECT fill:#fff3e0
    style BACKUP fill:#e8f5e9
    style ANALYZE fill:#fce4ec
    style UPDATE fill:#fff8e1
    style FINISH fill:#e0f2f1
```

## Detailed Analysis Flow

```mermaid
flowchart TD
    subgraph PROD_ANALYSIS["PROD Role Analysis"]
        PA1[Get PROD Role Definition] --> PA2[Extract Existing Patterns]
        PA2 --> PA3{Has 'partial-*'?}
        PA3 -->|No| PA4[Add to injection list]
        PA3 -->|Yes| PA5{Has 'restored-*'?}
        PA4 --> PA5
        PA5 -->|No| PA6[Add to injection list]
        PA5 -->|Yes| PA7[No injection needed]
        PA6 --> PA8[Return patterns to add]
        PA7 --> PA8
    end

    subgraph CCS_ANALYSIS["CCS Role Analysis"]
        CA1[Get CCS Role Definition] --> CA2[Extract Existing Patterns]
        CA2 --> CA3[Check for partial-*, restored-*]
        CA3 --> CA4[Get PROD Role Patterns]
        CA4 --> CA5[Compare PROD vs CCS Patterns]
        CA5 --> CA6[Identify Missing Patterns]
        CA6 --> CA7[Tag Sources: INJ vs SYNC]
        CA7 --> CA8[Return patterns to add with sources]
    end

    PA8 --> RESULT1[PROD Update List]
    CA8 --> RESULT2[CCS Update List]

    style PROD_ANALYSIS fill:#fff3e0
    style CCS_ANALYSIS fill:#e3f2fd
```

## Pattern Addition Strategy

```mermaid
flowchart TD
    subgraph STRATEGY["Pattern Addition to Role"]
        S1[New Patterns to Add] --> S2[Get Role's indices Entries]
        S2 --> S3{Any indices entries?}
        S3 -->|No| S4[Create New Entry with Default Privileges]
        S3 -->|Yes| S5[Score Each Entry]
        
        S5 --> S6["Scoring Formula:<br/>+10 per matching privilege<br/>+5 if local patterns only<br/>+1 per existing pattern"]
        S6 --> S7[Select Highest Score Entry]
        S7 --> S8[Append Patterns to names Array]
        S4 --> S9[Return Updated Role]
        S8 --> S9
    end

    style STRATEGY fill:#f3e5f5
```

## Command Flow Examples

### Example 1: Dry Run with Specific Roles

```mermaid
sequenceDiagram
    participant User
    participant Script
    participant PROD as PROD Cluster
    participant CCS as CCS Cluster

    User->>Script: --roles Role1 --dry-run
    Script->>Script: Load config
    Script->>PROD: Connect & Auth
    PROD-->>Script: ✓ Connected
    Script->>PROD: GET /_security/role
    PROD-->>Script: All roles
    Script->>CCS: Connect & Auth
    CCS-->>Script: ✓ Connected
    Script->>CCS: GET /_security/role
    CCS-->>Script: All roles
    Script->>Script: Analyze Role1
    Script->>Script: Generate Report
    Script-->>User: [DRY RUN] Would add X patterns
    Note over Script: No actual changes made
```

### Example 2: Full Update

```mermaid
sequenceDiagram
    participant User
    participant Script
    participant PROD as PROD Cluster
    participant CCS as CCS Cluster
    participant FS as File System

    User->>Script: --role-file roles.txt
    Script->>FS: Read roles.txt
    FS-->>Script: [Role1, Role2, Role3]
    Script->>PROD: Connect
    Script->>CCS: Connect
    Script->>FS: Create PROD backup
    Script->>FS: Create CCS backup
    
    loop For each role
        Script->>Script: Analyze role
        Script->>PROD: PUT /_security/role/RoleX
        PROD-->>Script: ✓ Updated
        Script->>CCS: PUT /_security/role/RoleX
        CCS-->>Script: ✓ Updated
    end
    
    Script->>FS: Write report JSON
    Script-->>User: Summary: X roles updated
```

## Data Flow

```mermaid
flowchart LR
    subgraph INPUT["📥 Inputs"]
        I1[es_clusters_config.json]
        I2[roles.txt / --roles]
        I3[CLI Options]
    end

    subgraph PROCESS["⚙️ Processing"]
        P1[Connect to Clusters]
        P2[Fetch Roles]
        P3[Analyze Differences]
        P4[Apply Updates]
    end

    subgraph OUTPUT["📤 Outputs"]
        O1[Updated PROD Roles]
        O2[Updated CCS Roles]
        O3[Backup Files]
        O4[Log Files]
        O5[JSON Report]
    end

    I1 --> P1
    I2 --> P2
    I3 --> P3
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> O1
    P4 --> O2
    P3 --> O3
    P4 --> O4
    P4 --> O5

    style INPUT fill:#e3f2fd
    style PROCESS fill:#fff8e1
    style OUTPUT fill:#e8f5e9
```

## State Diagram

```mermaid
stateDiagram-v2
    [*] --> Initializing
    Initializing --> ConfigLoaded: Config Valid
    Initializing --> Error: Invalid Config
    
    ConfigLoaded --> Connecting
    Connecting --> Connected: Both Clusters OK
    Connecting --> Error: Connection Failed
    
    Connected --> FetchingRoles
    FetchingRoles --> Analyzing
    
    Analyzing --> BackingUp: Updates Needed
    Analyzing --> Complete: No Updates Needed
    
    BackingUp --> Updating: Backup Complete
    BackingUp --> Updating: --no-backup
    
    Updating --> Verifying
    Verifying --> Complete: All Verified
    Verifying --> PartialSuccess: Some Failed
    
    Complete --> [*]
    PartialSuccess --> [*]
    Error --> [*]
```

---

## Viewing These Diagrams

These diagrams use [Mermaid](https://mermaid.js.org/) syntax and can be viewed in:

- **GitHub/GitLab**: Renders automatically in markdown files
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **Online**: Paste into [Mermaid Live Editor](https://mermaid.live)
- **Documentation tools**: Notion, Confluence, Obsidian support Mermaid

---

## ASCII Flowchart (For Terminal/Plain Text)

```
┌─────────────────────────────────────────────────────────────────┐
│                         START                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  INITIALIZATION                                                  │
│  ├── Parse CLI arguments                                        │
│  ├── Load cluster config (es_clusters_config.json)              │
│  └── Setup logging                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ROLE SELECTION                                                  │
│  ├── Option A: --roles Role1 Role2 (from CLI)                   │
│  ├── Option B: --role-file roles.txt (from file)                │
│  └── Option C: --all-matching (find common roles)               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  CONNECT TO CLUSTERS                                             │
│  ├── Connect to PROD cluster ──► Fetch all roles                │
│  └── Connect to CCS cluster  ──► Fetch all roles                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  CREATE BACKUPS (unless --no-backup)                             │
│  ├── ./backups/prod/roles_backup_TIMESTAMP.json                 │
│  └── ./backups/ccs/roles_backup_TIMESTAMP.json                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ANALYZE EACH ROLE                                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  FOR EACH ROLE:                                            │ │
│  │  ├── PROD Analysis:                                        │ │
│  │  │   └── Check for partial-*, restored-*                   │ │
│  │  │       └── If missing → Add to PROD update list          │ │
│  │  │                                                         │ │
│  │  └── CCS Analysis:                                         │ │
│  │      ├── Check for partial-*, restored-*                   │ │
│  │      │   └── If missing → Add to CCS update list [INJ]     │ │
│  │      └── Compare with PROD patterns                        │ │
│  │          └── If missing → Add to CCS update list [SYNC]    │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  --dry-run or   │
                    │  --report-only? │
                    └─────────────────┘
                     │              │
                 YES │              │ NO
                     ▼              ▼
         ┌──────────────┐  ┌──────────────────────────────────────┐
         │ Show Preview │  │  APPLY UPDATES                       │
         │ Only         │  │  ├── Update PROD roles               │
         └──────────────┘  │  │   └── PUT /_security/role/{name}  │
                     │     │  └── Update CCS roles                │
                     │     │      └── PUT /_security/role/{name}  │
                     │     └──────────────────────────────────────┘
                     │              │
                     ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GENERATE OUTPUTS                                                │
│  ├── ./logs/role_auto_update_TIMESTAMP.log                      │
│  └── ./logs/role_update_report_TIMESTAMP.json                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PRINT SUMMARY                                                   │
│  ├── PROD: X roles updated (Y successful, Z failed)             │
│  └── CCS:  X roles updated (Y successful, Z failed)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          END                                     │
│  Exit Code: 0 (success) or 1 (failures occurred)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pattern Sync Logic (ASCII)

```
PROD Role: ELK-Analytics-Role          CCS Role: ELK-Analytics-Role
┌─────────────────────────────┐        ┌─────────────────────────────┐
│ indices:                    │        │ indices:                    │
│   - names:                  │        │   - names:                  │
│       - filebeat-*          │        │       - prod:filebeat-*     │
│       - metricbeat-*        │        │       - prod:metricbeat-*   │
│       - partial-*      ✓    │        │       - filebeat-*          │
│       - restored-*     ✓    │        │       - metricbeat-*        │
│       - auditbeat-*         │        │                             │
└─────────────────────────────┘        └─────────────────────────────┘
              │                                      │
              │         ┌──────────────┐             │
              └────────►│   COMPARE    │◄────────────┘
                        └──────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │  CCS Missing:         │
                   │  ├── partial-*  [INJ] │
                   │  ├── restored-* [INJ] │
                   │  └── auditbeat-*[SYNC]│
                   └───────────────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │  UPDATE CCS ROLE      │
                   │  Add 3 patterns       │
                   └───────────────────────┘
```
