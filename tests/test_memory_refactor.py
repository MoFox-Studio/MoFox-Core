# -*- coding: utf-8 -*-
"""
记忆系统重构后测试套件

覆盖: 导入/结构/配置/模型/图存储/prompt/API兼容/语法/清理
"""

import ast
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ═══════════ 1. 模块导入 ═══════════
def test_imports():
    # 使用直接子模块导入，避免触发 __init__.py 中的 MemoryManager 导入链
    from src.memory_graph.models import (EdgeType, Memory, MemoryEdge, MemoryNode, MemoryStatus, MemoryType, NodeType, MemoryConfig, MemoryTier, GraphOperationType, ShortTermOperation, MemoryBlock, PerceptualMemory, ShortTermMemory, JudgeDecision, ShortTermDecision)
    from src.memory_graph.manager_singleton import (get_memory_manager, initialize_memory_manager, shutdown_memory_manager, is_initialized)
    print("  PASS test_imports")

# ═══════════ 2. 代码结构 ═══════════
def test_structure():
    src_dir = Path(__file__).resolve().parent.parent / "src" / "memory_graph"
    ltm = src_dir / "long_term_manager.py"
    ltm_src = ltm.read_text(encoding="utf-8")
    ltm_lines = ltm_src.split("\n")
    ltm_methods = [l for l in ltm_lines if l.strip().startswith(("def ", "async def "))]
    assert len(ltm_lines) < 900, f"long_term_manager too long: {len(ltm_lines)}"
    assert len(ltm_methods) < 25, f"too many methods: {len(ltm_methods)}"
    um = len((src_dir / "unified_manager.py").read_text(encoding="utf-8").split("\n"))
    assert um < 750, f"unified_manager too long: {um}"
    ms = len((src_dir / "manager_singleton.py").read_text(encoding="utf-8").split("\n"))
    assert ms < 250, f"manager_singleton too long: {ms}"
    print(f"  PASS test_structure: ltm={len(ltm_lines)}/{len(ltm_methods)}m, um={um}, ms={ms}")

# ═══════════ 3. MemoryConfig ═══════════
def test_memory_config_defaults():
    from src.memory_graph.models import MemoryConfig
    cfg = MemoryConfig()
    assert cfg.perceptual_max_blocks == 50
    assert cfg.short_term_max_memories == 30
    assert cfg.short_term_transfer_threshold == 0.6
    assert cfg.long_term_batch_size == 10
    assert cfg.long_term_decay_factor == 0.95
    assert cfg.judge_confidence_threshold == 0.7
    print("  PASS test_memory_config_defaults")

def test_memory_config_kwargs():
    from src.memory_graph.models import MemoryConfig
    cfg = MemoryConfig(perceptual_max_blocks=30, short_term_max_memories=20)
    pk = cfg.to_perceptual_kwargs()
    assert pk["max_blocks"] == 30
    sk = cfg.to_short_term_kwargs()
    assert sk["max_memories"] == 20
    lk = cfg.to_long_term_kwargs()
    assert lk["batch_size"] == 10
    print("  PASS test_memory_config_kwargs")

def test_memory_config_custom():
    from src.memory_graph.models import MemoryConfig
    cfg = MemoryConfig(perceptual_max_blocks=100, short_term_transfer_threshold=0.8, long_term_batch_size=20, long_term_auto_transfer_interval=300)
    assert cfg.perceptual_max_blocks == 100
    assert cfg.short_term_transfer_threshold == 0.8
    print("  PASS test_memory_config_custom")

# ═══════════ 4. 数据模型 ═══════════
def test_memory_node():
    from src.memory_graph.models import MemoryNode, NodeType
    node = MemoryNode(id="test_1", content="Test", node_type=NodeType.SUBJECT)
    d = node.to_dict()
    node2 = MemoryNode.from_dict(d)
    assert node2.id == node.id
    print("  PASS test_memory_node")

def test_short_term_memory():
    from src.memory_graph.models import ShortTermMemory
    stm = ShortTermMemory(id="stm_test_1", content="test", importance=0.7, subject="U", topic="T")
    d = stm.to_dict()
    stm2 = ShortTermMemory.from_dict(d)
    assert stm2.importance == 0.7
    assert stm2.id == "stm_test_1"
    print("  PASS test_short_term_memory")

def test_judge_decision():
    from src.memory_graph.models import JudgeDecision
    jd = JudgeDecision(is_sufficient=False, confidence=0.8, reasoning="need more", additional_queries=["q1"], missing_aspects=["time"])
    d = jd.to_dict()
    jd2 = JudgeDecision.from_dict(d)
    assert jd2.is_sufficient == jd.is_sufficient
    print("  PASS test_judge_decision")

