# Workflow Diagram: Elasticsearch Role Auto-Updater (Multi-Cluster)

## High-Level Architecture

```mermaid
flowchart TD
    subgraph CONFIG["📁 Configuration"]
        C1[es_clusters_config.json]
        C2["remote_inject_patterns:<br/>partial-*, restored-*"]
        C3["ccs_inject_patterns:<br/>partial-*, restored-*,<br/>elastic-cloud-logs-*"]
    end

    subgraph REMOTE["🏢 Remote Clusters"]
        R1[PROD Cluster]
        R2[QA Cluster]
        R3[DEV Cluster]
        R4[... More Clusters]
    end

    subgraph CCS["🔍 CCS Cluster"]
        CCS1[Cross-Cluster Search]
    end

    C1 --> R1
    C1 --> R2
    C1 --> R3
    C1 --> R4
    C1 --> CCS1

    C2 --> R1
    C2 --> R2
    C2 --> R3
    R1 -->|"Inject: partial-*, restored-*"| R1
    R2 -->|"Inject: partial-*, restored-*"| R2
    R3 -->|"Inject: partial-*, restored-*"| R3

    C3 --> CCS1
    R1 -->|"Sync patterns"| CCS1
    R2 -->|"Sync patterns"| CCS1
    R3 -->|"Sync patterns"| CCS1
    CCS1 -->|"Inject: partial-*, restored-*,<br/>elastic-cloud-logs-*"| CCS1

    style CONFIG fill:#e3f2fd
    style REMOTE fill:#fff3e0
    style CCS fill:#e8f5e9
```

## Inject Patterns Summary

```mermaid
flowchart LR
    subgraph REMOTE_PATTERNS["Remote Clusters (prod, qa, dev)"]
        RP1["partial-*"]
        RP2["restored-*"]
    end

    subgraph CCS_PATTERNS["CCS Cluster"]
        CP1["partial-*"]
        CP2["restored-*"]
        CP3["elastic-cloud-logs-*"]
        CP4["+ synced from remotes"]
    end

    style REMOTE_PATTERNS fill:#fff3e0
    style CCS_PATTERNS fill:#e8f5e9
```

## Main Execution Flow

```mermaid
flowchart TD
    subgraph INIT["🚀 INITIALIZATION"]
        A[Start] --> B[Parse CLI Arguments]
        B --> C[Load Cluster Config]
        C --> D{--list-clusters?}
        D -->|Yes| E[Print Clusters & Exit]
        D -->|No| F[Validate Configuration]
        F --> G{Config Valid?}
        G -->|No| H[Exit with Error]
        G -->|Yes| I[Setup Logging]
    end

    subgraph ROLES["📋 ROLE SELECTION"]
        I --> J{Role Source?}
        J -->|--roles| K[Use CLI Role List]
        J -->|--role-file| L[Load from File]
        J -->|--all-matching| M[Find Common Roles]
        K --> N[Validate Role Names]
        L --> N
        M --> N
    end

    subgraph CONNECT["🔌 CLUSTER CONNECTIONS"]
        N --> O[For Each Remote Cluster]
        O --> P[Connect & Authenticate]
        P --> Q[Fetch All Roles]
        Q --> R{More Remote Clusters?}
        R -->|Yes| O
        R -->|No| S{Skip CCS?}
        S -->|No| T[Connect to CCS Cluster]
        T --> U[Fetch CCS Roles]
        S -->|Yes| V[Continue]
        U --> V
    end

    subgraph BACKUP["💾 BACKUP PHASE"]
        V --> W{--no-backup?}
        W -->|Yes| X[Skip Backups]
        W -->|No| Y[Backup Each Cluster]
        Y --> X
    end

    subgraph ANALYZE["🔍 ANALYSIS PHASE"]
        X --> Z[For Each Role]
        Z --> AA["Analyze Remote Clusters<br/>(partial-*, restored-*)"]
        AA --> AB["Analyze CCS Cluster<br/>(partial-*, restored-*,<br/>elastic-cloud-logs-* + sync)"]
        AB --> AC{More Roles?}
        AC -->|Yes| Z
        AC -->|No| AD[Generate Report]
    end

    subgraph UPDATE["⚡ UPDATE PHASE"]
        AD --> AE{--dry-run?}
        AE -->|Yes| AF[Show Preview Only]
        AE -->|No| AG[Update Remote Clusters]
        AG --> AH[Update CCS Cluster]
        AH --> AI[Verify Updates]
    end

    subgraph FINISH["✅ COMPLETION"]
        AF --> AJ[Print Summary]
        AI --> AJ
        AJ --> AK[Exit]
    end

    style INIT fill:#e1f5fe
    style ROLES fill:#f3e5f5
    style CONNECT fill:#fff3e0
    style BACKUP fill:#e8f5e9
    style ANALYZE fill:#fce4ec
    style UPDATE fill:#fff8e1
    style FINISH fill:#e0f2f1
```

