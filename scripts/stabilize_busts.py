#!/usr/bin/env python3
"""
Face-Only Delta Patch — stabilize AI-generated speaking sprite sheets.

Problem: Nano Banana Pro generates each frame independently, so hair, body,
and background have subtle pixel variations → visible flickering in animation.

Solution: Use frame 0 (idle) as reference. For frames 1-3, keep changes ONLY
in the face/mouth region (auto-detected). Everything else is copied from frame 0.

Algorithm:
  1. Split sprite sheet into N frames
  2. Frame 0 = BASE reference
  3. For each frame N (1..3):
     a. Per-pixel diff from BASE (sum of |R|+|G|+|B| channels)
     b. Threshold → binary change map (removes AI generation noise)
     c. Morphological close → fill gaps in face region
     d. Largest connected component → face cluster
     e. Dilate + Gaussian blur → soft mask with feathered edges
     f. Composite: output = BASE * (1 - mask) + frameN * mask
  4. Reassemble patched sprite sheet

Usage:
  python scripts/stabilize_busts.py                       # preview all (test output)
  python scripts/stabilize_busts.py --avatar af_bella     # single avatar
  python scripts/stabilize_busts.py --apply               # overwrite originals
  python scripts/stabilize_busts.py --preview             # regenerate HTML only
  python scripts/stabilize_busts.py --threshold 30        # custom diff threshold

Output:
  scripts/bust-test/                    — test directory
  scripts/bust-test/<name>/original/    — original frames (PNG)
  scripts/bust-test/<name>/patched/     — stabilized frames (PNG)
  scripts/bust-test/<name>/mask/        — debug masks (PNG)
  scripts/bust-test/<name>/speaking.webp — reassembled patched sprite sheet
  scripts/bust-test/viewer.html         — interactive comparison viewer
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AVATARS_DIR = Path(__file__).resolve().parent.parent / "examples" / "web-demo" / "public" / "avatars"
OUTPUT_DIR = Path(__file__).resolve().parent / "bust-test"
FRAME_COUNT = 4

# Per-avatar overrides: (cx, cy, radius_x, radius_y) as fractions of frame size.
# None = use auto-detection. Only override avatars that need fixing.
AVATAR_MOUTH = {
    "bm_george":  {"cx": 0.50, "cy": 0.26, "smooth": 0},  # mouth at 25%, subtle diff
    "af_heart":   {"cx": 0.50, "cy": 0.29},                # mouth at 29%
    "am_michael": {"rx": 0.20, "ry": 0.08},                # slightly larger mask
}


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def load_frames(sprite_path: Path) -> list[np.ndarray]:
    """Load sprite sheet and split into individual frames (RGBA uint8 arrays)."""
    img = Image.open(sprite_path).convert("RGBA")
    w, h = img.size
    frame_w = w // FRAME_COUNT
    frames = []
    for i in range(FRAME_COUNT):
        crop = img.crop((i * frame_w, 0, (i + 1) * frame_w, h))
        frames.append(np.array(crop))
    return frames


def compute_diff_map(base: np.ndarray, frame: np.ndarray) -> np.ndarray:
    """Per-pixel difference intensity (sum of |dR|+|dG|+|dB|), ignoring alpha."""
    diff = np.abs(base[:, :, :3].astype(np.int16) - frame[:, :, :3].astype(np.int16))
    return diff.sum(axis=2).astype(np.float32)  # shape: (H, W), range 0..765


def find_face_mask(
    diff_map: np.ndarray,
    base_rgb: np.ndarray,
    threshold: float,
    dilate_px: int,
    blur_px: int,
    avatar_name: str = "",
) -> np.ndarray:
    """Create soft mouth-only mask using position of strongest changes.

    Only the mouth should animate. Eyes, eyebrows, nose, cheeks all come
    from the base frame to avoid AI-generated positional jitter.

    Returns float32 array (H, W) in range [0, 1].
    """
    h, w = diff_map.shape
    overrides = AVATAR_MOUTH.get(avatar_name, {})

    # --- Step 1: Find mouth position ---
    if "cx" in overrides:
        # Use manual override
        cx = int(w * overrides["cx"])
    else:
        # Auto-detect: centroid of top-2% changes in mouth zone (25-55%)
        mouth_top = int(h * 0.25)
        mouth_bot = int(h * 0.55)
        mouth_zone = diff_map[mouth_top:mouth_bot, :]
        nonzero = mouth_zone[mouth_zone > 0]
        if nonzero.size < 10:
            return np.zeros(diff_map.shape, dtype=np.float32)
        p98 = np.percentile(nonzero, 98)
        strong = mouth_zone >= max(p98, 30)
        if strong.sum() < 5:
            return np.zeros(diff_map.shape, dtype=np.float32)
        _, xs = np.where(strong)
        cx = int(np.average(xs, weights=mouth_zone[strong]))

    if "cy" in overrides:
        cy = int(h * overrides["cy"])
    else:
        mouth_top = int(h * 0.25)
        mouth_bot = int(h * 0.55)
        mouth_zone = diff_map[mouth_top:mouth_bot, :]
        nonzero = mouth_zone[mouth_zone > 0]
        if nonzero.size < 10:
            return np.zeros(diff_map.shape, dtype=np.float32)
        p98 = np.percentile(nonzero, 98)
        strong = mouth_zone >= max(p98, 30)
        if strong.sum() < 5:
            return np.zeros(diff_map.shape, dtype=np.float32)
        ys, _ = np.where(strong)
        cy = mouth_top + int(np.average(ys, weights=mouth_zone[strong]))

    # --- Step 2: Solid ellipse around mouth ---
    rx_frac = overrides.get("rx", 0.17)
    ry_frac = overrides.get("ry", 0.065)
    radius_x = max(int(w * rx_frac), 15)
    radius_y = max(int(h * ry_frac), 10)

    yy, xx = np.ogrid[:h, :w]
    ellipse = ((yy - cy) / max(radius_y, 1)) ** 2 + ((xx - cx) / max(radius_x, 1)) ** 2
    mouth_mask = (ellipse <= 1.0).astype(np.uint8)

    # --- Step 3: Gaussian blur → soft feathered edges ---
    mask_img = Image.fromarray((mouth_mask * 255).astype(np.uint8), mode="L")
    blurred = mask_img.filter(ImageFilter.GaussianBlur(radius=blur_px))
    soft_mask = np.array(blurred).astype(np.float32) / 255.0

    return soft_mask


def composite(base: np.ndarray, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Blend frame over base using soft mask. ALL channels including alpha."""
    mask_4ch = mask[:, :, np.newaxis]  # (H, W, 1) for broadcasting
    # Blend ALL 4 channels (RGBA) — outside mask, everything is 100% base
    result = base.astype(np.float32) * (1.0 - mask_4ch) + frame.astype(np.float32) * mask_4ch
    return np.clip(result, 0, 255).astype(np.uint8)


