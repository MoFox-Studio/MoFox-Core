# Memory Graph System Design Outline

**Document Version**: 1.0  
**Last Updated**: 2025-11-05  
**Status**: Design Phase Complete, Implementation Phase 1 Complete

---

## Table of Contents

1. [Background and Motivation](#1-background-and-motivation)
2. [System Overview](#2-system-overview)
3. [Core Concepts](#3-core-concepts)
4. [Architecture Design](#4-architecture-design)
5. [Data Models](#5-data-models)
6. [Tool Calling Interface](#6-tool-calling-interface)
7. [Core Algorithms](#7-core-algorithms)
8. [Tech Stack and Dependencies](#8-tech-stack-and-dependencies)
9. [File Structure](#9-file-structure)
10. [Development Plan](#10-development-plan)
11. [Open Questions and Pitfalls](#11-open-questions-and-pitfalls)
12. [Performance Metrics](#12-performance-metrics)
13. [References](#13-references)

---

## 1. Background and Motivation

### The Problem

Current memory system limitations:
- **Single-layer memory**: Only chat history vector search, no relationship graph
- **No persistent semantic relationships**: Each query is independent, no cross-query context
- **Limited context capacity**: Long conversations get truncated, early context lost
- **No reasoning over relationships**: Cannot infer implicit connections between memories
- **Scalability issues**: Linear search becomes slow with millions of chat records

### The Solution: Knowledge Graph-Based Memory

**Memory Graph System** is a three-tier memory architecture that:
1. **Captures semantic relationships**: Build explicit graph edges between memories
2. **Enables relationship reasoning**: Navigate connected memories for richer context
3. **Supports efficient retrieval**: Combine vector search with graph traversal
4. **Scales to millions of memories**: Hierarchical consolidation and caching
5. **Learns over time**: Continuous relationship discovery and refinement

### Why Graph?

```
Traditional Vector Search      Memory Graph System
User Query                      User Query
    ↓                               ↓
Vector Embedding            Vector Embedding
    ↓                               ↓
Similarity Search           Similarity Search (Vector)
    ↓                               ↓
Top-N Memories              Top-N Memories
    (individual)                    ↓
    (return)                  Graph Expansion
                                    ↓
                             Related Memories
                             (via relationships)
                                    ↓
                             Ranked Results
                             (semantic + relational)
```

**Benefits**:
- Captures "why" (relationships) alongside "what" (content)
- One memory can activate related memories through graph traversal
- Enables complex reasoning: "Because X happened, which caused Y, which affected Z"

---

## 2. System Overview

### Three-Tier Memory Architecture

```
┌─────────────────────────────────────────────────┐
│                 User Interaction                 │
└────────────────────┬────────────────────────────┘
                     ↓
        ┌────────────────────────────┐
        │   Perceptual Memory Layer  │
        │  (Temporary Message Blocks)│
        │    - Message buffering     │
        │    - Activation detection  │
        │    - Raw content storage   │
        └────────────┬───────────────┘
                     │ (Transfer on activation)
        ┌────────────▼───────────────┐
        │  Short-Term Memory Layer   │
        │  (Structured & Indexed)    │
        │    - Event extraction      │
        │    - Relationship linking  │
        │    - Importance scoring    │
        └────────────┬───────────────┘
                     │ (Periodic consolidation)
        ┌────────────▼───────────────┐
        │  Long-Term Memory Layer    │
        │  (Graph-Based Persistent)  │
        │    - Memory graph (nodes)  │
        │    - Relationships (edges) │
        │    - Vector embeddings     │
        │    - Semantic consolidation│
        └────────────────────────────┘
```

### Core Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **MemoryGraph** | Core graph structure | NetworkX + ChromaDB |
| **MemoryNode** | Individual memory unit | Data model + Embedding |
| **MemoryEdge** | Relationship connector | Causal/Semantic/Reference |
| **VectorStore** | Semantic search | ChromaDB + Sentence Transformers |
| **GraphStore** | Graph operations | NetworkX |
| **NodeMerger** | Deduplication | Similarity matching |
| **LLM Tools** | Tool calling interface | Function schema |

---

## 3. Core Concepts

### 3.1 Memory Nodes

**What is a Node?**  
A node represents a discrete memory unit with five node types:

| Node Type | Description | Example |
|-----------|-------------|---------|
| **SUBJECT** | The actor/person | "I", "Alice", "User_123" |
| **TOPIC** | The concept/action | "running", "breakfast", "mood" |
| **OBJECT** | The object/target | "5km", "bread", "sad" |
| **ATTRIBUTE** | Property descriptor | "morning", "today", "energetic" |
| **VALUE** | Attribute value | "08:00", "wheat", "very" |

**Node Structure**:
```python
@dataclass
class MemoryNode:
    id: str                          # Unique identifier
    node_type: NodeType              # Type classification
    content: str                     # Text content
    embedding: Optional[List[float]] # Semantic vector
    created_at: datetime
    importance: float                # 0.0 to 1.0
    metadata: Dict[str, Any]         # Additional info
```

### 3.2 Memory Edges

**Relationship Types** (5 edge types):

| Edge Type | Meaning | Example |
|-----------|---------|---------|
| **CORE_RELATION** | Main subject-action relationship | (I) --ate--> (bread) |
| **ATTRIBUTE** | Property of something | (bread) --has quality--> (fresh) |
| **CAUSALITY** | Cause-effect relationship | (insomnia) --caused--> (fatigue) |
| **REFERENCE** | Citation/reference | (my opinion) --about--> (small明's claim) |
| **MEMORY_TYPE** | Memory classification | (event) --is type--> (breakfast) |

**Edge Structure**:
```python
@dataclass
class MemoryEdge:
    id: str                # Unique identifier
    source_id: str         # Source node ID
    target_id: str         # Target node ID
    edge_type: EdgeType    # Type classification
    relation: str          # Relation description
    importance: float      # 0.0 to 1.0
    metadata: Dict[str, Any]
```

### 3.3 Complete Memory

**What is a Memory?**  
A complete memory is a subgraph containing:
- Multiple nodes (subject, topic, object, attributes)
- Edges connecting them (relationships)
- Metadata (importance, timestamp, source)

**Memory Types** (4 types):

| Memory Type | Description | Example |
|------------|-------------|---------|
| **EVENT** | Something that happened | "I ran 5km this morning" |
| **FACT** | Static information | "My favorite color is blue" |
| **RELATION** | Connection between entities | "Alice is my best friend" |
| **OPINION** | Personal perspective | "I think X is unfair" |

**Memory Structure**:
```python
@dataclass
class Memory:
    id: str                              # Unique identifier
    memory_type: MemoryType              # Classification
    subject: str                         # Main subject
    nodes: List[MemoryNode]              # All nodes
    edges: List[MemoryEdge]              # All edges
    importance: float                    # 0.0-1.0
    created_at: datetime
    last_accessed: datetime
    access_count: int                    # Retrieval frequency
    consolidated: bool                   # Has been optimized
    metadata: Dict[str, Any]
```

---

## 4. Architecture Design

### 4.1 Overall Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    LLM Dialogue Engine                       │
│              (Calls memory tools via function call)          │
└─────────────────────────┬──────────────────────────────────┘
                          │
            ┌─────────────┴──────────────┐
            │                            │
    ┌───────▼────────────┐   ┌──────────▼───────────┐
    │  Memory Tools      │   │  Query Tools         │
    │ - create_memory()  │   │ - search_memories()  │
    │ - link_memories()  │   │ - judge_relevance()  │
    └────────┬───────────┘   └──────────┬───────────┘
             │                          │
    ┌────────▼──────────────────────────▼────────┐
    │     Memory Manager (Unified Interface)     │
    │  - Coordinate 3-tier operations            │
    │  - Route to appropriate layer              │
    │  - Handle consolidation                    │
    └────────┬──────────────────────────┬────────┘
             │                          │
    ┌────────▼─────────────┐  ┌────────▼─────────────┐
    │  Write Path          │  │  Read Path           │
    │  - add_memory()      │  │  - retrieve()        │
    │  - link()            │  │  - expand_graph()    │
    │  - stage()           │  │  - rank_results()    │
    └────────┬─────────────┘  └────────┬─────────────┘
             │                         │
    ┌────────▼─────────────────────────▼────────┐
    │        Storage Layer (3 Backends)         │
    ├──────────────────────────────────────────┤
    │ ① Vector Store (ChromaDB)                 │
    │    - Semantic embeddings                  │
    │    - Similarity search                    │
    ├──────────────────────────────────────────┤
    │ ② Graph Store (NetworkX)                  │
    │    - Graph structure                      │
    │    - Traversal algorithms                 │
    ├──────────────────────────────────────────┤
    │ ③ Persistent Store (SQLite + JSON)       │
    │    - Backup and recovery                  │
    │    - Export/import                        │
    └──────────────────────────────────────────┘
```

### 4.2 Module Responsibilities

| Module | Responsibility | Key Files |
|--------|-----------------|-----------|
| **Extractor** | Parse raw input into memory elements | `core/extractor.py` |
| **Builder** | Construct nodes, edges, and memories | `core/builder.py` |
| **Retriever** | Search and expand memories | `core/retriever.py` |
| **NodeMerger** | Deduplicate and merge similar nodes | `core/node_merger.py` |
| **VectorStore** | Manage semantic embeddings | `storage/vector_store.py` |
| **GraphStore** | Manage graph structure | `storage/graph_store.py` |
| **PersistenceManager** | Save/load from disk | `storage/persistence.py` |

---

## 5. Data Models

### 5.1 Enumerations

```python
from enum import Enum

class NodeType(Enum):
    """Five types of memory nodes"""
    SUBJECT = "subject"          # Actor (I, Alice, etc.)
    TOPIC = "topic"              # Concept (running, eating, etc.)
    OBJECT = "object"            # Target (5km, bread, etc.)
    ATTRIBUTE = "attribute"      # Property (morning, busy, etc.)
    VALUE = "value"              # Value (08:00, wheat, etc.)

class MemoryType(Enum):
    """Four types of memories"""
    EVENT = "event"              # Something happened
    FACT = "fact"                # Static information
    RELATION = "relation"        # Entity relationships
    OPINION = "opinion"          # Personal perspective

class EdgeType(Enum):
    """Five types of relationships"""
    CORE_RELATION = "core_relation"      # Main relationship
    ATTRIBUTE = "attribute"              # Property
    CAUSALITY = "causality"              # Cause-effect
    REFERENCE = "reference"              # Citation
    MEMORY_TYPE = "memory_type"          # Classification

class MemoryStatus(Enum):
    """Memory processing status"""
    STAGED = "staged"            # Temporary, not consolidated
    CONSOLIDATED = "consolidated"  # Processed and optimized
    ARCHIVED = "archived"        # Old, rarely accessed
```

### 5.2 Data Classes

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class MemoryNode:
    """Individual memory unit"""
    id: str
    node_type: NodeType
    content: str
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "content": self.content,
            "embedding": self.embedding,
            "created_at": self.created_at.isoformat(),
            "importance": self.importance,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryNode":
        """Deserialize from dictionary"""
        return cls(
            id=data["id"],
            node_type=NodeType(data["node_type"]),
            content=data["content"],
            embedding=data.get("embedding"),
            created_at=datetime.fromisoformat(data["created_at"]),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {})
        )

@dataclass
class MemoryEdge:
    """Relationship between nodes"""
    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    relation: str
    importance: float = 0.6
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "relation": self.relation,
            "importance": self.importance,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEdge":
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data["edge_type"]),
            relation=data["relation"],
            importance=data.get("importance", 0.6),
            metadata=data.get("metadata", {})
        )

@dataclass
class Memory:
    """Complete memory (subgraph)"""
    id: str
    memory_type: MemoryType
    subject: str
    nodes: List[MemoryNode]
    edges: List[MemoryEdge]
    importance: float
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    status: MemoryStatus = MemoryStatus.STAGED
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "subject": self.subject,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "status": self.status.value,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        return cls(
            id=data["id"],
            memory_type=MemoryType(data["memory_type"]),
            subject=data["subject"],
            nodes=[MemoryNode.from_dict(n) for n in data["nodes"]],
            edges=[MemoryEdge.from_dict(e) for e in data["edges"]],
            importance=data["importance"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            access_count=data.get("access_count", 0),
            status=MemoryStatus(data.get("status", "staged")),
            metadata=data.get("metadata", {})
        )

@dataclass
class StagedMemory:
    """Temporary memory awaiting consolidation"""
    memory: Memory
    status: MemoryStatus = MemoryStatus.STAGED
    created_at: datetime = field(default_factory=datetime.now)
    consolidated_at: Optional[datetime] = None
    merge_history: List[str] = field(default_factory=list)
```

---

## 6. Tool Calling Interface

### 6.1 Tool Definition Strategy

**Why separate tool definitions?**
- LLM needs clear, structured interface
- Tools encapsulate domain logic
- Easy to test and version
- Clear contract between LLM and system

### 6.2 Three Core Tools

#### Tool 1: `create_memory()`

**Purpose**: Create a new memory from user input

**Parameters**:
```json
{
  "subject": "string (required)",
  "memory_type": "enum: event|fact|relation|opinion (required)",
  "topic": "string (required)",
  "object": "string (optional)",
  "attributes": "object (optional)",
  "importance": "number 0-1 (default: 0.5)"
}
```

#### Tool 2: `link_memories()`

**Purpose**: Create relationship between two memories

#### Tool 3: `search_memories()`

**Purpose**: Query the memory graph

### 6.3 Complete JSON Schema

[Refer to original document for complete schema]

### 6.4 Tool Calling Examples

#### Example 1: Simple Event

User: "I ate bread for breakfast this morning at 8am"

LLM Tool Calls:
```python
create_memory({
    subject: "I",
    memory_type: "event",
    topic: "ate breakfast",
    object: "bread",
    attributes: {
        time: "2025-11-05 08:00",
        meal: "breakfast"
    },
    importance: 0.3
})
```

#### Example 2: Complex Causality

User: "Last night I couldn't sleep, so today I'm tired and don't feel like working"

[Multiple memory creation with causality linking]

#### Example 3: Opinion/Reference

User: "Tom told me he got full marks, but I think he's bragging"

[Memory creation with reference links]

---

## 7. Core Algorithms

### 7.1 Node Deduplication Algorithm

```
Input: New node N, existing node set NODES
Output: Merged node ID (or new if no match)

1. Compute embedding for N
2. Search ChromaDB for top-k similar nodes (k=5)
3. For each candidate node C:
   a. Compute semantic similarity sim = cosine_similarity(N.embedding, C.embedding)
   b. If sim > 0.95: Direct merge
   c. If 0.85 < sim <= 0.95:
      - Check node type match
      - Check context match (neighbor node similarity > 30%)
      - If match: merge
4. If no merge candidate: create new node
```

### 7.2 Memory Retrieval Algorithm

```
Input: Query Q, expansion depth D
Output: Ranked memory list

Phase 1: Vector Search (Initial Filtering)
1. Convert query Q to embedding
2. Search ChromaDB for top-50 similar nodes
3. Get memories containing these nodes → M_initial

Phase 2: Graph Expansion (Association)
1. Starting from M_initial nodes
2. Execute BFS with depth limit D:
   a. Traverse adjacent edges
   b. Collect adjacent nodes
   c. Record path and distance
   d. Get memories containing new nodes → M_expanded

Phase 3: Ranking and Scoring
1. For each memory M, compute score:
   score = α * semantic_sim + β * importance + γ * (1 / graph_distance) + δ * time_decay + ε * access_frequency
2. Sort by score descending
3. Return top-N memories

Recommended parameters: α=0.4, β=0.2, γ=0.2, δ=0.1, ε=0.1
```

### 7.3 Time Decay Algorithm

```python
def calculate_decay(memory: Memory, current_time: datetime) -> float:
    """Calculate memory time decay factor"""
    days_passed = (current_time - memory.created_at).days
    
    # Different decay rates by memory type
    decay_rate_map = {
        MemoryType.EVENT: 0.05,
        MemoryType.FACT: 0.01,
        MemoryType.RELATION: 0.005,
        MemoryType.OPINION: 0.03
    }
    
    λ = decay_rate_map[memory.memory_type]
    time_factor = math.exp(-λ * days_passed)
    access_bonus = 1 + math.log(1 + memory.access_count)
    
    return memory.importance * time_factor * access_bonus
```

---

## 8. Tech Stack and Dependencies

### 8.1 Core Dependencies

```toml
[tool.poetry.dependencies]
chromadb = "^0.4.0"              # Vector database
sentence-transformers = "*"      # Semantic embeddings
networkx = "^3.2"                # Graph algorithms
pydantic = "^2.0"                # Data validation
```

---

## 9. File Structure

[See original document for complete structure]

---

## 10. Development Plan

### Phase 1: Foundation (Week 1-2) ✅ COMPLETE
### Phase 2: Tool Interface (Week 3-4) 🔄 IN PROGRESS
### Phase 3: Retrieval System (Week 5-6)
### Phase 4: Advanced Features (Week 7-8)
### Phase 5: Integration & Deployment (Week 9-10)

---

## 11. Open Questions and Pitfalls

[See original document for details]

---

## 12. Performance Metrics

[See original document for details]

---

## 13. References

[See original document for details]

---

**Last Updated**: 2025-11-05
