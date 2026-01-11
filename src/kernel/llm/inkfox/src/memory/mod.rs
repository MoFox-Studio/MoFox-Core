use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::SystemTime;
use dashmap::DashMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MetadataEntry {
    pub memory_id: String,
    pub user_id: String,
    pub memory_type: String,
    pub subjects: Vec<String>,
    pub objects: Vec<String>,
    pub keywords: Vec<String>,
    pub tags: Vec<String>,
    pub importance: u8,
    pub confidence: u8,
    pub created_at: f64,
    pub access_count: u32,
    pub chat_id: Option<String>,
    pub content_preview: Option<String>,
}

impl MetadataEntry {
    fn normalize_vec(raw: &Bound<PyAny>) -> Vec<String> {
        if let Ok(list) = raw.downcast::<PyList>() {
            list.iter().filter_map(|v| v.extract::<String>().ok()).collect()
        } else if let Ok(s) = raw.extract::<String>() { vec![s] } else { vec![] }
    }

    fn from_pydict(d: &Bound<PyDict>) -> PyResult<Self> {
        fn get_item<'py>(d: &Bound<'py, PyDict>, key: &str) -> Option<Bound<'py, PyAny>> {
            match d.get_item(key) {
                Ok(Some(v)) => Some(v),
                _ => None,
            }
        }
        fn get_str(d: &Bound<PyDict>, key: &str) -> String {
            get_item(d, key).and_then(|v| v.extract::<String>().ok()).unwrap_or_default()
        }
        fn get_u8(d: &Bound<PyDict>, key: &str, default: u8) -> u8 {
            get_item(d, key).and_then(|v| v.extract::<u8>().ok()).unwrap_or(default)
        }
        fn get_u32(d: &Bound<PyDict>, key: &str, default: u32) -> u32 {
            get_item(d, key).and_then(|v| v.extract::<u32>().ok()).unwrap_or(default)
        }
        fn get_vec(d: &Bound<PyDict>, key: &str) -> Vec<String> {
            get_item(d, key).map(|v| MetadataEntry::normalize_vec(&v)).unwrap_or_default()
        }
        let created_at: f64 = get_item(d, "created_at")
            .and_then(|v| v.extract::<f64>().ok())
            .unwrap_or_else(|| SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_secs_f64());
        let subjects = get_vec(d, "subjects");
        let objects = get_vec(d, "objects");
        let keywords = get_vec(d, "keywords");
        let tags = get_vec(d, "tags");
        let memory_id = get_str(d, "memory_id");
        if memory_id.is_empty() { return Err(pyo3::exceptions::PyValueError::new_err("memory_id missing")); }
        Ok(MetadataEntry {
            memory_id,
            user_id: get_str(d, "user_id"),
            memory_type: get_str(d, "memory_type"),
            subjects,
            objects,
            keywords,
            tags,
            importance: get_u8(d, "importance", 2),
            confidence: get_u8(d, "confidence", 2),
            created_at,
            access_count: get_u32(d, "access_count", 0),
            chat_id: get_item(d, "chat_id").and_then(|v| v.extract::<String>().ok()),
            content_preview: get_item(d, "content_preview").and_then(|v| v.extract::<String>().ok()),
        })
    }
}

#[derive(Default)]
struct InnerIndex {
    entries: DashMap<String, MetadataEntry>,
    type_index: DashMap<String, Vec<String>>,      // type -> ids
    subject_index: DashMap<String, Vec<String>>,   // subject -> ids
    keyword_index: DashMap<String, Vec<String>>,   // keyword -> ids
    tag_index: DashMap<String, Vec<String>>,       // tag -> ids
}

impl InnerIndex {
    fn add_entry(&self, e: MetadataEntry) {
        let id = e.memory_id.clone();
        if let Some(old) = self.entries.get(&id) { // remove old references
            self.remove_from_inverted(old.value());
        }
        self.entries.insert(id.clone(), e.clone());
        self.push_index(&self.type_index, &e.memory_type, &id);
        for s in &e.subjects { self.push_index(&self.subject_index, &s.to_lowercase(), &id); }
        for k in &e.keywords { self.push_index(&self.keyword_index, &k.to_lowercase(), &id); }
        for t in &e.tags { self.push_index(&self.tag_index, &t.to_lowercase(), &id); }
    }
    fn push_index(&self, map: &DashMap<String, Vec<String>>, key: &str, id: &str) {
        if key.is_empty() { return; }
        let mut v = map.entry(key.to_string()).or_insert_with(Vec::new);
        // 避免重复
        if !v.iter().any(|x| x == id) { v.push(id.to_string()); }
    }
    fn remove_from_inverted(&self, e: &MetadataEntry) {
        if let Some(mut v) = self.type_index.get_mut(&e.memory_type) { v.retain(|x| x != &e.memory_id); }
        for s in &e.subjects { if let Some(mut v)= self.subject_index.get_mut(&s.to_lowercase()) { v.retain(|x| x != &e.memory_id); } }
        for k in &e.keywords { if let Some(mut v)= self.keyword_index.get_mut(&k.to_lowercase()) { v.retain(|x| x != &e.memory_id); } }
        for t in &e.tags { if let Some(mut v)= self.tag_index.get_mut(&t.to_lowercase()) { v.retain(|x| x != &e.memory_id); } }
    }
}