def smooth_jitter(
    base: np.ndarray, result: np.ndarray, mask: np.ndarray, gate_threshold: float = 30.0
) -> np.ndarray:
    """Suppress subtle pixel jitter within the face mask.

    Within the masked region, pixels whose diff from base is small (below
    gate_threshold) get pulled back toward the base frame. Large changes
    (mouth opening) are preserved fully. This creates a "soft gate":

      diff < gate_threshold → blend toward base (suppress jitter)
      diff >= gate_threshold → keep as-is (real animation)

    The gate ramps linearly: at diff=0 → 100% base, at diff=gate_threshold → 100% result.
    """
    # Per-pixel RGB distance from base
    diff = np.abs(
        result[:, :, :3].astype(np.float32) - base[:, :, :3].astype(np.float32)
    ).sum(axis=2)

    # Soft gate: 0 → use base, 1 → keep result
    gate = np.clip(diff / gate_threshold, 0.0, 1.0)

    # Apply gate only within mask (outside mask is already base)
    effective = gate * mask
    eff_4ch = effective[:, :, np.newaxis]

    # Blend ALL channels including alpha — outside mask, 100% base
    smoothed = base.astype(np.float32) * (1.0 - eff_4ch) + result.astype(np.float32) * eff_4ch
    return np.clip(smoothed, 0, 255).astype(np.uint8)


