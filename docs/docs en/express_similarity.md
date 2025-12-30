# Expression Similarity Strategy

This document explains the implementation and configuration of `calculate_similarity`, helping balance quality and performance.

## Overview

- Supports two paths:
  1) **Vector path (preferred by default)**: TF-IDF + cosine similarity (depends on `scikit-learn`)
  2) **Fallback path**: `difflib.SequenceMatcher`
- Parameter `prefer_vector` controls whether vectorization is attempted first (default `True`)
- Automatically falls back when dependencies are missing or text is too short—no extra config needed

## Usage

```python
from src.chat.express.express_utils import calculate_similarity

sim = calculate_similarity(text1, text2)  # vector-first by default
sim_fast = calculate_similarity(text1, text2, prefer_vector=False)  # force SequenceMatcher
```

## Dependencies and Fallback

- Optional dependency: `scikit-learn`
  - When missing, automatically falls back to `SequenceMatcher` without raising errors
- Text shorter than 2 characters directly falls back to avoid sparse vector noise

## Recommendations

- For longer text or stronger robustness/semantic similarity: keep vector-first (default)
- In environments without `scikit-learn` or pursuing minimal dependencies: set `prefer_vector=False` at call sites
- For high-concurrency, latency-sensitive paths: consider disabling vectorization or adding caching

## Return range

- Similarity always in range `[0, 1]`
- Empty strings → `0.0`; identical strings → `1.0`

## Extra tips

- For stronger semantic capability, swap in a vector database or sentence embedding model (requires new dependencies and config)
- For hot paths, consider adding caching (by text hash) or limiting input length to control vector dimensions and memory usage
