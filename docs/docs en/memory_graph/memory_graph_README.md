# Memory Graph System

> Multi-tier, multi-modal intelligent memory management framework

## 📚 System Overview

The MoFox memory system is a complete solution inspired by human memory mechanisms, containing three core components:

| Component | Functionality | Purpose |
|-----------|--------------|---------|
| **Three-Tier Memory System** | Perceptual/Short-term/Long-term memory | Handle messages, extract information, persistent storage |
| **Memory Graph System** | Graph-based knowledge base | Manage entity relationships, memory evolution, intelligent retrieval |
| **Interest System** | Dynamic interest calculation | Adjust conversation strategy based on user interests |

## 🎯 Core Features

### Three-Tier Memory System (Unified Memory Manager)
- **Perceptual Layer**: Message block buffering, TopK activation detection
- **Short-Term Layer**: Structured information extraction, intelligent decision merging
- **Long-Term Layer**: Knowledge graph storage, relationship networks, activation propagation

### Memory Graph System
- **Graph Structure Storage**: Node-edge model representing complex memory relationships
- **Semantic Retrieval**: Intelligent memory search based on vector similarity
- **Automatic Integration**: Periodic merging of similar memories, reducing redundancy
- **Intelligent Forgetting**: Automatic memory cleanup based on activation
- **LLM Integration**: Provides tools for AI assistants to call

### Interest System
- **Dynamic Calculation**: Real-time computation of user interests from messages
- **Topic Clustering**: Automatic identification and clustering of interested topics
- **Strategy Impact**: Influences conversation style and content selection

## 🚀 Quick Start

### Option A: Three-Tier Memory System (Recommended for New Users)

Simplest approach, automatically handles message flow and memory evolution:

```toml
# config/bot_config.toml
[three_tier_memory]
enable = true
data_dir = "data/memory_graph/three_tier"
```

```python
from src.memory_graph.unified_manager_singleton import get_unified_manager

# Add message (automatically handled)
unified_mgr = await get_unified_manager()
await unified_mgr.add_message(
    content="What user said",
    sender_id="user_123"
)

# Cross-layer memory search
results = await unified_mgr.search_memories(
    query="Search keyword",
    top_k=5
)
```

**Features**: Automatic transfer, intelligent merging, background maintenance

### Option B: Memory Graph System (Advanced Users)

Direct knowledge graph manipulation, manual memory management:

```toml
# config/bot_config.toml
[memory]
enable = true
data_dir = "data/memory_graph"
```

```python
from src.memory_graph.manager_singleton import get_memory_manager

manager = await get_memory_manager()

# Create memory
memory = await manager.create_memory(
    subject="User",
    memory_type="preference",
    topic="Likes sunny days",
    importance=0.7
)

# Search and operate
memories = await manager.search_memories(query="weather", top_k=5)
node = await manager.create_node(node_type="person", label="username")
edge = await manager.create_edge(
    source_id="node_1",
    target_id="node_2",
    relation_type="knows"
)
```

**Features**: High flexibility, strong control

### Enable Both Systems

Recommended production configuration:

```toml
[three_tier_memory]
enable = true
data_dir = "data/memory_graph/three_tier"

[memory]
enable = true
data_dir = "data/memory_graph"

[interest]
enable = true
```

## ⚙️ Core Configuration

### Three-Tier Memory System
```toml
[three_tier_memory]
enable = true
data_dir = "data/memory_graph/three_tier"
perceptual_max_blocks = 50              # Max perceptual blocks
short_term_max_memories = 100           # Max short-term memories
short_term_transfer_threshold = 0.6     # Transfer importance threshold
long_term_auto_transfer_interval = 600  # Auto transfer interval (seconds)
```

### Memory Graph System
```toml
[memory]
enable = true
data_dir = "data/memory_graph"
search_top_k = 5                        # Retrieval count
consolidation_interval_hours = 1.0      # Consolidation interval
forgetting_activation_threshold = 0.1   # Forgetting threshold
```

