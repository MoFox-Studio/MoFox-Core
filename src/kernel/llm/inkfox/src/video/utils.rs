use anyhow::{Context, Result};
use std::io::{BufReader, Read};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Instant;
use chrono::prelude::*;
use rayon::prelude::*;

// 简洁可控输出
macro_rules! vprintln { ($v:expr, $($t:tt)*) => { if $v { println!($($t)*); } } }

use crate::video::frame::PyVideoFrame;
use crate::video::performance::PerformanceResult;

pub fn extract_frames_memory_stream(video_path:&PathBuf, ffmpeg_path:&PathBuf, _deprecated_max_frames:usize, verbose:bool)->Result<(Vec<PyVideoFrame>,usize,usize)> {
    // _deprecated_max_frames 参数保留仅为兼容内部调用；实际总是提取全部帧
    vprintln!(verbose, "Extracting frames (full video): {}", video_path.display());
    let probe_output = Command::new(ffmpeg_path).args(["-i", video_path.to_str().unwrap(), "-hide_banner"]).output().context("Failed to probe video with FFmpeg")?;
    let probe_info = String::from_utf8_lossy(&probe_output.stderr);
    let (width,height)=parse_video_dimensions(&probe_info).ok_or_else(|| anyhow::anyhow!("Cannot parse video dimensions"))?;
    vprintln!(verbose, "Dimensions: {}x{}", width,height);
    let mut cmd = Command::new(ffmpeg_path); cmd.args(["-i", video_path.to_str().unwrap(), "-f","rawvideo","-pix_fmt","gray","-an","-threads","0","-preset","ultrafast"]);
    // 不再限制帧数：忽略 max_frames
    cmd.args(["-"]).stdout(Stdio::piped()).stderr(Stdio::null());
    let start = Instant::now(); let mut child = cmd.spawn().context("Failed to spawn FFmpeg process")?; let stdout = child.stdout.take().unwrap();
    let mut reader = BufReader::with_capacity(1024*1024, stdout); let frame_size = width*height; let mut frames=Vec::new(); let mut frame_count=0; let mut buf=vec![0u8;frame_size];
    vprintln!(verbose, "Frame size: {} bytes", frame_size);
    loop { match reader.read_exact(&mut buf) { Ok(()) => { frames.push(PyVideoFrame::new(frame_count,width,height,buf.clone())); frame_count+=1; if verbose && frame_count%1000==0 { vprintln!(true, "Processed {} frames", frame_count); } }, Err(_) => break } }
    let _ = child.wait(); vprintln!(verbose, "Done: {} frames in {:.2}s", frame_count, start.elapsed().as_secs_f64());
    Ok((frames,width,height))
}

pub fn parse_video_dimensions(info:&str)->Option<(usize,usize)> { for line in info.lines() { if line.contains("Video:") && line.contains('x') { for part in line.split_whitespace() { if let Some(p)=part.find('x') { let (w,h_part)=part.split_at(p); let h_seg=&h_part[1..]; let h_str=h_seg.split(',').next().unwrap_or(h_seg); if let (Ok(wu),Ok(hu))=(w.parse(), h_str.parse()) { return Some((wu,hu)); } } } } } None }