## Remote Cluster Analysis Flow

```mermaid
flowchart TD
    subgraph REMOTE_ANALYSIS["Remote Cluster Analysis (per cluster)"]
        RA1[Get Role Definition] --> RA2[Extract Existing Patterns]
        RA2 --> RA3{Has 'partial-*'?}
        RA3 -->|No| RA4[Add to injection list]
        RA3 -->|Yes| RA5{Has 'restored-*'?}
        RA4 --> RA5
        RA5 -->|No| RA6[Add to injection list]
        RA5 -->|Yes| RA7[No injection needed]
        RA6 --> RA8[Return patterns to add]
        RA7 --> RA8
    end

    RA8 --> RESULT["Remote Update List<br/>(partial-*, restored-*)"]

    style REMOTE_ANALYSIS fill:#fff3e0
```

## CCS Analysis Flow (Multi-Source Sync)

```mermaid
flowchart TD
    subgraph CCS_ANALYSIS["CCS Role Analysis"]
        CA1[Get CCS Role Definition] --> CA2[Extract Existing Patterns]
        
        CA2 --> CA3[Check CCS Inject Patterns]
        CA3 --> CA4{Missing partial-*?}
        CA4 -->|Yes| CA5[Add to list - tag INJ]
        CA4 -->|No| CA6{Missing restored-*?}
        CA5 --> CA6
        CA6 -->|Yes| CA7[Add to list - tag INJ]
        CA6 -->|No| CA8{Missing elastic-cloud-logs-*?}
        CA7 --> CA8
        CA8 -->|Yes| CA9[Add to list - tag INJ]
        CA8 -->|No| CA10[Continue to sync]
        CA9 --> CA10
        
        CA10 --> CA11[Get PROD Role Patterns]
        CA11 --> CA12[Find Missing - tag PROD]
        
        CA12 --> CA13[Get QA Role Patterns]
        CA13 --> CA14[Find Missing - tag QA]
        
        CA14 --> CA15[Get DEV Role Patterns]
        CA15 --> CA16[Find Missing - tag DEV]
        
        CA16 --> CA17[Combine All Missing Patterns]
        CA17 --> CA18[Return with Source Tags]
    end

    CA18 --> RESULT2["CCS Update List<br/>[INJ:3, PROD:1, QA:3, DEV:2]"]

    style CCS_ANALYSIS fill:#e3f2fd
```

## Multi-Cluster Update Sequence

