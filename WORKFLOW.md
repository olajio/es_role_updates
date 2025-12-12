# Workflow Diagram: Elasticsearch Role Auto-Updater (Multi-Cluster)

## High-Level Architecture

```mermaid
flowchart TD
    subgraph CONFIG["📁 Configuration"]
        C1[es_clusters_config.json]
        C2["remote_inject_patterns:<br/>partial-*, restored-*"]
        C3["ccs_inject_patterns:<br/>partial-*, restored-*,<br/>elastic-cloud-logs-*"]
        C4["ccs_kibana_privileges:<br/>feature_discover.all<br/>feature_dashboard.all<br/>feature_visualize.all"]
    end

    subgraph REMOTE["🏢 Remote Clusters"]
        R1[PROD Cluster]
        R2[QA Cluster]
        R3[DEV Cluster]
    end

    subgraph CCS["🔍 CCS Cluster"]
        CCS1[Cross-Cluster Search]
        CCS2[Kibana Spaces]
    end

    C1 --> R1
    C1 --> R2
    C1 --> R3
    C1 --> CCS1

    C2 --> R1
    C2 --> R2
    C2 --> R3
    R1 -->|"Inject: partial-*, restored-*"| R1
    R2 -->|"Inject: partial-*, restored-*"| R2
    R3 -->|"Inject: partial-*, restored-*"| R3

    C3 --> CCS1
    C4 --> CCS2
    R1 -->|"Sync patterns"| CCS1
    R2 -->|"Sync patterns"| CCS1
    R3 -->|"Sync patterns"| CCS1
    CCS1 -->|"Inject + Sync"| CCS1
    CCS2 -->|"Grant privileges"| CCS2

    style CONFIG fill:#e3f2fd
    style REMOTE fill:#fff3e0
    style CCS fill:#e8f5e9
```

## Summary Tables

### What Gets Updated

| Cluster Type | Index Patterns | Kibana Privileges |
|--------------|----------------|-------------------|
| **Remote** (prod, qa, dev) | `partial-*`, `restored-*` | None |
| **CCS** | `partial-*`, `restored-*`, `elastic-cloud-logs-*` + synced | `feature_discover.all`, `feature_dashboard.all`, `feature_visualize.all` |

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

    subgraph CONNECT["🔌 CLUSTER CONNECTIONS"]
        I --> J[Connect to Remote Clusters]
        J --> K[Fetch Remote Roles]
        K --> L{Skip CCS?}
        L -->|No| M[Connect to CCS Cluster]
        M --> N[Fetch CCS Roles]
        L -->|Yes| O[Continue]
        N --> O
    end

    subgraph BACKUP["💾 BACKUP PHASE"]
        O --> P{--no-backup?}
        P -->|No| Q[Backup Each Cluster]
        P -->|Yes| R[Skip Backups]
        Q --> R
    end

    subgraph ANALYZE["🔍 ANALYSIS PHASE"]
        R --> S[For Each Role]
        S --> T["Analyze Remote Clusters<br/>(partial-*, restored-*)"]
        T --> U["Analyze CCS Patterns<br/>(inject + sync)"]
        U --> V{Skip Kibana?}
        V -->|No| W["Analyze CCS Kibana<br/>(spaces + privileges)"]
        V -->|Yes| X[Skip Kibana Analysis]
        W --> Y{More Roles?}
        X --> Y
        Y -->|Yes| S
        Y -->|No| Z[Generate Report]
    end

    subgraph UPDATE["⚡ UPDATE PHASE"]
        Z --> AA{--dry-run?}
        AA -->|Yes| AB[Show Preview Only]
        AA -->|No| AC[Update Remote Clusters]
        AC --> AD["Update CCS Cluster<br/>(patterns + Kibana)"]
        AD --> AE[Verify Updates]
    end

    subgraph FINISH["✅ COMPLETION"]
        AB --> AF[Print Summary]
        AE --> AF
        AF --> AG[Exit]
    end

    style INIT fill:#e1f5fe
    style CONNECT fill:#fff3e0
    style BACKUP fill:#e8f5e9
    style ANALYZE fill:#fce4ec
    style UPDATE fill:#fff8e1
    style FINISH fill:#e0f2f1
```

## Kibana Privilege Analysis Flow

```mermaid
flowchart TD
    subgraph KIBANA_ANALYSIS["Kibana Privilege Analysis (CCS Only)"]
        KA1[Get Role Definition] --> KA2[Extract Kibana Spaces]
        KA2 --> KA3{Has Kibana Spaces?}
        KA3 -->|No| KA4[Skip - No Spaces Assigned]
        KA3 -->|Yes| KA5[Get Existing Privileges per Space]
        KA5 --> KA6{Has feature_discover.all?}
        KA6 -->|No| KA7[Add to missing list]
        KA6 -->|Yes| KA8{Has feature_dashboard.all?}
        KA7 --> KA8
        KA8 -->|No| KA9[Add to missing list]
        KA8 -->|Yes| KA10{Has feature_visualize.all?}
        KA9 --> KA10
        KA10 -->|No| KA11[Add to missing list]
        KA10 -->|Yes| KA12[Check Complete]
        KA11 --> KA12
        KA12 --> KA13{Any Missing?}
        KA13 -->|Yes| KA14[Return: needs_update=True]
        KA13 -->|No| KA15[Return: needs_update=False]
    end

    KA4 --> RESULT1["No Kibana Update Needed<br/>(no spaces)"]
    KA14 --> RESULT2["Kibana Update Needed<br/>(spaces + missing privileges)"]
    KA15 --> RESULT3["No Kibana Update Needed<br/>(already has all)"]

    style KIBANA_ANALYSIS fill:#e3f2fd
