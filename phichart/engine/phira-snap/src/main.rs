//! phira-snap: render frames of an RPE chart with Phira's real engine (prpr).
//!
//! Usage: phira-snap <job.json>
//!
//! job.json:
//! {
//!   "chart_dir": "/abs/dir",          // folder holding the chart + music
//!   "chart": "chart.json",            // file name inside chart_dir
//!   "music": "song.ogg",              // file name inside chart_dir (any format prpr decodes)
//!   "background": "/abs/bg.png",      // optional
//!   "dim": 0.6,                        // optional background dim (0..1)
//!   "aspect_ratio": 1.7777778,         // optional, default 16:9
//!   "note_scale": 1.0,                 // optional
//!   "frames": [{"time": 12.5, "out": "/abs/f.png"}]   // time = chart time in seconds
//! }
//! Window size is taken from the PHIRA_SNAP_W / PHIRA_SNAP_H env vars (default 1280x720).

use anyhow::{Context, Result};
use macroquad::prelude::*;
use prpr::{
    config::Config,
    core::{init_assets, Resource},
    ext::SafeTexture,
    fs::fs_from_file,
    info::{ChartFormat, ChartInfo},
    scene::GameScene,
    ui::{FontArc, TextPainter, Ui},
};
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Frame {
    time: f64,
    out: PathBuf,
}

#[derive(Deserialize)]
struct Job {
    chart_dir: PathBuf,
    chart: String,
    music: String,
    background: Option<PathBuf>,
    dim: Option<f32>,
    aspect_ratio: Option<f32>,
    note_scale: Option<f32>,
    frames: Vec<Frame>,
}

fn conf() -> Conf {
    let w = std::env::var("PHIRA_SNAP_W").ok().and_then(|it| it.parse().ok()).unwrap_or(1280);
    let h = std::env::var("PHIRA_SNAP_H").ok().and_then(|it| it.parse().ok()).unwrap_or(720);
    Conf {
        window_title: "phira-snap".to_owned(),
        window_width: w,
        window_height: h,
        window_resizable: false,
        ..Default::default()
    }
}

#[macroquad::main(conf)]
async fn main() {
    let code = match run().await {
        Ok(()) => 0,
        Err(err) => {
            eprintln!("phira-snap error: {err:?}");
            1
        }
    };
    std::process::exit(code);
}

async fn run() -> Result<()> {
    let job_path = std::env::args().nth(1).context("usage: phira-snap <job.json>")?;
    let job_path = std::fs::canonicalize(job_path)?;
    let mut job: Job = serde_json::from_slice(&std::fs::read(&job_path)?).context("invalid job json")?;
    // init_assets() changes cwd to the folder containing Phira's `assets`, so resolve paths first
    // (relative paths are relative to the job file).
    let base = job_path.parent().map(|it| it.to_path_buf()).unwrap_or_default();
    let abs = |p: &PathBuf| if p.is_absolute() { p.clone() } else { base.join(p) };
    let chart_dir = std::fs::canonicalize(abs(&job.chart_dir))?;
    job.background = job.background.as_ref().map(abs);
    for frame in &mut job.frames {
        frame.out = abs(&frame.out);
    }
    init_assets();

    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let _guard = rt.enter();

    let mut info = ChartInfo::default();
    info.chart = job.chart.clone();
    info.music = job.music.clone();
    info.format = Some(ChartFormat::Rpe);
    info.background_dim = job.dim.unwrap_or(0.6);
    if let Some(ar) = job.aspect_ratio {
        info.aspect_ratio = ar;
    }

    let mut fs = fs_from_file(&chart_dir)?;
    let (mut chart, _, _) = GameScene::load_chart(fs.as_mut(), &info).await.context("failed to load chart")?;

    let mut config = Config::default();
    config.particle = false;
    config.disable_effect = true;
    config.sample_count = 1;
    // headless: audio goes to an ALSA null sink, pin a sane rate/buffer
    config.preferred_sample_rate = Some(44100);
    config.audio_buffer_size = Some(1024);
    config.aspect_ratio = Some(info.aspect_ratio);
    if let Some(ns) = job.note_scale {
        config.note_scale = ns;
    }

    let bg_tex = match &job.background {
        Some(p) => {
            let img = image::open(p).with_context(|| format!("cannot open background {}", p.display()))?;
            SafeTexture::from(img)
        }
        None => SafeTexture::from(Texture2D::from_rgba8(1, 1, &[24, 24, 32, 255])),
    };
    let mut res = Resource::new(config, info.clone(), fs, None, bg_tex.clone(), bg_tex.clone(), true)
        .await
        .context("failed to create resource")?;
    res.judge_line_color = res.res_pack.info.color_perfect();

    let font = FontArc::try_from_vec(load_file("phigros.ttf").await?)?;
    let mut painter = TextPainter::new(font, None);

    // warm-up frame so the GL context / viewport is fully initialised
    clear_background(BLACK);
    next_frame().await;

    for frame in &job.frames {
        res.time = frame.time.max(0.) as f32 as _;
        chart.update(&mut res);
        {
            let mut ui = Ui::new(&mut painter, None);
            let vp = ui.viewport;
            res.update_size(vp);
            set_camera(&res.camera);
            clear_background(BLACK);
            let top = 1. / res.aspect_ratio;
            // background (cover-fit)
            let (tw, th) = (bg_tex.width(), bg_tex.height());
            let (sw, sh) = (2., top * 2.);
            let s = (sw / tw).max(sh / th);
            draw_texture_ex(
                *bg_tex,
                -tw * s / 2.,
                -th * s / 2.,
                WHITE,
                DrawTextureParams {
                    dest_size: Some(vec2(tw * s, th * s)),
                    ..Default::default()
                },
            );
            draw_rectangle(-1., -top, 2., top * 2., Color::new(0., 0., 0., res.info.background_dim));
            chart.render(&mut ui, &mut res);
        }
        let img = get_screen_data();
        let (w, h) = (img.width as u32, img.height as u32);
        let mut buf = image::RgbaImage::from_raw(w, h, img.bytes.clone()).context("bad screen buffer")?;
        image::imageops::flip_vertical_in_place(&mut buf);
        if let Some(parent) = frame.out.parent() {
            std::fs::create_dir_all(parent)?;
        }
        buf.save(&frame.out).with_context(|| format!("cannot save {}", frame.out.display()))?;
        next_frame().await;
    }
    Ok(())
}