```mermaid
sequenceDiagram
    participant User
    participant Script
    participant PROD
    participant QA
    participant DEV
    participant CCS

    User->>Script: --roles Role1 --remote-clusters prod qa dev --ccs-cluster ccs

    Note over Script: Phase 1: Connect to All Clusters
    Script->>PROD: Connect & Auth
    PROD-->>Script: ✓ Connected
    Script->>PROD: GET /_security/role
    PROD-->>Script: All roles

    Script->>QA: Connect & Auth
    QA-->>Script: ✓ Connected
    Script->>QA: GET /_security/role
    QA-->>Script: All roles

    Script->>DEV: Connect & Auth
    DEV-->>Script: ✓ Connected
    Script->>DEV: GET /_security/role
    DEV-->>Script: All roles

    Script->>CCS: Connect & Auth
    CCS-->>Script: ✓ Connected
    Script->>CCS: GET /_security/role
    CCS-->>Script: All roles

    Note over Script: Phase 2: Create Backups
    Script->>Script: Backup PROD roles
    Script->>Script: Backup QA roles
    Script->>Script: Backup DEV roles
    Script->>Script: Backup CCS roles

    Note over Script: Phase 3: Update Remote Clusters (partial-*, restored-*)
    Script->>Script: Analyze Role1 in PROD
    Script->>PROD: PUT /_security/role/Role1 (+partial-*, +restored-*)
    PROD-->>Script: ✓ Updated

    Script->>Script: Analyze Role1 in QA
    Script->>QA: PUT /_security/role/Role1 (+partial-*, +restored-*)
    QA-->>Script: ✓ Updated

    Script->>Script: Analyze Role1 in DEV
    Script->>DEV: PUT /_security/role/Role1 (+partial-*, +restored-*)
    DEV-->>Script: ✓ Updated

    Note over Script: Phase 4: Update CCS (partial-*, restored-*, elastic-cloud-logs-* + sync)
    Script->>Script: Analyze Role1 in CCS (merge from all remotes)
    Script->>CCS: PUT /_security/role/Role1 (+3 inject, +synced patterns)
    CCS-->>Script: ✓ Updated

    Script-->>User: Summary: All clusters updated
```

## Data Flow Diagram

```mermaid
flowchart LR
    subgraph INPUT["📥 Inputs"]
        I1[es_clusters_config.json]
        I2[roles.txt / --roles]
        I3[CLI Options]
    end

    subgraph CLUSTERS["🌐 Clusters"]
        C1[(PROD)]
        C2[(QA)]
        C3[(DEV)]
        C4[(CCS)]
    end

    subgraph PATTERNS["📋 Inject Patterns"]
        P1["Remote: partial-*, restored-*"]
        P2["CCS: partial-*, restored-*,<br/>elastic-cloud-logs-*"]
    end

    subgraph PROCESS["⚙️ Processing"]
        PR1[Load Config]
        PR2[Connect All]
        PR3[Fetch Roles]
        PR4[Analyze Gaps]
        PR5[Apply Updates]
    end

    subgraph OUTPUT["📤 Outputs"]
        O1[Updated Roles]
        O2[Backup Files]
        O3[Log Files]
        O4[JSON Report]
    end

    I1 --> PR1
    I2 --> PR3
    I3 --> PR1

    PR1 --> PR2
    PR1 --> P1
    PR1 --> P2
    PR2 --> C1
    PR2 --> C2
    PR2 --> C3
    PR2 --> C4
    C1 --> PR3
    C2 --> PR3
    C3 --> PR3
    C4 --> PR3
    PR3 --> PR4
    P1 --> PR4
    P2 --> PR4
    PR4 --> PR5

    PR5 --> O1
    PR3 --> O2
    PR5 --> O3
    PR5 --> O4

    style INPUT fill:#e3f2fd
    style CLUSTERS fill:#fff8e1
    style PATTERNS fill:#f3e5f5
    style PROCESS fill:#fce4ec
    style OUTPUT fill:#e8f5e9
```

## Pattern Sync Logic (Multi-Source)