def test_short_term_decision():
    from src.memory_graph.models import ShortTermDecision, ShortTermOperation
    sd = ShortTermDecision(operation=ShortTermOperation.MERGE, target_memory_id="mem_123", reasoning="overlap", confidence=0.9)
    d = sd.to_dict()
    sd2 = ShortTermDecision.from_dict(d)
    assert sd2.operation == sd.operation
    print("  PASS test_short_term_decision")

# ═══════════ 5. GraphStore ═══════════
def test_graph_store_basic():
    from src.memory_graph.storage.graph_store import GraphStore
    from src.memory_graph.models import Memory, MemoryNode, MemoryEdge, NodeType, EdgeType, MemoryType
    store = GraphStore()
    n1 = MemoryNode(id="n1", content="U", node_type=NodeType.SUBJECT)
    n2 = MemoryNode(id="n2", content="C", node_type=NodeType.OBJECT)
    e1 = MemoryEdge(id="e1", source_id="n1", target_id="n2", relation="like", edge_type=EdgeType.CORE_RELATION)
    mem = Memory(id="m1", subject_id="n1", memory_type=MemoryType.FACT, nodes=[n1, n2], edges=[e1])
    store.add_memory(mem)
    assert store.get_memory_by_id("m1") is not None
    stats = store.get_statistics()
    assert stats["total_memories"] == 1
    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1
    assert store.remove_memory("m1")
    assert store.get_memory_by_id("m1") is None
    print("  PASS test_graph_store_basic")

def test_graph_store_merge():
    from src.memory_graph.storage.graph_store import GraphStore
    from src.memory_graph.models import Memory, MemoryNode, MemoryEdge, NodeType, EdgeType, MemoryType
    store = GraphStore()
    n1 = MemoryNode(id="n1", content="U", node_type=NodeType.SUBJECT)
    n2 = MemoryNode(id="n2", content="coffee", node_type=NodeType.OBJECT)
    e1 = MemoryEdge(id="e1", source_id="n1", target_id="n2", relation="like", edge_type=EdgeType.CORE_RELATION)
    mem1 = Memory(id="m1", subject_id="n1", memory_type=MemoryType.FACT, nodes=[n1, n2], edges=[e1])
    n3 = MemoryNode(id="n3", content="U", node_type=NodeType.SUBJECT)
    n4 = MemoryNode(id="n4", content="latte", node_type=NodeType.OBJECT)
    e2 = MemoryEdge(id="e2", source_id="n3", target_id="n4", relation="like", edge_type=EdgeType.CORE_RELATION)
    mem2 = Memory(id="m2", subject_id="n3", memory_type=MemoryType.FACT, nodes=[n3, n4], edges=[e2])
    store.add_memory(mem1)
    store.add_memory(mem2)
    assert store.merge_memories("m1", ["m2"])
    assert store.get_memory_by_id("m2") is None
    merged = store.get_memory_by_id("m1")
    node_ids = {n.id for n in merged.nodes}
    assert "n3" in node_ids and "n4" in node_ids
    print("  PASS test_graph_store_merge")

# ═══════════ 6. Prompt & Parse ═══════════
def test_prompt_methods_exist():
    from src.memory_graph.long_term_manager import LongTermMemoryManager
    for m in ["_build_extraction_prompt", "_parse_extraction_result", "_extract_structured_memory", "_upsert_long_term_memory"]:
        assert hasattr(LongTermMemoryManager, m), f"Missing: {m}"
    print("  PASS test_prompt_methods_exist")

def test_parse_extraction_result():
    from src.memory_graph.long_term_manager import LongTermMemoryManager
    from src.memory_graph.models import ShortTermMemory

    class Fake:
        pass
    ltm = LongTermMemoryManager.__new__(LongTermMemoryManager)
    ltm.memory_manager = Fake()
    ltm.llm_temperature = 0.2

    stm = ShortTermMemory(id="stm_parse_test", content="test", importance=0.5, subject="U", topic="T")

    # JSON in code block
    r1 = ltm._parse_extraction_result('```json\n{"action":"create","subject":"U","topic":"coffee","importance":0.8}\n```', stm)
    assert r1["action"] == "create" and r1["topic"] == "coffee" and r1["importance"] == 0.8

    # Plain JSON
    r2 = ltm._parse_extraction_result('{"action":"update","target_memory_id":"m1"}', stm)
    assert r2["action"] == "update" and r2["target_memory_id"] == "m1"

    # Garbage fallback
    r3 = ltm._parse_extraction_result("not json", stm)
    assert r3["action"] == "create" and r3["subject"] == "U"
    print("  PASS test_parse_extraction_result")