```

## CCS Role Update Flow (Combined)

```mermaid
flowchart TD
    subgraph CCS_UPDATE["CCS Role Update (Patterns + Kibana)"]
        CU1[Get Original Role] --> CU2{Patterns to Add?}
        CU2 -->|Yes| CU3[Add Index Patterns]
        CU2 -->|No| CU4[Skip Patterns]
        CU3 --> CU5{Kibana Update Needed?}
        CU4 --> CU5
        CU5 -->|Yes| CU6["Add Kibana Application Entry<br/>(privileges + spaces)"]
        CU5 -->|No| CU7[Skip Kibana]
        CU6 --> CU8[Update Role via API]
        CU7 --> CU8
        CU8 --> CU9{Success?}
        CU9 -->|Yes| CU10[✓ Role Updated]
        CU9 -->|No| CU11[✗ Update Failed]
    end

    style CCS_UPDATE fill:#e8f5e9
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

    Note over Script: Phase 1: Connect & Fetch
    Script->>PROD: Connect & Fetch Roles
    Script->>QA: Connect & Fetch Roles
    Script->>DEV: Connect & Fetch Roles
    Script->>CCS: Connect & Fetch Roles

    Note over Script: Phase 2: Create Backups
    Script->>Script: Backup all clusters

    Note over Script: Phase 3: Analyze
    Script->>Script: Analyze Role1 patterns (all clusters)
    Script->>Script: Analyze Role1 Kibana privileges (CCS)

    Note over Script: Phase 4: Update Remote Clusters
    Script->>PROD: PUT Role1 (+partial-*, +restored-*)
    Script->>QA: PUT Role1 (+partial-*, +restored-*)
    Script->>DEV: PUT Role1 (+partial-*, +restored-*)

    Note over Script: Phase 5: Update CCS (Patterns + Kibana)
    Script->>CCS: PUT Role1 (+patterns +Kibana privileges)

    Script-->>User: Summary with results
```

## Kibana Privilege Example

```mermaid
flowchart LR
    subgraph BEFORE["CCS Role BEFORE"]
        B1["applications:"]
        B2["- application: kibana-.kibana<br/>  privileges: [feature_discover.read]<br/>  resources: [space:analytics, space:ops]"]
    end

    subgraph AFTER["CCS Role AFTER"]
        A1["applications:"]
        A2["- application: kibana-.kibana<br/>  privileges: [feature_discover.read]<br/>  resources: [space:analytics, space:ops]"]
        A3["- application: kibana-.kibana<br/>  privileges: [feature_dashboard.all,<br/>    feature_discover.all,<br/>    feature_visualize.all]<br/>  resources: [space:analytics, space:ops]"]
    end

    BEFORE -->|"Script adds<br/>new entry"| AFTER

    style BEFORE fill:#ffcdd2
    style AFTER fill:#c8e6c9
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
│  ├── Load cluster config                                                │
│  ├── Load inject patterns (remote vs CCS)                               │
│  ├── Load Kibana privileges                                             │
│  └── Setup logging                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CONNECT TO ALL CLUSTERS                                                 │
│  ├── Connect to each remote cluster (prod, qa, dev)                     │
│  ├── Fetch all roles from each remote                                   │
│  ├── Connect to CCS cluster                                             │
│  └── Fetch all roles from CCS                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CREATE BACKUPS (per cluster)                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ANALYZE EACH ROLE                                                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  FOR EACH ROLE:                                                    │ │
│  │  ├── REMOTE CLUSTER ANALYSIS:                                      │ │
│  │  │   └── Check for partial-*, restored-*                           │ │
│  │  │                                                                 │ │
│  │  ├── CCS PATTERN ANALYSIS:                                         │ │
│  │  │   ├── Check CCS inject patterns                                 │ │
│  │  │   └── Sync patterns from all remotes                            │ │
│  │  │                                                                 │ │
│  │  └── CCS KIBANA ANALYSIS:                                          │ │
│  │      ├── Extract existing Kibana spaces                            │ │
│  │      ├── Check for feature_discover.all                            │ │
│  │      ├── Check for feature_dashboard.all                           │ │
│  │      └── Check for feature_visualize.all                           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌───────────────────────────┐
                    │  --dry-run?               │
                    └───────────────────────────┘
                           │              │
                       YES │              │ NO
                           ▼              ▼
             ┌──────────────────┐  ┌──────────────────────────────────────┐
             │ Show Preview     │  │  APPLY UPDATES                       │
             │ Only             │  │  ├── Update PROD roles               │
             └──────────────────┘  │  ├── Update QA roles                 │
                           │       │  ├── Update DEV roles                │
                           │       │  └── Update CCS roles:               │
                           │       │      ├── Add patterns                │
                           │       │      └── Add Kibana privileges       │
                           │       └──────────────────────────────────────┘
                           │              │
                           ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PRINT SUMMARY                                                           │