pub fn extract_keyframes_optimized(frames:&[PyVideoFrame], max_keyframes:usize, use_simd:bool, block_size:usize, verbose:bool)->Result<Vec<usize>> {
    if frames.len()<2 || max_keyframes==0 { return Ok(vec![]); }
    let opt_name = if use_simd { "SIMD+Parallel" } else { "Parallel" }; vprintln!(verbose, "Keyframe analysis target: {} ({})", max_keyframes, opt_name);
    let start = Instant::now();
    // 计算差异并归一化到 [0,1]
    // 收集原始差异 (平均像素差 0..=255)
    let mut diffs: Vec<(usize,f64)> = frames.par_windows(2).enumerate().map(|(i,p)| {
        let raw = if use_simd { p[0].calculate_difference_parallel_simd(&p[1], block_size, true) } else { p[0].calculate_difference(&p[1]).unwrap_or(f64::MAX) };
        (i+1, raw)
    }).collect();
    let total_pairs = diffs.len();
    if max_keyframes >= total_pairs { // 全部作为关键帧
        let mut all: Vec<usize> = diffs.into_iter().map(|(i,_)| i).collect();
        all.sort_unstable();
        vprintln!(verbose, "Keyframes selected: {} (all) in {:.2}s", all.len(), start.elapsed().as_secs_f64());
        return Ok(all);
    }
    // 第 K 大差异 (K = max_keyframes)
    let k_index = max_keyframes - 1;
    diffs.select_nth_unstable_by(k_index, |a,b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let pivot = diffs[k_index].1; // Kth largest raw diff
    // 拿到 >= pivot 的所有索引（可能多于 max_keyframes 因 ties）
    let mut selected: Vec<usize> = diffs.into_iter().filter_map(|(idx,val)| if val >= pivot { Some(idx) } else { None }).collect();
    selected.sort_unstable();
    vprintln!(verbose, "Keyframes selected: {} (requested {}, pivot_diff={:.3}) in {:.2}s", selected.len(), max_keyframes, pivot, start.elapsed().as_secs_f64());
    Ok(selected)
}

pub fn save_keyframes_optimized(video_path:&PathBuf, indices:&[usize], out_dir:&PathBuf, ffmpeg_path:&PathBuf, max_save:usize, verbose:bool)->Result<usize> {
    use std::fs; if indices.is_empty(){ vprintln!(verbose, "No keyframes to save"); return Ok(0);} vprintln!(verbose, "Saving keyframes (max {})...", max_save);
    fs::create_dir_all(out_dir).context("Failed to create output directory")?; let save_count=indices.len().min(max_save); let mut saved=0;
    for (i,&idx) in indices.iter().take(save_count).enumerate() { let output_path = out_dir.join(format!("keyframe_{:03}.jpg", i+1)); let timestamp = idx as f64 / 30.0; let output = Command::new(ffmpeg_path).args(["-i", video_path.to_str().unwrap(), "-ss", &timestamp.to_string(), "-vframes","1","-q:v","2","-y", output_path.to_str().unwrap()]).output().context("Failed to extract keyframe with FFmpeg")?; if output.status.success() { saved+=1; } else if verbose { eprintln!("Save keyframe failed at frame {}", idx); } }
    vprintln!(verbose, "Saved {}/{} keyframes", saved, save_count); Ok(saved)
}

pub fn run_performance_test(video_path:&PathBuf, max_keyframes:usize, test_name:&str, ffmpeg_path:&PathBuf, use_simd:bool, block_size:usize, verbose:bool)->Result<PerformanceResult> {
    vprintln!(verbose, "Run test: {} (max_keyframes={})", test_name, max_keyframes);
    let total_start = Instant::now(); let extraction_start = Instant::now();
    let (frames,_,_) = extract_frames_memory_stream(video_path, ffmpeg_path, 0, verbose)?; let extraction_time = extraction_start.elapsed().as_secs_f64()*1000.0;
    let analysis_start = Instant::now(); let keyframes = extract_keyframes_optimized(&frames, max_keyframes, use_simd, block_size, verbose)?; let analysis_time = analysis_start.elapsed().as_secs_f64()*1000.0;
    let total_time = total_start.elapsed().as_secs_f64()*1000.0; let optimization_type = if use_simd { format!("SIMD+Parallel(block:{})", block_size) } else { "Standard Parallel".into() };
    let result = PerformanceResult { test_name: test_name.into(), video_file: video_path.file_name().unwrap().to_string_lossy().into(), total_time_ms: total_time, frame_extraction_time_ms: extraction_time, keyframe_analysis_time_ms: analysis_time, total_frames: frames.len(), keyframes_extracted: keyframes.len(), keyframe_ratio: keyframes.len() as f64 / frames.len() as f64 * 100.0, processing_fps: frames.len() as f64 / (total_time/1000.0), max_keyframes_requested: max_keyframes, optimization_type, simd_enabled: use_simd, threads_used: rayon::current_num_threads(), timestamp: Local::now().format("%Y-%m-%d %H:%M:%S").to_string() };
    vprintln!(verbose, "Result: frames={} keyframes={} requested={} time_ms={:.2} fps={:.1}", result.total_frames, result.keyframes_extracted, max_keyframes, result.total_time_ms, result.processing_fps);
    Ok(result)
}