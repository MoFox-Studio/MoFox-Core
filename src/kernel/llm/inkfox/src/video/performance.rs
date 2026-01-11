use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[pyclass]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PyPerformanceResult {
    #[pyo3(get)] pub test_name: String,
    #[pyo3(get)] pub video_file: String,
    #[pyo3(get)] pub total_time_ms: f64,
    #[pyo3(get)] pub frame_extraction_time_ms: f64,
    #[pyo3(get)] pub keyframe_analysis_time_ms: f64,
    #[pyo3(get)] pub total_frames: usize,
    #[pyo3(get)] pub keyframes_extracted: usize,
    #[pyo3(get)] pub keyframe_ratio: f64,
    #[pyo3(get)] pub processing_fps: f64,
    #[pyo3(get)] pub max_keyframes_requested: usize,
    #[pyo3(get)] pub optimization_type: String,
    #[pyo3(get)] pub simd_enabled: bool,
    #[pyo3(get)] pub threads_used: usize,
    #[pyo3(get)] pub timestamp: String,
}

#[pymethods]
impl PyPerformanceResult {
    fn to_dict(&self) -> PyResult<HashMap<String, PyObject>> { Python::with_gil(|py| { let mut d=HashMap::new();
        d.insert("test_name".into(), self.test_name.to_object(py));
        d.insert("video_file".into(), self.video_file.to_object(py));
        d.insert("total_time_ms".into(), self.total_time_ms.to_object(py));
        d.insert("frame_extraction_time_ms".into(), self.frame_extraction_time_ms.to_object(py));
        d.insert("keyframe_analysis_time_ms".into(), self.keyframe_analysis_time_ms.to_object(py));
        d.insert("total_frames".into(), self.total_frames.to_object(py));
        d.insert("keyframes_extracted".into(), self.keyframes_extracted.to_object(py));
        d.insert("keyframe_ratio".into(), self.keyframe_ratio.to_object(py));
        d.insert("processing_fps".into(), self.processing_fps.to_object(py));
        d.insert("max_keyframes_requested".into(), self.max_keyframes_requested.to_object(py));
        d.insert("optimization_type".into(), self.optimization_type.to_object(py));
        d.insert("simd_enabled".into(), self.simd_enabled.to_object(py));
        d.insert("threads_used".into(), self.threads_used.to_object(py));
        d.insert("timestamp".into(), self.timestamp.to_object(py)); Ok(d) }) }
}

pub struct PerformanceResult { pub test_name:String, pub video_file:String, pub total_time_ms:f64, pub frame_extraction_time_ms:f64,
    pub keyframe_analysis_time_ms:f64, pub total_frames:usize, pub keyframes_extracted:usize, pub keyframe_ratio:f64,
    pub processing_fps:f64, pub max_keyframes_requested:usize, pub optimization_type:String, pub simd_enabled:bool, pub threads_used:usize, pub timestamp:String }

impl From<PerformanceResult> for PyPerformanceResult { fn from(r:PerformanceResult)->Self { Self { test_name:r.test_name, video_file:r.video_file,
    total_time_ms:r.total_time_ms, frame_extraction_time_ms:r.frame_extraction_time_ms, keyframe_analysis_time_ms:r.keyframe_analysis_time_ms,
    total_frames:r.total_frames, keyframes_extracted:r.keyframes_extracted, keyframe_ratio:r.keyframe_ratio, processing_fps:r.processing_fps,
    max_keyframes_requested:r.max_keyframes_requested, optimization_type:r.optimization_type, simd_enabled:r.simd_enabled, threads_used:r.threads_used, timestamp:r.timestamp }}}