│  ├── PROD:  X roles updated (partial-*, restored-*)                     │
│  ├── QA:    X roles updated (partial-*, restored-*)                     │
│  ├── DEV:   X roles updated (partial-*, restored-*)                     │
│  └── CCS:   X roles updated                                             │
│             ├── Patterns: [INJ:3, PROD:1, QA:2, DEV:1]                  │
│             └── Kibana: +privileges for N spaces                        │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                                END                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Kibana Privileges Deep Dive (ASCII)

```
BEFORE UPDATE                              AFTER UPDATE
═════════════                              ════════════

CCS Role: ELK-Analytics-Role               CCS Role: ELK-Analytics-Role
┌────────────────────────────────┐         ┌────────────────────────────────┐
│ applications:                  │         │ applications:                  │
│ ┌────────────────────────────┐ │         │ ┌────────────────────────────┐ │
│ │ application: kibana-.kibana│ │         │ │ application: kibana-.kibana│ │
│ │ privileges:                │ │         │ │ privileges:                │ │
│ │   - feature_discover.read  │ │         │ │   - feature_discover.read  │ │
│ │   - feature_dashboard.read │ │         │ │   - feature_dashboard.read │ │
│ │ resources:                 │ │         │ │ resources:                 │ │
│ │   - space:analytics        │ │         │ │   - space:analytics        │ │
│ │   - space:operations       │ │         │ │   - space:operations       │ │
│ └────────────────────────────┘ │         │ └────────────────────────────┘ │
│                                │         │ ┌────────────────────────────┐ │
│                                │   ──►   │ │ application: kibana-.kibana│ │
│                                │  ADD    │ │ privileges:                │ │
│                                │  NEW    │ │   - feature_dashboard.all  │◄── NEW
│                                │ ENTRY   │ │   - feature_discover.all   │◄── NEW
│                                │         │ │   - feature_visualize.all  │◄── NEW
│                                │         │ │ resources:                 │ │
│                                │         │ │   - space:analytics        │ │
│                                │         │ │   - space:operations       │ │
│                                │         │ └────────────────────────────┘ │
└────────────────────────────────┘         └────────────────────────────────┘

RESULT: Role now has full Discover, Dashboard, and Visualize access
        for spaces: analytics, operations
        
        Users can now:
        ✓ Generate CSV reports from Discover
        ✓ Generate PDF/PNG reports from Dashboard
        ✓ Full Visualize editing capabilities
```

---

## Decision Tree: Kibana Privilege Update

```
                    ┌─────────────────────────┐
                    │ Analyze CCS Role        │
                    │ for Kibana Privileges   │
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │ Does role have any      │
                    │ Kibana spaces assigned? │
                    └───────────┬─────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                   NO                      YES
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌─────────────────────────┐
        │ SKIP              │   │ Extract all spaces      │
        │ No spaces to      │   │ (space:analytics, etc.) │
        │ grant privileges  │   └───────────┬─────────────┘
        └───────────────────┘               │
                                            ▼
                                ┌─────────────────────────┐
                                │ For each required priv: │
                                │ - feature_discover.all  │
                                │ - feature_dashboard.all │
                                │ - feature_visualize.all │
                                └───────────┬─────────────┘
                                            │
                                            ▼
                                ┌─────────────────────────┐
                                │ Check: Does role have   │
                                │ privilege for ALL spaces│
                                └───────────┬─────────────┘
                                            │
                                ┌───────────┴───────────┐
                                │                       │
                         ALL PRESENT             SOME MISSING
                                │                       │
                                ▼                       ▼
                    ┌───────────────────┐   ┌─────────────────────────┐
                    │ SKIP              │   │ ADD NEW APPLICATION     │
                    │ Already has all   │   │ ENTRY with:             │
                    │ required privs    │   │ - All 3 privileges      │
                    └───────────────────┘   │ - All existing spaces   │
                                            └─────────────────────────┘
```

---

## Summary Table

| Phase | Remote Clusters | CCS Cluster |
|-------|-----------------|-------------|
| **Connect** | Each remote individually | CCS cluster |
| **Backup** | Per-cluster backup | CCS backup |
| **Analyze Patterns** | Check for 2 patterns | Check for 3 patterns + sync |
| **Analyze Kibana** | N/A | Check for 3 privileges per space |
| **Update Patterns** | Add missing (max 2) | Add all missing (tagged by source) |
| **Update Kibana** | N/A | Add new application entry |
| **Report** | Per-cluster results | Patterns + Kibana updates |