```mermaid
flowchart TD
    subgraph PROD_ROLE["PROD: ELK-Analytics-Role"]
        P1["indices.names:<br/>- filebeat-*<br/>- metricbeat-*<br/>- partial-* ✓<br/>- restored-* ✓"]
    end

    subgraph QA_ROLE["QA: ELK-Analytics-Role"]
        Q1["indices.names:<br/>- filebeat-*<br/>- qa-custom-*<br/>- qa-logs-*<br/>- partial-* ✓<br/>- restored-* ✓"]
    end

    subgraph DEV_ROLE["DEV: ELK-Analytics-Role"]
        D1["indices.names:<br/>- filebeat-*<br/>- dev-test-*<br/>- partial-* ✓<br/>- restored-* ✓"]
    end

    subgraph CCS_ROLE["CCS: ELK-Analytics-Role (Before)"]
        C1["indices.names:<br/>- prod:filebeat-*<br/>- qa:filebeat-*<br/>- dev:filebeat-*<br/>- filebeat-*<br/>- metricbeat-*"]
    end

    P1 --> COMPARE
    Q1 --> COMPARE
    D1 --> COMPARE
    C1 --> COMPARE

    subgraph COMPARE["🔍 Compare & Identify Missing"]
        CMP1["Missing in CCS:<br/>├── partial-* [INJ]<br/>├── restored-* [INJ]<br/>├── elastic-cloud-logs-* [INJ]<br/>├── qa-custom-* [QA]<br/>├── qa-logs-* [QA]<br/>└── dev-test-* [DEV]"]
    end

    COMPARE --> UPDATE

    subgraph UPDATE["⚡ Update CCS Role"]
        U1["Add 6 patterns"]
    end

    UPDATE --> RESULT

    subgraph RESULT["CCS: ELK-Analytics-Role (After)"]
        R1["indices.names:<br/>- prod:filebeat-*<br/>- qa:filebeat-*<br/>- dev:filebeat-*<br/>- filebeat-*<br/>- metricbeat-*<br/>- partial-* ✨<br/>- restored-* ✨<br/>- elastic-cloud-logs-* ✨<br/>- qa-custom-* ✨<br/>- qa-logs-* ✨<br/>- dev-test-* ✨"]
    end

    style PROD_ROLE fill:#fff3e0
    style QA_ROLE fill:#e8f5e9
    style DEV_ROLE fill:#e3f2fd
    style CCS_ROLE fill:#fce4ec
    style COMPARE fill:#fff8e1
    style UPDATE fill:#f3e5f5
    style RESULT fill:#e0f2f1
```

## State Diagram

```mermaid
stateDiagram-v2
    [*] --> Initializing
    Initializing --> ListingClusters: --list-clusters
    Initializing --> ConfigLoaded: Config Valid
    Initializing --> Error: Invalid Config
    
    ListingClusters --> [*]
    
    ConfigLoaded --> ConnectingRemotes
    ConnectingRemotes --> AllRemotesConnected: All OK
    ConnectingRemotes --> Error: Connection Failed
    
    AllRemotesConnected --> ConnectingCCS: CCS Enabled
    AllRemotesConnected --> FetchingRoles: CCS Skipped
    ConnectingCCS --> FetchingRoles: Connected
    ConnectingCCS --> Error: Connection Failed
    
    FetchingRoles --> Analyzing
    
    Analyzing --> BackingUp: Updates Needed
    Analyzing --> Complete: No Updates Needed
    
    BackingUp --> UpdatingRemotes: Backup Complete
    
    UpdatingRemotes --> UpdatingCCS: Remotes Done
    UpdatingRemotes --> UpdatingCCS: Remotes Skipped
    
    UpdatingCCS --> Verifying: CCS Done
    UpdatingCCS --> Verifying: CCS Skipped
    
    Verifying --> Complete: All Verified
    Verifying --> PartialSuccess: Some Failed
    
    Complete --> [*]
    PartialSuccess --> [*]
    Error --> [*]
```

## Decision Tree: Cluster Selection

```mermaid
flowchart TD
    START[User Command] --> Q1{--skip-remote?}
    
    Q1 -->|Yes| SKIP_REM[Skip Remote Updates]
    Q1 -->|No| Q2{--remote-clusters specified?}
    
    Q2 -->|Yes| USE_CLI[Use CLI clusters]
    Q2 -->|No| Q3{defaults.remote_clusters in config?}
    
    Q3 -->|Yes| USE_DEF[Use config defaults]
    Q3 -->|No| ERROR1[Error: No remotes]
    
    USE_CLI --> Q4{--skip-ccs?}
    USE_DEF --> Q4
    SKIP_REM --> Q4
    
    Q4 -->|Yes| SKIP_CCS[Skip CCS Update]
    Q4 -->|No| Q5{--ccs-cluster specified?}
    
    Q5 -->|Yes| USE_CCS_CLI[Use CLI CCS]
    Q5 -->|No| Q6{defaults.ccs_cluster in config?}
    
    Q6 -->|Yes| USE_CCS_DEF[Use config CCS]
    Q6 -->|No| ERROR2[Error: No CCS]
    
    USE_CCS_CLI --> PROCEED[Proceed with Updates]
    USE_CCS_DEF --> PROCEED
    SKIP_CCS --> PROCEED
    
    style ERROR1 fill:#ffcdd2
    style ERROR2 fill:#ffcdd2
    style PROCEED fill:#c8e6c9
```