def stabilize_frames(
    frames: list[np.ndarray],
    threshold: float = 60.0,
    dilate_px: int = 4,
    blur_px: int = 8,
    smooth: float = 0.0,
    avatar_name: str = "",
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Stabilize speaking frames against frame 0 (base).

    Args:
        smooth: Jitter suppression gate threshold. 0 = disabled.
                Values 20-40 work well. Higher = more aggressive smoothing.

    Returns (patched_frames, masks) where masks are for debug visualization.
    """
    base = frames[0]
    patched = [base.copy()]  # Frame 0 is unchanged
    masks = [np.zeros(base.shape[:2], dtype=np.float32)]  # No mask for base

    # Compute ONE shared mask from the max diff across all speaking frames.
    # The face doesn't move between frames — the mask should be identical.
    diff_maps = [compute_diff_map(base, f) for f in frames[1:]]
    combined_diff = np.maximum.reduce(diff_maps)
    shared_mask = find_face_mask(combined_diff, base[:, :, :3], threshold, dilate_px, blur_px, avatar_name=avatar_name)

    for i in range(1, len(frames)):
        result = composite(base, frames[i], shared_mask)

        # Per-avatar smooth override (e.g., george has subtle mouth, smooth kills it)
        overrides = AVATAR_MOUTH.get(avatar_name, {})
        effective_smooth = overrides.get("smooth", smooth)
        if effective_smooth > 0:
            result = smooth_jitter(base, result, shared_mask, gate_threshold=effective_smooth)

        patched.append(result)
        masks.append(shared_mask)

    return patched, masks


def reassemble_sprite(frames: list[np.ndarray]) -> Image.Image:
    """Reassemble individual frames into a horizontal sprite sheet."""
    h, w = frames[0].shape[:2]
    total_w = w * len(frames)
    sheet = Image.new("RGBA", (total_w, h))
    for i, frame in enumerate(frames):
        sheet.paste(Image.fromarray(frame), (i * w, 0))
    return sheet


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def save_debug_output(
    name: str,
    original_frames: list[np.ndarray],
    patched_frames: list[np.ndarray],
    masks: list[np.ndarray],
    output_dir: Path,
):
    """Save original, patched, and mask images for debugging."""
    for subdir in ["original", "patched", "mask", "diff"]:
        (output_dir / name / subdir).mkdir(parents=True, exist_ok=True)

    for i, (orig, patch, mask) in enumerate(zip(original_frames, patched_frames, masks)):
        Image.fromarray(orig).save(output_dir / name / "original" / f"frame{i}.png")
        Image.fromarray(patch).save(output_dir / name / "patched" / f"frame{i}.png")
        # Mask as red overlay for visualization
        mask_vis = np.zeros((*mask.shape, 4), dtype=np.uint8)
        mask_vis[:, :, 0] = (mask * 255).astype(np.uint8)  # Red channel
        mask_vis[:, :, 3] = (mask * 180).astype(np.uint8)  # Semi-transparent
        Image.fromarray(mask_vis).save(output_dir / name / "mask" / f"frame{i}.png")
        # Diff visualization (amplified)
        if i > 0:
            diff = np.abs(orig[:, :, :3].astype(np.int16) - original_frames[0][:, :, :3].astype(np.int16))
            diff_vis = np.clip(diff * 5, 0, 255).astype(np.uint8)  # 5x amplified
            Image.fromarray(diff_vis).save(output_dir / name / "diff" / f"frame{i}.png")

    # Save patched sprite sheet
    sprite = reassemble_sprite(patched_frames)
    sprite.save(output_dir / name / "speaking.webp", quality=90)


def generate_viewer_html(avatars: list[str], output_dir: Path):
    """Generate interactive HTML viewer for comparing original vs patched."""
    avatar_js = ",\n    ".join(f'{{ name: "{a}", label: "{a}" }}' for a in avatars)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bust Stabilization — Before / After</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0a0a0f; color: #e0e0e0;
    display: flex; flex-direction: column; align-items: center;
    padding: 2rem; min-height: 100vh;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.5rem; background: linear-gradient(135deg, #6366f1, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .controls {{
    display: flex; gap: 0.5rem; flex-wrap: wrap;
    justify-content: center; margin-bottom: 1.5rem;
  }}
  .controls button {{
    padding: 0.4rem 0.9rem; border-radius: 0.5rem;
    border: 1px solid rgba(255,255,255,0.1);
    background: rgba(255,255,255,0.05); color: #ccc;
    cursor: pointer; font-size: 0.8rem; transition: all 0.2s;
  }}
  .controls button:hover {{ background: rgba(99,102,241,0.2); border-color: rgba(99,102,241,0.4); }}
  .controls button.active {{ background: rgba(99,102,241,0.3); border-color: #6366f1; color: #fff; }}
  .params {{
    display: flex; gap: 1.5rem; margin-bottom: 1.5rem;
    font-size: 0.75rem; color: #888;
  }}
  .params label {{ display: flex; align-items: center; gap: 0.4rem; }}
  .params input[type=range] {{ width: 80px; accent-color: #6366f1; }}
  .params span {{ color: #6366f1; font-family: monospace; min-width: 2ch; }}
  .comparison {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 1.5rem; max-width: 900px; width: 100%;
  }}
  .panel {{
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 1rem; padding: 1rem; text-align: center;
  }}
  .panel h2 {{ font-size: 0.9rem; margin-bottom: 0.8rem; color: #aaa; }}
  .panel canvas {{
    max-width: 100%; height: auto; border-radius: 0.5rem;
    background: repeating-conic-gradient(#1a1a2e 0% 25%, #12121f 0% 50%) 0 0 / 20px 20px;
  }}
  .frame-info {{ font-size: 0.7rem; color: #666; margin-top: 0.4rem; font-family: monospace; }}
  .masks {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem; max-width: 900px; width: 100%;
    margin-top: 1.5rem;
  }}
  .masks h2 {{ grid-column: 1 / -1; font-size: 0.9rem; color: #aaa; text-align: center; }}
  .mask-cell {{ text-align: center; }}
  .mask-cell canvas {{
    max-width: 100%; border-radius: 0.4rem;
    background: #0f0f17; border: 1px solid rgba(255,255,255,0.05);
  }}
  .mask-cell .label {{ font-size: 0.65rem; color: #666; margin-top: 0.2rem; }}
  .play-controls {{
    display: flex; gap: 0.5rem; justify-content: center;
    margin-bottom: 1rem;
  }}
  .play-controls button {{
    padding: 0.4rem 1.2rem; border-radius: 0.5rem;
    border: 1px solid rgba(99,102,241,0.3);
    background: rgba(99,102,241,0.15); color: #a5b4fc;
    cursor: pointer; font-size: 0.8rem; transition: all 0.2s;
  }}
  .play-controls button:hover {{ background: rgba(99,102,241,0.3); }}
  .play-controls button.active {{ background: #6366f1; color: #fff; }}
</style>
</head>
<body>

<h1>Bust Stabilization Viewer</h1>
<p class="subtitle">Face-Only Delta Patch — compare original vs stabilized frames</p>

<div class="controls" id="avatar-buttons"></div>

<div class="play-controls">
  <button id="btn-play" onclick="togglePlay()">&#9654; Play</button>
  <button id="btn-prev" onclick="stepFrame(-1)">&#9664; Prev</button>
  <button id="btn-next" onclick="stepFrame(1)">Next &#9654;</button>
</div>

<div class="params">
  <label>FPS: <input type="range" id="fps-slider" min="2" max="20" value="8" oninput="updateFps(this.value)"> <span id="fps-val">8</span></label>
</div>

<div class="comparison">
  <div class="panel">
    <h2>Original</h2>
    <canvas id="canvas-orig"></canvas>
    <div class="frame-info" id="info-orig"></div>
  </div>
  <div class="panel">
    <h2>Stabilized</h2>
    <canvas id="canvas-patched"></canvas>
    <div class="frame-info" id="info-patched"></div>
  </div>
</div>

<div class="masks">
  <h2>Masks &amp; Diffs (frames 1-3)</h2>
  <div class="mask-cell"><canvas id="mask-1"></canvas><div class="label">Mask F1</div></div>
  <div class="mask-cell"><canvas id="mask-2"></canvas><div class="label">Mask F2</div></div>
  <div class="mask-cell"><canvas id="mask-3"></canvas><div class="label">Mask F3</div></div>
  <div class="mask-cell"><canvas id="diff-vis"></canvas><div class="label">Diff (5x)</div></div>
</div>

<script>
const AVATARS = [
    {avatar_js}
];

const FRAME_COUNT = 4;
let currentAvatar = AVATARS[0].name;
let origFrames = [];
let patchedFrames = [];
let maskFrames = [];
let diffFrames = [];
let currentFrame = 0;
let direction = 1;
let playing = false;
let animInterval = null;
let fps = 8;

// Ping-pong sequence (skip frame 0 for speaking)
const speakSeq = [1, 2, 3, 2, 1];
let seqIdx = 0;

function loadImage(src) {{
  return new Promise((resolve, reject) => {{
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  }});
}}

async function loadAvatar(name) {{
  currentAvatar = name;
  origFrames = [];
  patchedFrames = [];
  maskFrames = [];
  diffFrames = [];

  for (let i = 0; i < FRAME_COUNT; i++) {{
    origFrames.push(await loadImage(name + '/original/frame' + i + '.png'));
    patchedFrames.push(await loadImage(name + '/patched/frame' + i + '.png'));
    if (i > 0) {{
      maskFrames.push(await loadImage(name + '/mask/frame' + i + '.png'));
      try {{ diffFrames.push(await loadImage(name + '/diff/frame' + i + '.png')); }} catch(e) {{}}
    }}
  }}

  // Draw masks
  for (let m = 0; m < 3; m++) {{
    const mc = document.getElementById('mask-' + (m + 1));
    if (maskFrames[m]) drawToCanvas(mc, maskFrames[m]);
  }}
  if (diffFrames.length > 0) {{
    drawToCanvas(document.getElementById('diff-vis'), diffFrames[diffFrames.length - 1]);
  }}

  seqIdx = 0;
  currentFrame = 0;
  renderFrame();
  updateButtons();
}}

function drawToCanvas(canvas, img) {{
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
}}

function renderFrame() {{
  const f = currentFrame;
  if (origFrames[f]) drawToCanvas(document.getElementById('canvas-orig'), origFrames[f]);
  if (patchedFrames[f]) drawToCanvas(document.getElementById('canvas-patched'), patchedFrames[f]);
  document.getElementById('info-orig').textContent = 'Frame ' + f + ' / ' + (FRAME_COUNT - 1);
  document.getElementById('info-patched').textContent = 'Frame ' + f + ' / ' + (FRAME_COUNT - 1);
}}

function stepFrame(dir) {{
  if (playing) return;
  currentFrame = Math.max(0, Math.min(FRAME_COUNT - 1, currentFrame + dir));
  renderFrame();
}}

function togglePlay() {{
  playing = !playing;
  document.getElementById('btn-play').classList.toggle('active', playing);
  document.getElementById('btn-play').innerHTML = playing ? '&#9724; Stop' : '&#9654; Play';
  if (playing) {{
    seqIdx = 0;
    animInterval = setInterval(() => {{
      currentFrame = speakSeq[seqIdx];
      seqIdx = (seqIdx + 1) % speakSeq.length;
      renderFrame();
    }}, 1000 / fps);
  }} else {{
    clearInterval(animInterval);
    animInterval = null;
  }}
}}

function updateFps(val) {{
  fps = parseInt(val);
  document.getElementById('fps-val').textContent = val;
  if (playing) {{
    clearInterval(animInterval);
    animInterval = setInterval(() => {{
      currentFrame = speakSeq[seqIdx];
      seqIdx = (seqIdx + 1) % speakSeq.length;
      renderFrame();
    }}, 1000 / fps);
  }}
}}

function updateButtons() {{
  document.querySelectorAll('.controls button').forEach(b => {{
    b.classList.toggle('active', b.dataset.avatar === currentAvatar);
  }});
}}

// Init
const btnContainer = document.getElementById('avatar-buttons');
AVATARS.forEach(a => {{
  const btn = document.createElement('button');
  btn.textContent = a.label;
  btn.dataset.avatar = a.name;
  btn.onclick = () => loadAvatar(a.name);
  btnContainer.appendChild(btn);
}});

loadAvatar(AVATARS[0].name);
</script>
</body>
</html>"""
    (output_dir / "viewer.html").write_text(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_avatar(
    name: str, threshold: float, dilate_px: int, blur_px: int,
    smooth: float = 0.0, apply: bool = False,
) -> bool:
    """Process a single avatar. Returns True on success."""
    sprite_path = AVATARS_DIR / name / "speaking.webp"
    if not sprite_path.exists():
        print(f"  SKIP {name}: no speaking.webp")
        return False

    print(f"  Processing {name}...")
    frames = load_frames(sprite_path)
    h, w = frames[0].shape[:2]
    print(f"    {len(frames)} frames, {w}x{h}px")

    patched, masks = stabilize_frames(frames, threshold, dilate_px, blur_px, smooth=smooth, avatar_name=name)

    # Stats: mask coverage + stabilization effectiveness
    base = frames[0]
    alpha_visible = base[:, :, 3] > 10
    visible_total = alpha_visible.sum()
    for i in range(1, len(frames)):
        mask = masks[i]
        coverage = (mask > 0.01).sum() / mask.size * 100

        orig_diff = np.abs(base[:, :, :3].astype(int) - frames[i][:, :, :3].astype(int)).sum(axis=2)
        patch_diff = np.abs(base[:, :, :3].astype(int) - patched[i][:, :, :3].astype(int)).sum(axis=2)
        orig_pct = (orig_diff[alpha_visible] > 5).sum() / visible_total * 100
        patch_pct = (patch_diff[alpha_visible] > 5).sum() / visible_total * 100
        reduction = (1 - patch_pct / orig_pct) * 100 if orig_pct > 0 else 0

        print(f"    Frame {i}: mask={coverage:.0f}%, changed {orig_pct:.0f}%→{patch_pct:.0f}% (reduction {reduction:.0f}%)")

    save_debug_output(name, frames, patched, masks, OUTPUT_DIR)

    # Apply: overwrite original sprite sheet with stabilized version
    if apply:
        sprite = reassemble_sprite(patched)
        sprite.save(sprite_path, quality=90)
        print(f"    APPLIED → {sprite_path}")
    else:
        print(f"    Preview → {OUTPUT_DIR / name}/")
    return True


def main():
    parser = argparse.ArgumentParser(description="Stabilize AI-generated speaking bust sprites")
    parser.add_argument("--avatar", type=str, help="Process single avatar (e.g., af_bella)")
    parser.add_argument("--threshold", type=float, default=60.0, help="Pixel diff threshold (default: 60)")
    parser.add_argument("--dilate", type=int, default=4, help="Mask dilation iterations (default: 4)")
    parser.add_argument("--blur", type=int, default=8, help="Gaussian blur radius for mask edges (default: 8)")
    parser.add_argument("--smooth", type=float, default=0.0,
                        help="Jitter suppression gate threshold (0=off, 20-40 recommended)")
    parser.add_argument("--preview", action="store_true", help="Generate HTML viewer only (no processing)")
    parser.add_argument("--apply", action="store_true", help="Overwrite original sprite sheets with stabilized versions")
    args = parser.parse_args()

    print("=== Bust Stabilization: Face-Only Delta Patch ===")
    print(f"  Params: threshold={args.threshold}, dilate={args.dilate}, blur={args.blur}, smooth={args.smooth}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # Clean output dir
    if OUTPUT_DIR.exists() and not args.preview:
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.preview:
        # Discover avatars
        if args.avatar:
            avatar_names = [args.avatar]
        else:
            avatar_names = sorted(
                d.name for d in AVATARS_DIR.iterdir()
                if d.is_dir() and (d / "speaking.webp").exists()
            )

        print(f"Avatars to process: {', '.join(avatar_names)}")
        print()

        processed = []
        for name in avatar_names:
            if process_avatar(name, args.threshold, args.dilate, args.blur,
                             smooth=args.smooth, apply=args.apply):
                processed.append(name)
    else:
        processed = sorted(
            d.name for d in OUTPUT_DIR.iterdir()
            if d.is_dir() and (d / "patched").exists()
        )

    # Generate HTML viewer
    if processed:
        generate_viewer_html(processed, OUTPUT_DIR)
        print(f"\nViewer: {OUTPUT_DIR / 'viewer.html'}")
    else:
        print("\nNo avatars processed.")

    print("Done!")


if __name__ == "__main__":
    main()
