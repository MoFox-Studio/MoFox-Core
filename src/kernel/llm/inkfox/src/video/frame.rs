use pyo3::prelude::*;

#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

#[pyclass]
#[derive(Debug, Clone)]
pub struct PyVideoFrame {
    #[pyo3(get)]
    pub frame_number: usize,
    #[pyo3(get)]
    pub width: usize,
    #[pyo3(get)]
    pub height: usize,
    pub data: Vec<u8>,
}

#[pymethods]
impl PyVideoFrame {
    #[new]
    pub fn new(frame_number: usize, width: usize, height: usize, data: Vec<u8>) -> Self {
        let mut aligned_data = data;
        let remainder = aligned_data.len() % 32;
        if remainder != 0 { aligned_data.resize(aligned_data.len() + (32 - remainder), 0); }
        Self { frame_number, width, height, data: aligned_data }
    }
    fn get_data(&self) -> &[u8] { let pixel_count = self.width * self.height; &self.data[..pixel_count] }
    pub fn calculate_difference(&self, other: &PyVideoFrame) -> PyResult<f64> {
        if self.width != other.width || self.height != other.height { return Ok(f64::MAX); }
        let total_pixels = self.width * self.height;
        let total_diff: u64 = self.data[..total_pixels].iter().zip(other.data[..total_pixels].iter())
            .map(|(a,b)| (*a as i32 - *b as i32).abs() as u64).sum();
        Ok(total_diff as f64 / total_pixels as f64)
    }
    #[pyo3(signature = (other, block_size=None))]
    fn calculate_difference_simd(&self, other: &PyVideoFrame, block_size: Option<usize>) -> PyResult<f64> {
        Ok(self.calculate_difference_parallel_simd(other, block_size.unwrap_or(8192), true))
    }
}

impl PyVideoFrame {
    pub fn calculate_difference_parallel_simd(&self, other: &PyVideoFrame, block_size: usize, use_simd: bool) -> f64 {
        use rayon::prelude::*;
        if self.width != other.width || self.height != other.height { return f64::MAX; }
        let total_pixels = self.width * self.height;
        let num_blocks = (total_pixels + block_size - 1)/block_size;
        let total_diff: u64 = (0..num_blocks).into_par_iter().map(|i| {
            let start = i * block_size; let end = ((i+1)*block_size).min(total_pixels); let block_len = end-start;
            if use_simd { #[cfg(target_arch="x86_64")] unsafe {
                if std::arch::is_x86_feature_detected!("avx2") { return self.calculate_difference_avx2_block(&other.data,start,block_len); }
                else if std::arch::is_x86_feature_detected!("sse2") { return self.calculate_difference_sse2_block(&other.data,start,block_len); }
            }}
            self.data[start..end].iter().zip(other.data[start..end].iter())
                .map(|(a,b)| (*a as i32 - *b as i32).abs() as u64).sum::<u64>()
        }).sum();
        total_diff as f64 / total_pixels as f64
    }
    #[cfg(target_arch="x86_64")]
    #[target_feature(enable="avx2")]
    unsafe fn calculate_difference_avx2_block(&self, other: &[u8], start: usize, len: usize) -> u64 {
        let mut total = 0u64; let chunks = len/32; for i in 0..chunks { let off = start + i*32;
            let a = _mm256_loadu_si256(self.data.as_ptr().add(off) as *const __m256i);
            let b = _mm256_loadu_si256(other.as_ptr().add(off) as *const __m256i);
            let diff = _mm256_sad_epu8(a,b);
            total += _mm256_extract_epi64(diff,0) as u64 + _mm256_extract_epi64(diff,1) as u64 + _mm256_extract_epi64(diff,2) as u64 + _mm256_extract_epi64(diff,3) as u64;
        }
        for i in (start + chunks*32)..(start+len) { total += (self.data[i] as i32 - other[i] as i32).abs() as u64; }
        total
    }
    #[cfg(target_arch="x86_64")]
    #[target_feature(enable="sse2")]
    unsafe fn calculate_difference_sse2_block(&self, other: &[u8], start: usize, len: usize) -> u64 {
        let mut total = 0u64; let chunks = len/16; for i in 0..chunks { let off = start + i*16;
            let a = _mm_loadu_si128(self.data.as_ptr().add(off) as *const __m128i);
            let b = _mm_loadu_si128(other.as_ptr().add(off) as *const __m128i);
            let diff = _mm_sad_epu8(a,b);
            total += _mm_extract_epi64(diff,0) as u64 + _mm_extract_epi64(diff,1) as u64;
        }
        for i in (start + chunks*16)..(start+len) { total += (self.data[i] as i32 - other[i] as i32).abs() as u64; }
        total
    }
}