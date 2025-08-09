from genericpath import exists
import math
import shutil
import subprocess
from functools import reduce
from pathlib import Path

# ================== Config ==================

# Grid / render config
FPS = 30
CELL_W = 640
CELL_H = 480
BGHEX = "#F8F8F8"

# Optional vertical phone export; set to (1080, 1920) or None
VERTICAL_TARGET = None  # e.g., (1080, 1920) to scale+pad for phones



SRC_DIR = Path("videos")
CROPPED_DIR = Path("work") / "cropped"
OUT_DIR = Path("out") / "normalized"

# Crop: keep 65% of width & height, anchored at (0,0), even dims
CROP_EXPR = "crop=w=floor(iw*0.65/2)*2:h=floor(ih*0.65/2)*2:x=0:y=0"

BUCKETS = [15.0, 30.0, 45.0]
EPS = 0.5  # tolerance for ~15/~30/~45 reads

def snap_to_bucket(d: float) -> int:
    """Map a noisy duration (e.g., 29.97) to 15/30/45."""
    if d is None:
        return 30
    return int(min(BUCKETS, key=lambda b: abs(d - b)))


# Encoding options for final outputs
VIDEO_CODEC = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
AUDIO_CODEC = ["-c:a", "aac", "-b:a", "192k"]


def compress_video(input_path: Path, output_path: Path, crf: int = 28, preset: str = "slow"):
    """
    Compress a video using H.264 with a given CRF (quality) and preset (speed).
    Lower CRF = higher quality/bigger file. Higher CRF = lower quality/smaller file.
    Typical CRF range: 18 (visually lossless) to 32 (low quality).
    """
    print(f"[*] Compressing {input_path.name} → {output_path.name} (CRF={crf}, preset={preset})")
    run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "128k",  # audio settings
        str(output_path)
    ])
    print(f"[OK] Compressed file written: {output_path}")


# Allowable rounding error for loop detection
EPS = 0.35
# ============================================


def find_out(stem: str) -> Path:
    """
    Find the final normalized output for a given logical stem.
    - For MOV inputs, outputs are '<stem>.mp4'
    - For MP4 inputs that we cropped, outputs are '<stem>_cropped.mp4'
    """
    c1 = OUT_DIR / f"{stem}.mp4"
    c2 = OUT_DIR / f"{stem}_cropped.mp4"
    if c1.exists():
        return c1
    if c2.exists():
        return c2
    raise FileNotFoundError(f"Could not find normalized file for stem '{stem}' (tried {c1.name} and {c2.name})")


def run(cmd):
    subprocess.run(cmd, check=True)

def have_tool(name: str) -> bool:
    try:
        subprocess.run([name, "-version"], capture_output=True, text=True)
        return True
    except FileNotFoundError:
        return False