---

## ASCII Flowchart (For Terminal/Plain Text)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              START                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  INITIALIZATION                                                          │
│  ├── Parse CLI arguments                                                │
│  ├── Load cluster config (es_clusters_config.json)                      │
│  ├── Load inject patterns:                                              │
│  │   ├── Remote: partial-*, restored-*                                  │
│  │   └── CCS: partial-*, restored-*, elastic-cloud-logs-*               │
│  └── Setup logging                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                        ┌──────────┴──────────┐
                        ▼                     ▼
              ┌──────────────────┐   ┌────────────────────────┐
              │  --list-clusters │   │  Continue with update  │
              │  Print & Exit    │   │                        │
              └──────────────────┘   └────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ROLE SELECTION                                                          │
│  ├── Option A: --roles Role1 Role2 (from CLI)                           │
│  ├── Option B: --role-file roles.txt (from file)                        │
│  └── Option C: --all-matching (find common roles across all clusters)   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CONNECT TO ALL CLUSTERS                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  FOR EACH REMOTE CLUSTER (prod, qa, dev, ...):                     │ │
│  │  ├── Connect and authenticate                                      │ │
│  │  ├── Fetch all roles                                               │ │
│  │  └── Store in memory                                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  FOR CCS CLUSTER (if not --skip-ccs):                              │ │
│  │  ├── Connect and authenticate                                      │ │
│  │  └── Fetch all roles                                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CREATE BACKUPS (unless --no-backup)                                     │
│  ├── ./backups/prod/roles_backup_TIMESTAMP.json                         │
│  ├── ./backups/qa/roles_backup_TIMESTAMP.json                           │
│  ├── ./backups/dev/roles_backup_TIMESTAMP.json                          │
│  └── ./backups/ccs/roles_backup_TIMESTAMP.json                          │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ANALYZE EACH ROLE                                                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  FOR EACH ROLE:                                                    │ │
│  │  ├── REMOTE CLUSTER ANALYSIS (prod, qa, dev):                      │ │
│  │  │   └── Check for partial-*, restored-*                           │ │
│  │  │       └── If missing → Add to cluster's update list             │ │
│  │  │                                                                 │ │
│  │  └── CCS CLUSTER ANALYSIS:                                         │ │
│  │      ├── Check for partial-*, restored-*, elastic-cloud-logs-*     │ │
│  │      │   └── If missing → Add to list [tag: INJ]                   │ │
│  │      ├── Compare with PROD patterns                                │ │
│  │      │   └── If missing → Add to list [tag: PROD]                  │ │
│  │      ├── Compare with QA patterns                                  │ │
│  │      │   └── If missing → Add to list [tag: QA]                    │ │
│  │      └── Compare with DEV patterns                                 │ │
│  │          └── If missing → Add to list [tag: DEV]                   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                    ┌───────────────────────────┐
                    │  --dry-run or             │
                    │  --report-only?           │
                    └───────────────────────────┘
                           │              │
                       YES │              │ NO
                           ▼              ▼
             ┌──────────────────┐  ┌──────────────────────────────────────┐
             │ Show Preview     │  │  APPLY UPDATES                       │
             │ Only             │  │  ├── Update PROD roles (+2 patterns) │
             └──────────────────┘  │  ├── Update QA roles (+2 patterns)   │
                           │       │  ├── Update DEV roles (+2 patterns)  │
                           │       │  └── Update CCS roles (+3 + synced)  │
                           │       └──────────────────────────────────────┘
                           │              │
                           ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GENERATE OUTPUTS                                                        │