# ═══════════ 7. API兼容 ═══════════
def test_api_exports():
    from src.memory_graph.models import MemoryConfig
    assert MemoryConfig is not None
    print("  PASS test_api_exports")

def test_singleton_api_exists():
    # 检查模块源码确保所有 API 函数存在（避免导入触发配置加载）
    ms_path = Path(__file__).resolve().parent.parent / "src" / "memory_graph" / "manager_singleton.py"
    src = ms_path.read_text(encoding="utf-8")
    required = [
        "get_memory_manager", "initialize_memory_manager", "shutdown_memory_manager",
        "is_initialized", "get_unified_memory_manager", "initialize_unified_memory_manager",
        "ensure_unified_memory_manager_initialized", "shutdown_unified_memory_manager",
    ]
    for name in required:
        assert f"def {name}" in src or f"async def {name}" in src, f"Missing: {name}"
    print("  PASS test_singleton_api_exists")

# ═══════════ 8. 语法 + 清理验证 ═══════════
def test_syntax_all_files():
    root = Path(__file__).resolve().parent.parent
    files = [
        "src/memory_graph/models.py", "src/memory_graph/__init__.py",
        "src/memory_graph/manager.py", "src/memory_graph/manager_singleton.py",
        "src/memory_graph/unified_manager.py", "src/memory_graph/long_term_manager.py",
        "src/memory_graph/perceptual_manager.py", "src/memory_graph/short_term_manager.py",
        "src/memory_graph/storage/graph_store.py", "src/memory_graph/storage/vector_store.py",
        "src/memory_graph/storage/persistence.py", "src/memory_graph/core/builder.py",
        "src/memory_graph/core/extractor.py", "src/memory_graph/core/node_merger.py",
        "src/memory_graph/utils/embeddings.py", "src/memory_graph/utils/similarity.py",
        "src/memory_graph/utils/three_tier_formatter.py", "src/memory_graph/tools/memory_tools.py",
        "src/memory_graph/plugin_tools/memory_plugin_tools.py",
        "src/main.py", "src/api/memory_visualizer_router.py",
    ]
    for f in files:
        fpath = root / f
        if fpath.exists():
            ast.parse(fpath.read_text(encoding="utf-8"))
    print(f"  PASS test_syntax_all_files ({len(files)} files)")

def test_no_old_code():
    ltm = Path(__file__).resolve().parent.parent / "src" / "memory_graph" / "long_term_manager.py"
    src = ltm.read_text(encoding="utf-8")
    removed = ["_decide_graph_operations", "_build_graph_operation_prompt", "_execute_create_memory", "_execute_update_memory", "_execute_merge_memories", "_execute_create_node", "_execute_create_edge", "_is_placeholder_id", "_register_temp_id", "_resolve_id", "_resolve_parameters", "_register_aliases_from_params"]
    for m in removed:
        assert f"def {m}" not in src, f"Old method still present: {m}"
    new = ["_extract_structured_memory", "_build_extraction_prompt", "_parse_extraction_result", "_upsert_long_term_memory"]
    for m in new:
        assert f"def {m}" in src or f"async def {m}" in src, f"New method missing: {m}"
    print(f"  PASS test_no_old_code: {len(removed)} removed, {len(new)} present")

# ═══════════ RUN ═══════════
if __name__ == "__main__":
    print("=" * 60)
    print("Memory System Refactor Test Suite")
    print("=" * 60)
    tests = [
        ("imports", test_imports), ("structure", test_structure),
        ("MemoryConfig defaults", test_memory_config_defaults),
        ("MemoryConfig kwargs", test_memory_config_kwargs),
        ("MemoryConfig custom", test_memory_config_custom),
        ("MemoryNode", test_memory_node), ("ShortTermMemory", test_short_term_memory),
        ("JudgeDecision", test_judge_decision), ("ShortTermDecision", test_short_term_decision),
        ("GraphStore basic", test_graph_store_basic), ("GraphStore merge", test_graph_store_merge),
        ("prompt methods", test_prompt_methods_exist), ("parse extraction", test_parse_extraction_result),
        ("API exports", test_api_exports), ("singleton API", test_singleton_api_exists),
        ("syntax all files", test_syntax_all_files), ("old code cleanup", test_no_old_code),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"\n{'=' * 60}")
    print(f"Result: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
    if failed:
        sys.exit(1)
