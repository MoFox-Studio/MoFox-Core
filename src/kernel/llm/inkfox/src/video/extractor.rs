use pyo3::prelude::*;
use std::collections::HashMap;
use std::path::PathBuf;

use crate::video::frame::PyVideoFrame;
use crate::video::performance::PyPerformanceResult;
use crate::video::utils::*;

#[pyclass]
pub struct VideoKeyframeExtractor { ffmpeg_path:String, threads:usize, verbose:bool }

#[pymethods]
impl VideoKeyframeExtractor {
    #[new]
    #[pyo3(signature = (ffmpeg_path = "ffmpeg".to_string(), threads = 0, verbose = false))]
    pub fn new(ffmpeg_path:String, threads:usize, verbose:bool)->PyResult<Self> { if threads>0 { let _ = rayon::ThreadPoolBuilder::new().num_threads(threads).build_global(); }
        Ok(Self { ffmpeg_path, threads: if threads==0 { rayon::current_num_threads() } else { threads }, verbose }) }
    #[pyo3(signature = (video_path, max_frames=None))]
    pub fn extract_frames(&self, video_path:&str, max_frames:Option<usize>) -> PyResult<(Vec<PyVideoFrame>,usize,usize)> {
        extract_frames_memory_stream(&PathBuf::from(video_path), &PathBuf::from(&self.ffmpeg_path), max_frames.unwrap_or(0), self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Frame extraction failed: {}", e))) }
    #[pyo3(signature = (frames, max_keyframes, use_simd=None, block_size=None))]
    pub fn extract_keyframes(&self, frames:Vec<PyVideoFrame>, max_keyframes:usize, use_simd:Option<bool>, block_size:Option<usize>) -> PyResult<Vec<usize>> {
        extract_keyframes_optimized(&frames, max_keyframes, use_simd.unwrap_or(true), block_size.unwrap_or(8192), self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Keyframe extraction failed: {}", e))) }
    #[pyo3(signature = (video_path, keyframe_indices, output_dir, max_save=None))]
    pub fn save_keyframes(&self, video_path:&str, keyframe_indices:Vec<usize>, output_dir:&str, max_save:Option<usize>) -> PyResult<usize> {
        save_keyframes_optimized(&PathBuf::from(video_path), &keyframe_indices, &PathBuf::from(output_dir), &PathBuf::from(&self.ffmpeg_path), max_save.unwrap_or(50), self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Save keyframes failed: {}", e))) }
    #[pyo3(signature = (video_path, max_keyframes, test_name, use_simd=None, block_size=None))]
    pub fn benchmark(&self, video_path:&str, max_keyframes:usize, test_name:&str, use_simd:Option<bool>, block_size:Option<usize>) -> PyResult<PyPerformanceResult> {
        run_performance_test(&PathBuf::from(video_path), max_keyframes, test_name, &PathBuf::from(&self.ffmpeg_path), use_simd.unwrap_or(true), block_size.unwrap_or(8192), self.verbose)
            .map(|r| r.into()).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Benchmark failed: {}", e))) }
    #[pyo3(signature = (video_path, output_dir, max_keyframes, max_save=None, use_simd=None, block_size=None))]
    pub fn process_video(&self, video_path:&str, output_dir:&str, max_keyframes:usize, max_save:Option<usize>, use_simd:Option<bool>, block_size:Option<usize>) -> PyResult<PyPerformanceResult> {
        let max_save_val = max_save.unwrap_or(50); let use_simd_val = use_simd.unwrap_or(true); let block = block_size.unwrap_or(8192);
        let video_path_buf = PathBuf::from(video_path); let output_dir_buf = PathBuf::from(output_dir);
        let result = run_performance_test(&video_path_buf, max_keyframes, "Python Processing", &PathBuf::from(&self.ffmpeg_path), use_simd_val, block, self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Processing failed: {}", e)))?;
        let (frames,_,_) = extract_frames_memory_stream(&video_path_buf, &PathBuf::from(&self.ffmpeg_path), 0, self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Frame extraction failed: {}", e)))?;
        let keyframes = extract_keyframes_optimized(&frames, max_keyframes, use_simd_val, block, self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Keyframe extraction failed: {}", e)))?;
        save_keyframes_optimized(&video_path_buf, &keyframes, &output_dir_buf, &PathBuf::from(&self.ffmpeg_path), max_save_val, self.verbose)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError,_>(format!("Save keyframes failed: {}", e)))?; Ok(result.into()) }
    pub fn get_cpu_features(&self) -> PyResult<HashMap<String,bool>> { let mut f = HashMap::new(); #[cfg(target_arch="x86_64")] {
        f.insert("avx2".into(), std::arch::is_x86_feature_detected!("avx2")); f.insert("sse2".into(), std::arch::is_x86_feature_detected!("sse2"));
        f.insert("sse4_1".into(), std::arch::is_x86_feature_detected!("sse4.1")); f.insert("sse4_2".into(), std::arch::is_x86_feature_detected!("sse4.2")); f.insert("fma".into(), std::arch::is_x86_feature_detected!("fma")); }
        #[cfg(not(target_arch="x86_64"))] { f.insert("simd_supported".into(), false); } Ok(f) }
    pub fn get_thread_count(&self) -> usize { self.threads }
    pub fn get_configured_threads(&self) -> usize { self.threads }
    pub fn get_actual_thread_count(&self) -> usize { rayon::current_num_threads() }
}