│  ├── ./logs/role_auto_update_TIMESTAMP.log                              │
│  └── ./logs/role_update_report_TIMESTAMP.json                           │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PRINT SUMMARY                                                           │
│  ├── PROD:  X roles updated (partial-*, restored-*)                     │
│  ├── QA:    X roles updated (partial-*, restored-*)                     │
│  ├── DEV:   X roles updated (partial-*, restored-*)                     │
│  └── CCS:   X roles updated                                             │
│             [INJ:3, PROD:1, QA:3, DEV:2]                                │
│             (partial-*, restored-*, elastic-cloud-logs-* + synced)      │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                                END                                       │
│  Exit Code: 0 (all success) or 1 (some failures)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Multi-Cluster Pattern Sync (ASCII)

```
REMOTE CLUSTERS                                      CCS CLUSTER
═══════════════                                      ═══════════

PROD Role                    
┌────────────────────┐       
│ Inject:            │       
│  + partial-*       │       
│  + restored-*      │       
│                    │       
│ indices.names:     │       
│  - filebeat-*      │       
│  - metricbeat-*    │───────┐
│  - partial-*  ✓    │       │
│  - restored-* ✓    │       │
└────────────────────┘       │
                             │
QA Role                      │
┌────────────────────┐       │
│ Inject:            │       │
│  + partial-*       │       │
│  + restored-*      │       │
│                    │       │
│ indices.names:     │       │
│  - filebeat-*      │       │
│  - qa-custom-*     │───────┼──────► CCS Role
│  - qa-logs-*       │       │        ┌────────────────────────────┐
│  - partial-*  ✓    │       │        │ Inject:                    │
│  - restored-* ✓    │       │        │  + partial-*               │
└────────────────────┘       │        │  + restored-*              │
                             │        │  + elastic-cloud-logs-*    │
DEV Role                     │        │                            │
┌────────────────────┐       │        │ Sync from remotes:         │
│ Inject:            │       │        │  + metricbeat-* [PROD]     │
│  + partial-*       │       │        │  + qa-custom-* [QA]        │
│  + restored-*      │       │        │  + qa-logs-* [QA]          │
│                    │       │        │  + dev-test-* [DEV]        │
│ indices.names:     │       │        │                            │
│  - filebeat-*      │       │        │ indices.names (AFTER):     │
│  - dev-test-*      │───────┘        │  - prod:filebeat-*         │
│  - partial-*  ✓    │                │  - qa:filebeat-*           │
│  - restored-* ✓    │                │  - dev:filebeat-*          │
└────────────────────┘                │  - filebeat-*              │
                                      │  - metricbeat-*      ✨    │
                                      │  - partial-*         ✨    │
                                      │  - restored-*        ✨    │
                                      │  - elastic-cloud-logs-* ✨ │
                                      │  - qa-custom-*       ✨    │
                                      │  - qa-logs-*         ✨    │
                                      │  - dev-test-*        ✨    │
                                      └────────────────────────────┘

Summary: Remote clusters get 2 patterns each
         CCS gets 3 inject patterns + synced patterns from all remotes
```

---

## Viewing These Diagrams

These diagrams use [Mermaid](https://mermaid.js.org/) syntax and can be viewed in:

- **GitHub/GitLab**: Renders automatically in markdown files
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **Online**: Paste into [Mermaid Live Editor](https://mermaid.live)
- **Documentation tools**: Notion, Confluence, Obsidian support Mermaid

---

## Summary Table

| Cluster Type | Inject Patterns | Sync From |
|--------------|-----------------|-----------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` | N/A |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` | All remote clusters |

| Phase | Remote Clusters | CCS Cluster |
|-------|-----------------|-------------|
| Connect | Each remote individually | CCS cluster |
| Backup | Per-cluster backup | CCS backup |
| Analyze | Check for 2 patterns | Check for 3 patterns + sync from remotes |
| Update | Add missing (max 2) | Add all missing (tagged by source) |
| Report | Per-cluster results | Aggregated with source tags |