def ffprobe_duration_seconds(path: Path):
    """Return float seconds or None on failure."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(path)],
            capture_output=True, text=True, check=True
        )
        return float(p.stdout.strip())
    except Exception:
        return None

def lcm(a, b):
    return abs(a * b) // math.gcd(a, b)

def lcm_list(numbers):
    return reduce(lcm, numbers)

def ensure_dirs():
    CROPPED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def crop_if_needed(src: Path) -> Path:
    """
    For .mp4 files:
      - if already *_cropped.mp4, copy into CROPPED_DIR unchanged
      - else crop using 65% window and write *_cropped.mp4 in CROPPED_DIR
    For .mov files:
      - copy into CROPPED_DIR unchanged
    """
    if src.suffix.lower() == ".mov" or src.suffix.lower() == "mp4":
        dst = CROPPED_DIR / (src.stem + src.suffix)
        if not dst.exists():
            print(f"[-] MOV no-crop: {src.name}")
            shutil.copy2(src, dst)
        else:
            print(f"[=] Exists (mov): {dst.name}")
        return dst

    # if src.suffix.lower() == ".mp4":
    #     if src.stem.lower().endswith("_cropped"):
    #         dst = CROPPED_DIR / src.name
    #         if not dst.exists():
    #             print(f"[-] Copy already-cropped mp4: {src.name}")
    #             shutil.copy2(src, dst)
    #         else:
    #             print(f"[=] Exists (already-cropped mp4): {dst.name}")
    #         return dst
    #     else:
    #         dst = CROPPED_DIR / f"{src.stem}_cropped.mp4"
    #         if dst.exists():
    #             print(f"[=] Exists (cropped): {dst.name}")
    #             return dst
    #         print(f"[*] Cropping mp4: {src.name} -> {dst.name}")
    #         run([
    #             "ffmpeg", "-y",
    #             "-hide_banner", "-loglevel", "error",
    #             "-i", str(src),
    #             "-vf", CROP_EXPR,
    #             "-c:a", "copy",  # keep original audio for speed at this stage
    #             str(dst),
    #         ])
    #         return dst

    dst = CROPPED_DIR / src.name
    if not dst.exists():
        print(f"[-] Copy passthrough: {src.name}")
        shutil.copy2(src, dst)
    else:
        print(f"[=] Exists (passthrough): {dst.name}")
    return dst

def normalize_to_lcm(in_path: Path, out_path: Path, target_lcm: int):
    dur = ffprobe_duration_seconds(in_path)
    if dur is None:
        dur = target_lcm
        print(f"[WARN] Unknown duration for {in_path.name} → assuming target {target_lcm}s")

    need_loop = dur < target_lcm - EPS
    loop_count = math.ceil(target_lcm / dur) if need_loop else 0

    input_args = (["-stream_loop", str(loop_count)] if need_loop else []) + ["-i", str(in_path)]

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *input_args,
        "-t", str(target_lcm),
        *VIDEO_CODEC,
        *AUDIO_CODEC,
        "-shortest",
        str(out_path),
    ]
    run(cmd)

def main():
    if not have_tool("ffmpeg") or not have_tool("ffprobe"):
        raise SystemExit("[ERROR] ffmpeg/ffprobe not found in PATH")

    if not SRC_DIR.exists():
        raise SystemExit(f'[ERROR] Source folder "{SRC_DIR}" not found.')

    ensure_dirs()

    # 1) Gather inputs
    sources = sorted([p for p in SRC_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mov"}])
    if not sources:
        raise SystemExit("[ERROR] No .mp4 or .mov files found in videos/")

    # 2) Crop/copy phase
    print(f"\n=== Cropping .mp4s (or copying) into {CROPPED_DIR} ===")
    cropped_paths = []
    for src in sources:
        try:
            cropped_paths.append(crop_if_needed(src))
        except subprocess.CalledProcessError:
            print(f"[FAIL] Crop/Copy failed: {src.name}")

    # 3) Determine LCM duration
    raw_durations = []
    for p in cropped_paths:
        d = ffprobe_duration_seconds(p)
        if d:
            raw_durations.append(d)

    if not raw_durations:
        raise SystemExit("[ERROR] Could not read durations for any files.")

    # Snap to canonical buckets first, then LCM across the unique buckets present
    snapped_buckets = sorted({snap_to_bucket(d) for d in raw_durations})
    target_lcm = lcm_list(snapped_buckets)

    print("\n[i] Durations (raw → snapped):")
    for d in raw_durations:
        print(f"    {d:.2f}s → {snap_to_bucket(d)}s")
    print(f"[i] Buckets present: {snapped_buckets} → LCM target = {target_lcm}s")


    # 4) Normalize all to LCM
    print(f"\n=== Normalizing to {target_lcm}s into {OUT_DIR} ===")
    for p in cropped_paths:
        out_name = p.stem + ".mp4"
        out_path = OUT_DIR / out_name
        if not exists(out_path):
            try:
                normalize_to_lcm(p, out_path, target_lcm)
                print(f"[OK] Wrote: {out_path.name}")
            except subprocess.CalledProcessError:
                print(f"[FAIL] Normalize failed: {p.name}")
        else:
            print(f"[Exists]: {out_name}")

    print("\nDone.")

        # ===== 5) Build 3x3 grid from normalized outputs =====
    # Define the order you want in the 3×3:
    # Top:    explosion [base, thinking, pro]
    # Middle: Ball      [Main,  Thinking,  Pro]
    # Bottom: audio     [base, thinking, pro]
    file_order = [
        "explosion_base", "explosion_thinking", "explosion_pro",
        "Ball - Main",    "Ball - Thinking",    "Ball - Pro",
        "audio_base",     "audio_thinking",     "audio_pro",
    ]
    labels = [
        "Explosion - Base", "Explosion - Thinking", "Explosion - Pro",
        "Ball - Main",      "Ball - Thinking",      "Ball - Pro",
        "Audio - Base",     "Audio - Thinking",     "Audio - Pro",
    ]

    inputs = []
    filter_parts = []

    # Build layout positions for 3×3
    layout_positions = [
        f"0_0", f"{CELL_W}_0", f"{CELL_W*2}_0",
        f"0_{CELL_H}", f"{CELL_W}_{CELL_H}", f"{CELL_W*2}_{CELL_H}",
        f"0_{CELL_H*2}", f"{CELL_W}_{CELL_H*2}", f"{CELL_W*2}_{CELL_H*2}",
    ]

    # Collect inputs (already normalized to LCM, so no per-tile looping now)
    for i, stem in enumerate(file_order):
        p = find_out(stem)
        inputs += ["-i", str(p)]
        filter_parts.append(
            f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},"
            f"scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=decrease,"
            f"pad={CELL_W}:{CELL_H}:(ow-iw)/2:(oh-ih)/2:color={BGHEX},"
            f"drawbox=x=0:y=0:w={CELL_W}:h={CELL_H}:color=black@1.0:t=2,"
            f"drawtext=font='Arial':text='{labels[i]}':x=(w-text_w)/2:y=h-40:fontsize=32:fontcolor=white[v{i}]"
        )

    stack = f"{''.join(f'[v{k}]' for k in range(9))}xstack=inputs=9:layout={'|'.join(layout_positions)}:fill={BGHEX}[vout]"
    filter_complex = ";".join(filter_parts) + ";" + stack

    # Optionally scale/pad for vertical phone export
    map_label = "[vout]"
    if VERTICAL_TARGET:
        tw, th = VERTICAL_TARGET
        filter_complex += (
            f";[vout]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color={BGHEX}[vout2]"
        )
        map_label = "[vout2]"

    OUT_GRID = OUT_DIR.parent / "grid_3x3.mp4"  # e.g., out/grid_3x3.mp4

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", map_label,
        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(OUT_GRID),
    ]
    print(f"\n=== Building 3x3 grid → {OUT_GRID} ===")
    run(cmd)
    print(f"[OK] Wrote grid: {OUT_GRID}")


    # Example: compress the 3×3 grid video
    compressed_grid = OUT_DIR.parent / "grid_3x3_compressed.mp4"
    compress_video(OUT_GRID, compressed_grid, crf=28, preset="slow")

if __name__ == "__main__":
    main()