#[pyclass]
pub struct PyMetadataIndex {
    inner: Arc<InnerIndex>,
    path: Option<PathBuf>,
}

#[pymethods]
impl PyMetadataIndex {
    #[new]
    #[pyo3(signature = (path=None))]
    pub fn new(path: Option<String>) -> PyResult<Self> {
        let idx = InnerIndex::default();
        let inst = PyMetadataIndex { inner: Arc::new(idx), path: path.map(PathBuf::from) };
        if let Some(p) = &inst.path {
            if p.exists() {
                if let Ok(bytes) = fs::read(p) {
                    if let Ok(vec) = serde_json::from_slice::<Vec<MetadataEntry>>(&bytes) {
                        for e in vec { inst.inner.add_entry(e); }
                    }
                }
            }
        }
        Ok(inst)
    }

    pub fn batch_add(&self, _py: Python<'_>, entries: &Bound<PyAny>) -> PyResult<usize> {
        let mut count = 0usize;
        if let Ok(list) = entries.downcast::<PyList>() {
            for item in list.iter() {
                if let Ok(d) = item.downcast::<PyDict>() { if let Ok(e) = MetadataEntry::from_pydict(&d) { self.inner.add_entry(e); count+=1; } }
            }
        }
        Ok(count)
    }

    #[pyo3(signature = (params))]
    pub fn search_flexible(&self, params: &Bound<PyDict>) -> PyResult<Vec<String>> {
        let get = |k: &str| params.get_item(k).ok().flatten();
        let user_id: Option<String> = get("user_id").and_then(|v| v.extract::<String>().ok());
        let types: Option<Vec<String>> = get("memory_types").and_then(|v| v.extract::<Vec<String>>().ok());
        let subjects: Option<Vec<String>> = get("subjects").and_then(|v| v.extract::<Vec<String>>().ok());
        let created_after: Option<f64> = get("created_after").and_then(|v| v.extract::<f64>().ok());
        let created_before: Option<f64> = get("created_before").and_then(|v| v.extract::<f64>().ok());
        let limit: usize = get("limit").and_then(|v| v.extract::<usize>().ok()).unwrap_or(100);

        let entries: Vec<MetadataEntry> = self.inner.entries.iter().map(|e| e.value().clone()).collect();
        let subjects_lc: Vec<String> = subjects.clone().unwrap_or_default().into_iter().map(|s| s.to_lowercase()).collect();

        let mut scored: Vec<(f32, String, f64)> = entries.par_iter().filter_map(|e| {
            if let Some(uid) = &user_id { if &e.user_id != uid { return None; } }
            // 时间过滤
            if let Some(ca) = created_after { if e.created_at < ca { return None; } }
            if let Some(cb) = created_before { if e.created_at > cb { return None; } }

            let mut score = 0f32;
            // 1. 类型
            if let Some(ts) = &types { if !ts.is_empty() { let mut tscore = 0f32; for t in ts { if e.memory_type == *t { tscore = 1.0; break; } else if e.memory_type.contains(t) || t.contains(&e.memory_type) { tscore = 0.5; break; } } score += tscore; } }
            // 2. 主语
            if !subjects_lc.is_empty() { let mut sscore = 0f32; for s in &subjects_lc { for es in &e.subjects { let esn = es.to_lowercase(); if esn == *s { sscore = 1.0; break; } if esn.contains(s) || s.contains(&esn) { sscore = 0.6; break; } } if sscore > 0.0 { break; } } score += sscore; }
            // 3. 宾语与主语关联
            if !subjects_lc.is_empty() && !e.objects.is_empty() { let mut os = 0f32; 'outer: for o in &e.objects { let on = o.to_lowercase(); for s in &subjects_lc { if on.contains(s) || s.contains(&on) { os = 0.8; break 'outer; } } } score += os; }
            // 4. 时间加分（如果传了范围且通过）
            if created_after.is_some() || created_before.is_some() { score += 1.0; }
            if score >= 2.0 { Some((score, e.memory_id.clone(), e.created_at)) } else { None }
        }).collect();

        // 排序: 分数优先，时间次之（新 -> 旧）
        scored.par_sort_unstable_by(|a,b| {
            b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal))
        });
        Ok(scored.into_iter().take(limit).map(|(_, id, _)| id).collect())
    }

    #[pyo3(signature = (params))]
    pub fn search_strict(&self, params: &Bound<PyDict>) -> PyResult<Vec<String>> {
        let get = |k: &str| params.get_item(k).ok().flatten();
        let user_id: Option<String> = get("user_id").and_then(|v| v.extract::<String>().ok());
        let types: Option<Vec<String>> = get("memory_types").and_then(|v| v.extract::<Vec<String>>().ok());
        let subjects: Option<Vec<String>> = get("subjects").and_then(|v| v.extract::<Vec<String>>().ok());
        let keywords: Option<Vec<String>> = get("keywords").and_then(|v| v.extract::<Vec<String>>().ok());
        let tags: Option<Vec<String>> = get("tags").and_then(|v| v.extract::<Vec<String>>().ok());
        let importance_min: Option<u8> = get("importance_min").and_then(|v| v.extract::<u8>().ok());
        let importance_max: Option<u8> = get("importance_max").and_then(|v| v.extract::<u8>().ok());
        let created_after: Option<f64> = get("created_after").and_then(|v| v.extract::<f64>().ok());
        let created_before: Option<f64> = get("created_before").and_then(|v| v.extract::<f64>().ok());
        let limit: usize = get("limit").and_then(|v| v.extract::<usize>().ok()).unwrap_or(100);

        let mut candidates: Vec<MetadataEntry> = self.inner.entries.iter().map(|e| e.value().clone()).collect();
        // 用户过滤
        if let Some(uid) = &user_id { candidates.retain(|e| &e.user_id == uid); }
        // 类型过滤
        if let Some(ts) = &types { if !ts.is_empty() { candidates.retain(|e| ts.iter().any(|t| t == &e.memory_type)); } }
        // 主语过滤（模糊）
        if let Some(subs) = &subjects { if !subs.is_empty() { let subs_lc: Vec<String> = subs.iter().map(|s| s.to_lowercase()).collect(); candidates.retain(|e| { let mut ok=false; for s in &subs_lc { for es in &e.subjects { let esn=es.to_lowercase(); if esn==*s || esn.contains(s) || s.contains(&esn) { ok=true; break; } } if ok { break; } } ok }); } }
        // 关键词过滤
        if let Some(ks) = &keywords { if !ks.is_empty() { let ks_lc: Vec<String> = ks.iter().map(|k| k.to_lowercase()).collect(); candidates.retain(|e| { let mut ok=false; for k in &ks_lc { for ek in &e.keywords { let ekn=ek.to_lowercase(); if ekn==*k || ekn.contains(k) || k.contains(&ekn) { ok=true; break; } } if ok { break; } } ok }); } }
        // 标签过滤（精确OR）
        if let Some(ts) = &tags { if !ts.is_empty() { candidates.retain(|e| e.tags.iter().any(|t| ts.iter().any(|tt| tt==t))); } }
        // 重要性过滤
        if importance_min.is_some() || importance_max.is_some() { candidates.retain(|e| { let mut ok=true; if let Some(mi)=importance_min { if e.importance < mi { ok=false; } } if let Some(ma)=importance_max { if e.importance > ma { ok=false; } } ok }); }
        // 时间范围
        if created_after.is_some() || created_before.is_some() { candidates.retain(|e| { if let Some(ca)=created_after { if e.created_at < ca { return false; } } if let Some(cb)=created_before { if e.created_at > cb { return false; } } true }); }
        // 排序（时间降序）
        candidates.sort_by(|a,b| b.created_at.partial_cmp(&a.created_at).unwrap_or(std::cmp::Ordering::Equal));
        let out: Vec<String> = candidates.into_iter().take(limit).map(|e| e.memory_id).collect();
        Ok(out)
    }

    pub fn stats(&self) -> PyResult<Py<PyDict>> {
        Python::with_gil(|py| {
            let d = PyDict::new_bound(py);
            d.set_item("total", self.inner.entries.len())?;
            d.set_item("types_indexed", self.inner.type_index.len())?;
            d.set_item("subjects_indexed", self.inner.subject_index.len())?;
            d.set_item("keywords_indexed", self.inner.keyword_index.len())?;
            d.set_item("tags_indexed", self.inner.tag_index.len())?;
            // 类型分布: memory_type -> 数量
            let types_dist = PyDict::new_bound(py);
            for kv in self.inner.type_index.iter() {
                types_dist.set_item(kv.key(), kv.value().len())?;
            }
            d.set_item("types_dist", types_dist)?;
            Ok(d.into())
        })
    }

    pub fn save(&self) -> PyResult<bool> {
        if let Some(p) = &self.path { 
            let list: Vec<MetadataEntry> = self.inner.entries.iter().map(|e| e.value().clone()).collect();
            if let Ok(json) = serde_json::to_vec(&list) { let _ = fs::write(p, json); return Ok(true); }
        }
        Ok(false)
    }
}