### Interest System
```toml
[interest]
enable = true
max_topics = 10                         # Max tracked topics
time_decay_factor = 0.95                # Time decay factor
update_interval = 300                   # Update interval (seconds)
```

**Full Configuration Reference**: 
- 📖 [MEMORY_SYSTEM_OVERVIEW.md](MEMORY_SYSTEM_OVERVIEW.md#configuration) - Detailed configuration
- 📖 [MEMORY_SYSTEM_QUICK_REFERENCE.md](MEMORY_SYSTEM_QUICK_REFERENCE.md) - Quick reference table

## 📚 Documentation Navigation

### Quick Start
- 🔥 **[Quick Reference Card](MEMORY_SYSTEM_QUICK_REFERENCE.md)** - Common commands and quick lookup (5 minutes)

### User Guides
- 📖 **[Complete System Guide](MEMORY_SYSTEM_OVERVIEW.md)** - Three-tier system, memory graph, interest system (30 minutes)
- 📖 **[Three-Tier Memory Guide](three_tier_memory_user_guide.md)** - Perceptual/short-term/long-term workflow (20 minutes)
- 📖 **[Memory Graph Guide](memory_graph_guide.md)** - LLM tools, memory operations, advanced usage (20 minutes)

### Developer Guides
- 🛠️ **[Developer Guide](MEMORY_SYSTEM_DEVELOPER_GUIDE.md)** - Module details, development process, integration schemes (1 hour)
- 🛠️ **[Original API Reference](../src/memory_graph/README.md)** - Code-level API documentation

### Learning Paths

**New Users** (1 hour):
1. Read this README (5 minutes)
2. Check quick reference card (5 minutes)
3. Run quick start examples (10 minutes)
4. Read usage section of complete guide (30 minutes)
5. Integrate memory in plugins (10 minutes)

**Developers** (3 hours):
1. Quick start (1 hour)
2. Read three-tier memory guide (20 minutes)
3. Read memory graph guide (20 minutes)
4. Read developer guide (60 minutes)
5. Implement custom memory types (20 minutes)

**Contributors** (8+ hours):
1. Complete learning of all guides (3 hours)
2. Study source code (2 hours)
3. Understand graph algorithms and vector operations (1 hour)
4. Implement advanced features (2 hours)
5. Write tests and documentation (ongoing)

## ✅ Development Status

### Three-Tier Memory System (Phase 3)
- [x] Perceptual layer implementation
- [x] Short-term layer implementation
- [x] Long-term layer implementation
- [x] Automatic transfer and maintenance
- [x] Integration testing

### Memory Graph System (Phase 2)
- [x] Plugin system integration
- [x] Prompt memory retrieval
- [x] Periodic memory consolidation
- [x] Configuration system support
- [x] Integration testing

### Interest System (Phase 2)
- [x] Basic computation framework
- [x] Component manager
- [x] AFC strategy integration
- [ ] Advanced clustering algorithms
- [ ] Trend analysis

### 📝 Planned Optimizations
- [ ] Vector retrieval performance optimization (FAISS integration)
- [ ] Graph traversal algorithm optimization
- [ ] More LLM tool examples
- [ ] Visualization interface

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Messages/LLM Calls                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│Three-Tier Memory │ │  Memory Graph    │ │  Interest System │
│Unified Manager   │ │  MemoryManager   │ │  InterestMgr     │
└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
         │                    │                    │
    ┌────┴─────────────────┬──┴──────────┬────────┴──────┐
    │                      │             │               │
    ▼                      ▼             ▼               ▼
┌─────────┐        ┌────────────┐  ┌──────────┐   ┌─────────┐
│Perceptual│       │Vector Store│  │Graph Store│   │Interest │
│Layer     │       │            │  │           │   │Calculator
└────┬────┘        └──────┬─────┘  └─────┬────┘   └─────────┘
     │                    │              │
     ▼                    │              │
┌─────────┐               │              │
│Short-Term│              │              │
│Layer     │──────────────┼──────────────┘
└────┬────┘               │
     │                    │
     ▼                    ▼
┌─────────────────────────────────┐
│    Long-Term/Memory Graph       │
│  ├─ Vector Index               │
│  ├─ Graph Database             │
│  └─ Persistent Storage         │
└─────────────────────────────────┘
```

**Three-Tier Memory Flow**:
Message → Perceptual Layer (buffering) → Activation Detection → Short-Term Layer (structured) → Long-Term Layer (graph storage)

## 🎬 Common Scenarios

### Scenario 1: Remember User Preferences
```python
# Automatic handling - three-tier system learns automatically
await unified_manager.add_message(
    content="I like rainy days",
    sender_id="user_123"
)

# Auto-apply on next conversation
memories = await unified_manager.search_memories(
    query="weather preferences"
)
```

### Scenario 2: Record Important Events
```python
# Explicitly create high-importance memory
memory = await memory_manager.create_memory(
    subject="User",
    memory_type="event",
    topic="Attended important meeting",
    content="Detailed information...",
    importance=0.9  # High importance, won't be forgotten
)
```

### Scenario 3: Build Relationship Network
```python
# Create people and relationships
user_node = await memory_manager.create_node(
    node_type="person",
    label="Tom"
)
friend_node = await memory_manager.create_node(
    node_type="person",
    label="Jerry"
)

# Establish relationship
await memory_manager.create_edge(
    source_id=user_node.id,
    target_id=friend_node.id,
    relation_type="knows",
    weight=0.9
)
```

## 🧪 Testing and Monitoring

### Run Tests
```bash
# Integration tests
python -m pytest tests/test_memory_graph_integration.py -v

# Three-tier memory tests
python -m pytest tests/test_three_tier_memory.py -v

# Interest system tests
python -m pytest tests/test_interest_system.py -v
```

### View Statistics
```python
from src.memory_graph.manager_singleton import get_memory_manager

manager = await get_memory_manager()
stats = await manager.get_statistics()
print(f"Total memories: {stats['total_memories']}")
print(f"Total nodes: {stats['total_nodes']}")
print(f"Average activation: {stats['avg_activation']:.2f}")
```

## 🔗 Related Resources

### Core Files
- `src/memory_graph/unified_manager.py` - Three-tier system manager
- `src/memory_graph/manager.py` - Memory graph manager  
- `src/memory_graph/models.py` - Data model definitions
- `src/chat/interest_system/` - Interest system
- `config/bot_config.toml` - Configuration file

### Related Systems
- 📚 [Database System](../docs/database_refactoring_completion.md) - SQLAlchemy architecture
- 📚 [Plugin System](../src/plugin_system/) - LLM tool integration
- 📚 [Chat System](../src/chat/) - AFC strategy integration
- 📚 [Configuration System](../src/config/config.py) - Global configuration management

## 🐛 Troubleshooting

### Common Questions

**Q: Memories not transferring to long-term layer?**
A: Check if short-term memory importance ≥ 0.6, or review `short_term_transfer_threshold` configuration

**Q: Can't find memories in search?**
A: Check similarity threshold settings, try lowering `search_similarity_threshold`

**Q: System using too much disk space?**
A: Enable more aggressive forgetting, adjust `forgetting_activation_threshold`

**More Questions**: See [Complete System Guide](MEMORY_SYSTEM_OVERVIEW.md#faq) or [Quick Reference](MEMORY_SYSTEM_QUICK_REFERENCE.md)

## 🤝 Contributing

Contributions welcome! Submit Issues and PRs.

### Contribution Guide
1. Fork the project
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📞 Getting Help

- 📖 View documentation: [Complete Guide](MEMORY_SYSTEM_OVERVIEW.md)
- 💬 GitHub Issues: Submit bugs or feature requests
- 📧 Contact team: Through official channels

## 📄 License

MIT License - See [LICENSE](../LICENSE) file

---

**MoFox Bot** - Smarter Memory Management  
Updated: December 13, 2025 | Version: 2.0
