# 路径评分扩展算法技术规范

**文档版本**: 1.1.0  
**更新日期**: 2025-12-21  
**状态**: 已实现 (Python)  
**目标**: 为 C++/其他语言实现提供完整的算法规范  
**作者**: MoFox Bot Development Team

---

## 目录

1. [算法概述](#1-算法概述)
2. [核心数据结构](#2-核心数据结构)
3. [算法流程详解](#3-算法流程详解)
# Path Scoring Expansion Algorithm Specification

**Document version**: 1.1.0  
**Last updated**: 2025-12-21  
**Status**: Implemented (Python)  
**Goal**: Provide a complete spec for C++/other language implementations  
**Author**: MoFox Bot Development Team

---

## Table of Contents

1. [Algorithm Overview](#1-algorithm-overview)
2. [Core Data Structures](#2-core-data-structures)
3. [Algorithm Flow](#3-algorithm-flow)
4. [Core Formulas](#4-core-formulas)
5. [Performance Tips](#5-performance-tips)
6. [Interfaces](#6-interfaces)
7. [Test Cases](#7-test-cases)
8. [Appendix](#8-appendix)

---

## 1. Algorithm Overview

### 1.1 Background

In large-scale memory graph retrieval, the classic vector-similarity-plus-graph-expansion approach suffers from:

- Recall gaps: vector similarity alone misses structured relations
- Combinatorial explosion: deep traversal causes candidate blow-up
- Quality drop: deeper levels are less relevant

### 1.2 Objectives

Design a graph retrieval algorithm based on path scoring and propagation to achieve:

1. Higher recall by combining semantic similarity and graph structure
2. Controlled expansion via dynamic pruning
3. Quality assurance with depth-aware score decay

### 1.3 Core Idea

```
Initial nodes (TopK from vector search)
    ↓
Path expansion (multi-hop traversal + score propagation)
    ↓
Path merge (merge when endpoints meet)
    ↓
Path pruning (early stop low-score paths)
    ↓
Memory aggregation (map paths to memories)
    ↓
Final scoring (path score + importance + recency)
```

---

## 2. Core Data Structures

### 2.1 Node

> Note: In the Python implementation (`src/memory_graph/models.py`), `MemoryNode` does not store `importance` directly. Node importance usually comes from its parent `Memory` or vector similarity.

```cpp
struct Node {
    string id;              // Node ID (UUID)
    string content;         // Text content
    NodeType type;          // Node type
    vector<float> embedding; // Embedding (384 dims or other)
    map<string, string> metadata; // Metadata

    // Optional
    float importance;       // Node importance [0.0, 1.0] (not used directly in Python)
    time_t created_at;      // Creation timestamp
    map<string, string> metadata;
};

enum NodeType {
    PERSON,
    ENTITY,
    EVENT,
    TOPIC,
    ATTRIBUTE,
    VALUE,
    TIME,
    LOCATION,
    OTHER
};
```

### 2.2 Edge

```cpp
struct Edge {
    string id;              // Edge ID
    string source_id;       // Source node ID
    string target_id;       // Target node ID
    EdgeType type;          // Edge type
    string relation;        // Relation text (for example "likes", "created")
    float importance;       // Edge importance [0.0, 1.0]

    // Optional
    time_t created_at;      // Creation timestamp
    map<string, string> metadata;
};

enum EdgeType {
    REFERENCE,       // Weight 1.3
    ATTRIBUTE,       // Weight 1.2
    HAS_PROPERTY,    // Weight 1.2
    RELATION,        // Weight 0.9
    TEMPORAL,        // Weight 0.7
    CORE_RELATION,   // Weight 1.0
    DEFAULT          // Weight 1.0
};
```

### 2.3 Memory

```cpp
struct Memory {
    string id;              // Memory ID
    vector<Node> nodes;     // Nodes in the memory
    vector<Edge> edges;     // Edges in the memory
    MemoryType type;        // Memory type

    // Scoring fields
    float importance;       // Importance [0.0, 1.0]
    float activation;       // Activation [0.0, 1.0]
    time_t created_at;      // Creation time
    time_t last_accessed_at; // Last access time

    // Optional
    map<string, string> metadata;
};

enum MemoryType {
    FACT,
    OPINION,
    RELATION,
    EVENT,
    OTHER
};
```

### 2.4 Path

```cpp
struct Path {
    vector<string> nodes;   // Ordered node IDs
    vector<string> edges;   // Ordered edge IDs (size = nodes.size() - 1)
    float score;            // Current path score
    int depth;              // Hop count

    // Merge info
    Path* parent;           // Parent path pointer (for merge tracing)
    bool is_merged;         // Whether this is a merged path
    vector<Path*> merged_from; // Paths merged into this one

    // Constructor
    Path(const string& start_node, float initial_score)
        : score(initial_score), depth(0), parent(nullptr), is_merged(false) {
        nodes.push_back(start_node);
    }
};
```

### 2.5 Config

```cpp
struct PathExpansionConfig {
    // Expansion control
    int max_hops = 2;                    // Max depth
    float damping_factor = 0.85;         // Decay factor (PageRank style)
    int max_branches_per_node = 10;      // Max branches per node

    // Merge strategy
    enum MergeStrategy {
        WEIGHTED_GEOMETRIC,  // Geometric mean with bonus
        MAX_BONUS            // Max value with bonus
    };
    MergeStrategy merge_strategy = WEIGHTED_GEOMETRIC;

    // Pruning
    float pruning_threshold = 0.9;       // Path similarity threshold

    // Edge type weights
    map<EdgeType, float> edge_type_weights = {
        {REFERENCE, 1.3},
        {ATTRIBUTE, 1.2},
        {HAS_PROPERTY, 1.2},
        {RELATION, 0.9},
        {TEMPORAL, 0.7},
        {DEFAULT, 1.0}
    };

    // Final scoring weights
    struct FinalScoringWeights {
        float path_score = 0.50;
        float importance = 0.30;
        float recency = 0.20;
    } final_scoring_weights;
};
```

---

## 3. Algorithm Flow

### 3.1 Overview

```
┌─────────────────────────────────────────┐
│ Input: initial nodes (TopK from vector) │
│        [(node_id, score, metadata)...]  │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step 1: Init path queue                 │
│  - Create a path for each initial node  │
│  - Set initial score and depth          │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step 2: Multi-hop expansion (main loop) │
│  for hop in 1..max_hops:                │
│    ├─ 2.1 Get neighbor edges            │
│    ├─ 2.2 Compute edge weight           │
│    ├─ 2.3 Compute node score            │
│    ├─ 2.4 Propagate path score          │
│    ├─ 2.5 Try merging paths             │
│    ├─ 2.6 Prune low-score paths         │
│    └─ 2.7 Control branching             │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step 3: Extract leaf paths              │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step 4: Map paths to memories           │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Step 5: Final scoring and sorting       │
└─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Output: sorted memories (TopK)          │
└─────────────────────────────────────────┘
```

### 3.2 Step 1: Initialize Paths

```python
def initialize_paths(initial_nodes):
    active_paths = []
    best_score_to_node = {}  # Best score seen per node

    for (node_id, score, metadata) in initial_nodes:
        path = Path(node_id, score)
        active_paths.append(path)
        best_score_to_node[node_id] = score

    return active_paths, best_score_to_node
```

Key points:
- `best_score_to_node` is used to deduplicate during merges
- Initial scores come from vector similarity

### 3.3 Step 2: Multi-hop Expansion

```python
def expand_paths_multi_hop(active_paths, config, graph_store):
    for hop in range(1, config.max_hops + 1):
        new_paths = []
        merge_count = 0
        prune_count = 0
        branch_count = 0

        for path in active_paths:
            current_node_id = path.nodes[-1]

            neighbor_edges = get_sorted_neighbor_edges(current_node_id, graph_store)

            max_branches = calculate_max_branches(path.score, config)

            for edge in neighbor_edges[:max_branches]:
                next_node_id = edge.target_id

                if next_node_id in path.nodes:
                    continue

                edge_weight = get_edge_weight(edge, config)
                node_score = get_node_score(next_node_id, query_embedding)

                new_score = calculate_path_score(
                    old_score=path.score,
                    edge_weight=edge_weight,
                    node_score=node_score,
                    depth=hop,
                    damping=config.damping_factor
                )

                should_merge, existing_path = try_merge_paths(
                    next_node_id, new_score, best_score_to_node, config
                )

                if should_merge:
                    merged_path = merge_two_paths(path, existing_path, new_score, config)
                    new_paths.append(merged_path)
                    merge_count += 1
                else:
                    new_path = extend_path(path, next_node_id, edge.id, new_score, hop)
                    new_paths.append(new_path)
                    best_score_to_node[next_node_id] = max(
                        best_score_to_node.get(next_node_id, 0.0), new_score
                    )
                    branch_count += 1

        new_paths, prune_count = prune_low_score_paths(new_paths, config)
        active_paths = new_paths

        log(
            f"Hop {hop}/{config.max_hops}: {len(active_paths)} paths, "
            f"{branch_count} branches, {merge_count} merges, {prune_count} pruned"
        )

    return active_paths
```

### 3.4 Step 3: Extract Leaf Paths

```python
def extract_leaf_paths(all_paths, config):
    endpoint_nodes = set(path.nodes[-1] for path in all_paths)
    startpoint_nodes = set(path.nodes[0] for path in all_paths if path.depth > 0)

    leaf_paths = []
    for path in all_paths:
        if path.nodes[-1] not in startpoint_nodes or path.depth == config.max_hops:
            leaf_paths.append(path)

    return leaf_paths
```

### 3.5 Step 4: Map Paths To Memories

```python
def map_paths_to_memories(leaf_paths, graph_store):
    memory_paths = {}  # { memory_id: (Memory, [Path...]) }

    for path in leaf_paths:
        for node_id in path.nodes:
            memory_ids = graph_store.get_memories_by_node(node_id)

            for memory_id in memory_ids:
                if memory_id not in memory_paths:
                    memory = graph_store.get_memory_by_id(memory_id)
                    memory_paths[memory_id] = (memory, [])

                memory_paths[memory_id][1].append(path)

    return memory_paths
```

### 3.6 Step 5: Final Scoring

```python
def final_scoring(memory_paths, config, current_time):
    scored_memories = []

    for memory_id, (memory, paths) in memory_paths.items():
        path_score = aggregate_path_scores(paths)
        importance_score = memory.importance
        recency_score = calculate_recency(memory, current_time)

        weights = config.final_scoring_weights
        final_score = (
            path_score * weights.path_score
            + importance_score * weights.importance
            + recency_score * weights.recency
        )

        scored_memories.append((memory, final_score, paths))

    scored_memories.sort(key=lambda x: x[1], reverse=True)
    return scored_memories
```

---

## 4. Core Formulas

### 4.1 Path Score Propagation

```
new_score = old_score × edge_weight × decay + node_score × (1 - decay)

decay = damping_factor ^ depth

Parameters:
  old_score: previous hop path score
  edge_weight: edge weight (type and importance)
  decay: exponential decay by depth
  node_score: new node quality (vector similarity)
  damping_factor: decay coefficient (default 0.85)
  depth: current hop (1, 2, ...)
```

Explanation:
1. Propagation term (`old_score × edge_weight × decay`): carries prior score, decays with depth
2. Injection term (`node_score × (1 - decay)`): injects freshness from the new node

Example:

```
old_score = 0.8
edge_weight = 1.2 (ATTRIBUTE)
node_score = 0.6
depth = 1
damping_factor = 0.85

decay = 0.85
propagated = 0.8 × 1.2 × 0.85 = 0.816
fresh = 0.6 × 0.15 = 0.09
new_score = 0.906
```

### 4.2 Edge Weight

```cpp
float get_edge_weight(const Edge& edge, const Config& config) {
    float base_weight = edge.importance;
    float type_weight = config.edge_type_weights.at(edge.type);
    return base_weight * type_weight;
}
```

| Edge type   | Weight | Notes                  |
| ----------- | ------ | ---------------------- |
| REFERENCE   | 1.3    | Strong reference       |
| ATTRIBUTE   | 1.2    | Attribute relation     |
| HAS_PROPERTY| 1.2    | Has-property relation  |
| CORE_RELATION| 1.0   | Core relation          |
| RELATION    | 0.9    | General relation       |
| TEMPORAL    | 0.7    | Temporal relation      |
| DEFAULT     | 1.0    | Default weight         |

### 4.3 Node Score

```cpp
float get_node_score(const string& node_id, const vector<float>& query_embedding,
                     VectorStore& vector_store) {
    auto node_data = vector_store.get_node_by_id(node_id);
    if (!node_data.has_value()) {
        return 0.3;  // Low score when embedding is missing
    }

    vector<float> node_embedding = node_data->embedding;
    float similarity = cosine_similarity(query_embedding, node_embedding);
    return std::max(0.0f, std::min(1.0f, similarity));
}
```

### 4.4 Dynamic Branch Count

```cpp
int calculate_max_branches(float path_score, const Config& config) {
    float ratio = 0.5f + 0.5f * path_score;
    int branches = static_cast<int>(config.max_branches_per_node * ratio);
    return std::max(1, branches);
}
```

| Path score | Branch ratio | Branches (max=10) |
| ---------- | ------------ | ----------------- |
| 1.0        | 100%         | 10                |
| 0.8        | 90%          | 9                 |
| 0.6        | 80%          | 8                 |
| 0.4        | 70%          | 7                 |
| 0.2        | 60%          | 6                 |
| 0.0        | 50%          | 5                 |

### 4.5 Path Merge

Strategy 1: Weighted geometric mean

```cpp
float merge_score_weighted_geometric(float score1, float score2) {
    float geometric_mean = std::sqrt(score1 * score2);
    return geometric_mean * 1.2f;
}
```

Strategy 2: Max bonus

```cpp
float merge_score_max_bonus(float score1, float score2) {
    float max_score = std::max(score1, score2);
    return max_score * 1.3f;
}
```

### 4.6 Aggregate Path Scores

```cpp
float aggregate_path_scores(const vector<Path*>& paths) {
    if (paths.empty()) return 0.0f;

    vector<Path*> sorted_paths = paths;
    std::sort(sorted_paths.begin(), sorted_paths.end(),
              [](Path* a, Path* b) { return a->score > b->score; });

    float total_weight = 0.0f;
    float weighted_sum = 0.0f;

    for (size_t i = 0; i < sorted_paths.size(); ++i) {
        float weight = 1.0f / (i + 1);  // Rank decay: 1.0, 0.5, 0.33...
        weighted_sum += sorted_paths[i]->score * weight;
        total_weight += weight;
    }

    return weighted_sum / total_weight;
}
```

### 4.7 Recency Score

```cpp
float calculate_recency(const Memory& memory, time_t current_time) {
    time_t created_delta = current_time - memory.created_at;
    time_t accessed_delta = current_time - memory.last_accessed_at;

    float creation_decay = std::exp(-created_delta / (30.0 * 86400));
    float access_decay = std::exp(-accessed_delta / (7.0 * 86400));

    return 0.4f * creation_decay + 0.6f * access_decay;
}
```

### 4.8 Preferred Node Types Bonus

Supports explicit LLM preference for certain node types (for example EVENT or ENTITY).

```cpp
float apply_type_bonus(float base_score, const Node& node, const vector<NodeType>& preferred_types) {
    if (preferred_types.empty()) return base_score;

    bool is_match = std::find(preferred_types.begin(), preferred_types.end(), node.type) != preferred_types.end();

    if (is_match) {
        return base_score + (base_score * 0.2f);
    }

    return base_score;
}
```

Example use cases:
- User asks "What happened?" -> `preferred_types=[EVENT]`
- User asks "Tell me about Alice" -> `preferred_types=[PERSON, ENTITY]`

---

## 5. Performance Tips

### 5.1 Bottlenecks (Python profiling)

| Operation                | Time share | Priority |
| ------------------------ | ---------- | -------- |
| Vector similarity        | 35%        | High     |
| Graph traversal          | 25%        | High     |
| Path merge decisions     | 15%        | Medium   |
| Path object creation     | 10%        | Medium   |
| Final sorting            | 8%         | Medium   |
| Other                    | 7%         | Low      |

### 5.2 Optimizations

#### Vector similarity

Method 1: SIMD

```cpp
// AVX2/AVX512 cosine similarity
float cosine_similarity_simd(const float* vec1, const float* vec2, size_t dim) {
    #ifdef __AVX2__
    __m256 sum = _mm256_setzero_ps();
    __m256 norm1 = _mm256_setzero_ps();
    __m256 norm2 = _mm256_setzero_ps();

    for (size_t i = 0; i < dim; i += 8) {
        __m256 v1 = _mm256_loadu_ps(&vec1[i]);
        __m256 v2 = _mm256_loadu_ps(&vec2[i]);

        sum = _mm256_fmadd_ps(v1, v2, sum);
        norm1 = _mm256_fmadd_ps(v1, v1, norm1);
        norm2 = _mm256_fmadd_ps(v2, v2, norm2);
    }

    float dot = horizontal_sum(sum);
    float n1 = std::sqrt(horizontal_sum(norm1));
    float n2 = std::sqrt(horizontal_sum(norm2));

    return dot / (n1 * n2);
    #else
    // Fallback implementation
    #endif
}
```

Method 2: Product quantization

```cpp
struct QuantizedVector {
    vector<uint8_t> codes;
    vector<float> codebook;

    float approximate_similarity(const QuantizedVector& other) const;
};
```

#### Graph traversal

Use a compact adjacency layout plus caching:

```cpp
struct CompactGraph {
    unordered_map<string, int> node_index;
    vector<int> edge_offsets;
    vector<int> edge_targets;
    vector<Edge> edge_data;

    span<Edge> get_neighbors(const string& node_id) const {
        int idx = node_index.at(node_id);
        int start = edge_offsets[idx];
        int end = edge_offsets[idx + 1];
        return span<Edge>(&edge_data[start], end - start);
    }
};
```

#### Path object pool

```cpp
class PathPool {
public:
    Path* allocate() {
        if (free_list.empty()) {
            return new Path();
        }
        Path* path = free_list.back();
        free_list.pop_back();
        return path;
    }

    void deallocate(Path* path) {
        path->reset();
        free_list.push_back(path);
    }

private:
    vector<Path*> free_list;
};
```

#### Parallelism

```cpp
vector<Path*> expand_paths_parallel(const vector<Path*>& active_paths,
                                    const Config& config,
                                    int num_threads = 8) {
    vector<vector<Path*>> thread_results(num_threads);

    #pragma omp parallel for num_threads(num_threads)
    for (int i = 0; i < active_paths.size(); ++i) {
        int tid = omp_get_thread_num();
        auto new_paths = expand_single_path(active_paths[i], config);
        thread_results[tid].insert(thread_results[tid].end(),
                                   new_paths.begin(), new_paths.end());
    }

    vector<Path*> result;
    for (const auto& thread_result : thread_results) {
        result.insert(result.end(), thread_result.begin(), thread_result.end());
    }

    return result;
}
```

### 5.3 Memory Optimizations

#### Compact layout

```cpp
struct CompactPath {
    vector<int> node_indices;
    vector<int> edge_indices;

    float score;
    uint8_t depth;
    uint8_t flags;
};
```

#### Stage-wise release

```cpp
for (int hop = 1; hop <= config.max_hops; ++hop) {
    auto new_paths = expand_one_hop(active_paths, config);

    for (auto* path : active_paths) {
        if (!path->is_merged) {
            delete path;
        }
    }

    active_paths = new_paths;
}
```

### 5.4 Python Implementation Notes

Implemented in `src/memory_graph/utils/path_expansion.py`:

1. Batch node scoring (`_batch_get_node_scores`) with matrix ops; heavy compute moved to a thread pool.
2. Neighbor edge cache (`_neighbor_cache`) during a single query lifecycle.
3. Early stopping by monitoring path growth rate (`early_stop_growth_threshold`, default 10%).
4. Coarse ranking to filter low-quality memories before expensive scoring (`max_candidate_memories`).
5. Type preloading for node types before final scoring.

---

## 6. Interfaces

### 6.1 Main API

```cpp
vector<tuple<Memory, float, vector<Path*>>> expand_with_path_scoring(
    const vector<tuple<string, float, map<string, string>>>& initial_nodes,
    const vector<float>& query_embedding,
    int top_k,
    const PathExpansionConfig& config,
    GraphStore& graph_store,
    VectorStore& vector_store
);
```

### 6.2 Graph Store

```cpp
class GraphStore {
public:
    virtual vector<Edge> get_outgoing_edges(const string& node_id) const = 0;
    virtual vector<string> get_memories_by_node(const string& node_id) const = 0;
    virtual Memory get_memory_by_id(const string& memory_id) const = 0;
};
```

### 6.3 Vector Store

```cpp
class VectorStore {
public:
    virtual optional<NodeData> get_node_by_id(const string& node_id) const = 0;

    struct NodeData {
        string id;
        vector<float> embedding;
        map<string, string> metadata;
    };
};
```

---

## 7. Test Cases

### 7.1 Unit Tests

#### Test 1: Score Propagation

```cpp
TEST(PathExpansion, ScorePropagation) {
    float old_score = 0.8;
    float edge_weight = 1.2;
    float node_score = 0.6;
    int depth = 1;
    float damping = 0.85;

    float new_score = calculate_path_score(old_score, edge_weight, node_score, depth, damping);

    float expected = 0.8 * 1.2 * 0.85 + 0.6 * (1 - 0.85);
    EXPECT_NEAR(new_score, expected, 0.001);
    EXPECT_NEAR(new_score, 0.906, 0.001);
}
```

#### Test 2: Path Merge

```cpp
TEST(PathExpansion, PathMerge) {
    Path path1({"A", "B", "C"}, {}, 0.8, 2);
    Path path2({"D", "E", "C"}, {}, 0.7, 2);

    PathExpansionConfig config;
    config.merge_strategy = WEIGHTED_GEOMETRIC;

    Path* merged = merge_two_paths(&path1, &path2, 0.9, config);

    EXPECT_TRUE(merged->is_merged);
    EXPECT_EQ(merged->merged_from.size(), 2);
    EXPECT_NEAR(merged->score, sqrt(0.8 * 0.7) * 1.2, 0.001);
}
```

#### Test 3: Dynamic Branching

```cpp
TEST(PathExpansion, DynamicBranches) {
    PathExpansionConfig config;
    config.max_branches_per_node = 10;

    EXPECT_EQ(calculate_max_branches(1.0, config), 10);
    EXPECT_EQ(calculate_max_branches(0.8, config), 9);
    EXPECT_EQ(calculate_max_branches(0.5, config), 7);
    EXPECT_EQ(calculate_max_branches(0.0, config), 5);
}
```

### 7.2 Integration Test

```cpp
TEST(PathExpansion, SmallGraphRetrieval) {
    GraphStore graph = build_test_graph();
    VectorStore vectors = build_test_vectors();

    vector<tuple<string, float, map<string, string>>> initial_nodes = {
        {"A", 0.9, {}},
        {"B", 0.7, {}}
    };

    vector<float> query_embedding = generate_random_vector(384);

    PathExpansionConfig config;
    config.max_hops = 2;

    auto results = expand_with_path_scoring(
        initial_nodes, query_embedding, 5, config, graph, vectors
    );

    EXPECT_GT(results.size(), 0);
    EXPECT_LE(results.size(), 5);

    for (size_t i = 1; i < results.size(); ++i) {
        EXPECT_GE(get<1>(results[i-1]), get<1>(results[i]));
    }
}
```

### 7.3 Benchmark

```cpp
BENCHMARK(PathExpansion, LargeGraph) {
    GraphStore graph = load_large_graph("test_data/large_graph.bin");
    VectorStore vectors = load_large_vectors("test_data/large_vectors.bin");

    auto initial_nodes = get_top_k_nodes(vectors, query_embedding, 50);

    PathExpansionConfig config;
    config.max_hops = 2;
    config.max_branches_per_node = 10;

    auto start = chrono::high_resolution_clock::now();

    auto results = expand_with_path_scoring(
        initial_nodes, query_embedding, 20, config, graph, vectors
    );

    auto end = chrono::high_resolution_clock::now();
    auto duration = chrono::duration_cast<chrono::milliseconds>(end - start);

    EXPECT_LT(duration.count(), 500);

    cout << "Execution time: " << duration.count() << " ms" << endl;
    cout << "Throughput: " << (initial_nodes.size() / (duration.count() / 1000.0))
         << " nodes/sec" << endl;
}
```

---

## 8. Appendix

### 8.1 Python Reference

- Core algorithm: `src/memory_graph/utils/path_expansion.py`
- Data models: `src/memory_graph/models.py`
- Config: `src/config/official_configs.py`

### 8.2 Math Symbols

| Symbol | Meaning |
| ------ | ------- |
| $s_{old}$ | Previous hop score |
| $w_e$ | Edge weight |
| $s_n$ | Node score |
| $d$ | Depth (hop) |
| $\alpha$ | Damping factor |
| $\delta$ | Decay value $= \alpha^d$ |
| $s_{new}$ | New path score |

$$
s_{new} = s_{old} \times w_e \times \alpha^d + s_n \times (1 - \alpha^d)
$$

### 8.3 Complexity

- Worst case: $O(N \times B^H)$
  - $N$: initial nodes
  - $B$: average branching
  - $H$: max hops

- Practical with pruning: $O(N \times B \times H)$

- Space: $O(P \times H)$ where $P$ is total paths

### 8.4 Tuning Tips

| Param | Default | Guidance |
| ----- | ------- | -------- |
| max_hops | 2 | 1: fast/low recall; 2: balanced; 3+: higher recall slower |
| damping_factor | 0.85 | 0.9: favor propagation; 0.8: favor node quality |
| max_branches | 10 | 5: faster; 10: balanced; 15+: more recall |
| pruning_threshold | 0.9 | 0.85: aggressive pruning; 0.95: keep more paths |
| path_score_weight | 0.50 | Increase to emphasize path quality |

### 8.5 FAQ

Q1: Why exponential decay instead of linear?

A: Exponential decay $\alpha^d$ better models information spread: hop1 85%, hop2 72%, hop3 61%. Linear decay keeps far nodes too influential.

Q2: Path merge condition?

```cpp
bool should_merge = (path1.nodes.back() == path2.nodes.back()) &&
                    (abs(path1.score - path2.score) < 0.1);
```

Q3: Directed vs undirected graphs?

Current implementation assumes directed. For undirected, include incoming edges:

```cpp
vector<Edge> edges = graph.get_outgoing_edges(node_id);
vector<Edge> incoming = graph.get_incoming_edges(node_id);
edges.insert(edges.end(), incoming.begin(), incoming.end());
```

Q4: Memory estimate?

```
Paths: 50 * 10 * 10 = 5000
Per path: ~100 bytes
Total: ~500 KB (can be reduced to <100 KB with optimizations)
```

---

## 9. Implementation Checklist

### 9.1 Data Structures
- [ ] Node struct (id, content, type, embedding, metadata)
- [ ] Edge struct (id, source_id, target_id, type, importance)
- [ ] Memory struct (id, nodes, edges, importance, timestamps)
- [ ] Path struct (nodes, edges, score, depth, merge info)
- [ ] PathExpansionConfig struct (all parameters)

### 9.2 Core Algorithm
- [ ] Path score propagation (decay + edge weight + node score)
- [ ] Dynamic branching
- [ ] Path merge logic (geometric mean / max bonus)
- [ ] Pruning logic
- [ ] Multi-hop loop
- [ ] Leaf extraction
- [ ] Path-to-memory mapping
- [ ] Final scoring (path + importance + recency)

### 9.3 Helpers
- [ ] Cosine similarity (SIMD optional)
- [ ] Edge weight calculation
- [ ] Node score calculation
- [ ] Path score aggregation
- [ ] Recency calculation

### 9.4 Interfaces
- [ ] GraphStore (get_outgoing_edges, get_memories_by_node, get_memory_by_id)
- [ ] VectorStore (get_node_by_id)
- [ ] expand_with_path_scoring

### 9.5 Performance
- [ ] SIMD for vectors
- [ ] Compact CSR graph storage
- [ ] Path object pool
- [ ] Parallel execution
- [ ] Cache-friendly layout

### 9.6 Tests
- [ ] Unit tests (score propagation, merge, branching)
- [ ] Integration test (small graph retrieval)
- [ ] Benchmark (large graph)
- [ ] Edge cases (empty graph, single node, cycles)

---

## 10. Contact

- MoFox Bot Team
- Python reference: `src/memory_graph/utils/path_expansion.py`
- Config example: `config/bot_config.toml`

---

End of document. Good luck with your implementation.
    
