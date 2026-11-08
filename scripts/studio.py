#!/usr/bin/env python3
"""Local media helpers. Editorial decisions remain in the project's edit plan."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "studio.config.json").read_text(encoding='utf-8'))
sys.path.insert(0, str(ROOT / "style-library"))
from new_project import brief_section  # noqa: E402  (needs the sys.path insert above)


def run(args, capture=False):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          capture_output=capture)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')


def probe(source):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", source], capture=True).stdout)


def seconds(value):
    if isinstance(value, bool):
        raise ValueError("A time cannot be a boolean")
    parts = str(value).split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Invalid time: {value}")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    if not math.isfinite(total) or total < 0:
        raise ValueError(f"Invalid time: {value}")
    return total


def timecode(value):
    millis = round(value * 1000)
    hours, rest = divmod(millis, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


def project_source(project, source):
    project = project.resolve()
    source = source.resolve()
    if not source.is_relative_to(project / "raw") or not source.is_file():
        raise ValueError("Source must be an existing file inside this project's raw folder")
    return source


def fresh(path):
    if path.exists():
        raise ValueError(f"Output already exists: {path}. Choose a new version.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def doctor(_):
    report = {"python": sys.version.split()[0], "tools": {}, "python_packages": {}}
    for tool in ["ffmpeg", "ffprobe", "node", "npm"]:
        report["tools"][tool] = shutil.which(tool)
    for package in ["PIL"]:
        report["python_packages"][package] = bool(importlib.util.find_spec(package))
    report["hyperframes"] = (ROOT / "node_modules/.bin/hyperframes").exists()
    print(json.dumps(report, indent=2))
    if not all(report["tools"].values()) or not report["hyperframes"]:
        raise SystemExit(1)
    if not all(report["python_packages"].values()):
        venv_python = '.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python'
        print(f"Use {venv_python} for media prep and transcription.", file=sys.stderr)
        raise SystemExit(1)


def new_project(args):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        raise ValueError("Use a project slug such as brand-product-01")
    project = ROOT / "projects" / args.slug
    project.mkdir(parents=True, exist_ok=False)
    for folder in ["raw", "broll", "audio", "graphics/assets", "work", "exports"]:
        (project / folder).mkdir(parents=True, exist_ok=True)
    for name in ["STATUS.md", "STORYBOARD.md", "selects.csv", "sound-cues.csv", "asset-ledger.csv", "edit-plan.json"]:
        shutil.copy2(ROOT / "templates" / name, project / name)
    # templates/brief.md now wraps its Hebrew/English sections in <!-- lang:.. -->
    # markers (Task 7); this scaffold has no language choice of its own and already
    # writes everything else in English, so pull just the English section rather than
    # copying the file verbatim and leaking both languages' wrapper markers into it.
    (project / "brief.md").write_text(brief_section("en"), encoding='utf-8')
    (project / "script.txt").write_text("Paste the supplied original script here.\n", encoding='utf-8')
    (project / "assembled-script.txt").write_text("Pending take selection.\n", encoding='utf-8')
    (project / "review-notes.md").write_text("# Review notes\n\nNo footage reviewed yet.\n", encoding='utf-8')
    write_json(project / "media-manifest.json", {"version": 1, "sources": []})
    descriptor = {"id": args.slug, "title": args.slug.replace("-", " ").title(), "subtitle": "New project", "format": "video", "state": "in_progress", "stage": "intake", "summary": "Bring your footage, script and references to the editing chat.", "next_step": "Establish the spoken cut before storyboarding.", "primary_artifact": "intake", "source_notes": [{"path": "STATUS.md", "label": "Current status"}], "artifacts": [{"id": "intake", "label": "Project notes", "type": "document", "path": "STATUS.md", "version": "V01", "role": "current"}]}
    write_json(project / "studio-entry.json", descriptor)
    run([sys.executable, ROOT / "scripts/register.py", "project", project / "studio-entry.json"])
    print(project)


def ingest(args):
    project = args.project.resolve()
    manifest_path = project / "media-manifest.json"
    if not manifest_path.exists():
        raise ValueError("Create a project with the new command first")
    source = args.source.resolve(strict=True)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    target = fresh(project / "raw" / source.name)
    metadata = probe(source)
    shutil.copy2(source, target)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest["sources"].append({"file": target.relative_to(project).as_posix(),
                                "sha256": digest.hexdigest(), "bytes": target.stat().st_size,
                                "probe": metadata})
    write_json(manifest_path, manifest)
    print(target)


def prepare(args):
    source = project_source(args.project, args.source)
    info = probe(source)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("No video stream found")
    duration = float(info["format"]["duration"])
    start = seconds(args.start)
    end = min(seconds(args.end), duration) if args.end is not None else duration
    if not 0 <= start < end or args.interval <= 0 or args.max_frames <= 0:
        raise ValueError("Require 0 <= start < end, positive interval, and positive max-frames")
    folder = args.project.resolve() / "work" / source.stem
    if folder.exists():
        raise ValueError(f"Review folder exists: {folder}. Use a distinct source stem or archive the prior review.")
    folder.mkdir(parents=True)
    write_json(folder / "probe.json", info)
    hdr = video.get("color_transfer") in ["smpte2084", "arib-std-b67"]
    if hdr:
        (folder / "HDR-REVIEW-REQUIRED.txt").write_text(
            "HDR detected. Proxy is for timing only; its color is not approved. Plan SDR conversion before export.\n", encoding='utf-8')
    edge = CONFIG["review"]["proxy_long_edge"]
    scale = f"scale='if(gte(iw,ih),min(iw,{edge}),-2)':'if(gte(iw,ih),-2,min(ih,{edge}))'"
    run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", source,
         "-map", "0:v:0", "-map", "0:a:0?", "-vf", scale,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", folder / "proxy.mp4"])
    if any(s["codec_type"] == "audio" for s in info["streams"]):
        run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", source,
             "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", folder / "audio.wav"])
        detection = run(["ffmpeg", "-nostdin", "-hide_banner", "-i", source, "-vn",
                         "-af", "silencedetect=noise=-35dB:d=0.35", "-f", "null", "-"], capture=True)
        (folder / "silence-candidates.log").write_text(detection.stderr, encoding='utf-8')
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=16)
    # Independent seeks keep the label tied to the requested original source time.
    timestamps = []
    count = min(math.ceil((end - start) / args.interval), args.max_frames)
    tiles = []
    with tempfile.TemporaryDirectory(prefix="frames-", dir=folder) as tmp:
        for index in range(count):
            moment = start + index * args.interval
            frame = Path(tmp) / f"{index:04}.jpg"
            run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-ss", f"{moment:.6f}",
                 "-i", source, "-frames:v", "1", "-vf", "scale=320:-2", frame])
            if not frame.exists():
                continue
            with Image.open(frame) as opened:
                image = opened.convert("RGB")
                image.thumbnail((320, 400))
                tile = Image.new("RGB", (336, 432), "#15181d")
                tile.paste(image, ((336 - image.width) // 2, 8))
                ImageDraw.Draw(tile).text((8, 410), timecode(moment), font=font, fill="white")
                tiles.append(tile)
            timestamps.append({"index": index, "source_seconds": moment})
        for page in range(math.ceil(len(tiles) / 12)):
            subset = tiles[page * 12:(page + 1) * 12]
            sheet = Image.new("RGB", (1008, 432 * math.ceil(len(subset) / 3)), "#101216")
            for index, tile in enumerate(subset):
                sheet.paste(tile, ((index % 3) * 336, (index // 3) * 432))
            sheet.save(folder / f"contact-sheet-{page + 1:02}.jpg", quality=90)
    write_json(folder / "frames.json", {"source": str(source), "frames": timestamps,
               "sample_interval": args.interval, "requested_end": end,
               "truncated": count < math.ceil((end - start) / args.interval),
               "note": "Frame seeks are approximate to the source frame boundary. Inspect proxy/candidates for motion."})
    print(folder)


def assemble(args):
    project = args.project.resolve()
    plan = json.loads((project / "edit-plan.json").read_text(encoding='utf-8'))
    cuts = plan["cuts"]
    if not cuts:
        raise ValueError("No chosen cuts in edit-plan.json")
    settings = {**CONFIG["format"], **plan.get("output", {})}
    width, height, fps = (int(settings[k]) for k in ["width", "height", "fps"])
    if width <= 0 or height <= 0 or fps <= 0 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be positive/even; fps must be positive")
    crf = int(settings.get("crf", CONFIG["delivery"]["crf"]))
    output = fresh(args.output or project / "exports" / "assembly-v01.mp4")
    if output.resolve().is_relative_to(project / "raw"):
        raise ValueError("Cannot write exports into raw")
    map_path = fresh(output.with_suffix(".time-map.json"))
    script_path = fresh(output.with_suffix(".spoken-script.txt"))
    validated = []
    for index, cut in enumerate(cuts):
        source = project_source(project, project / cut["source"])
        info = probe(source)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        if video.get("color_transfer") in ["smpte2084", "arib-std-b67"]:
            raise ValueError(f"HDR source requires a deliberate SDR conversion before assembly: {source}")
        start, end = seconds(cut["source_in"]), seconds(cut["source_out"])
        if not start < end <= float(info["format"]["duration"]) + 0.001:
            raise ValueError(f"Cut {index + 1}: source range is outside the media duration")
        frames = max(1, round((end - start) * fps))
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        validated.append((cut, source, start, end, frames, has_audio))
    timeline, position = [], 0.0
    with tempfile.TemporaryDirectory(prefix="assembly-", dir=project / "work") as tmp:
        folder = Path(tmp)
        for index, (cut, source, start, end, frames, has_audio) in enumerate(validated):
            length = frames / fps
            part = folder / f"{index:04}.mov"
            vf = (f"trim=start={start}:end={end},setpts=PTS-STARTPTS,"
                  f"fps={fps}:start_time=0,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                  f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                  f"tpad=stop_mode=clone:stop_duration={1/fps},trim=end_frame={frames},setpts=N/({fps}*TB)")
            af = (f"atrim=start={start}:end={end},asetpts=PTS-STARTPTS,aresample=48000,"
                  f"apad,atrim=duration={length},aformat=channel_layouts=stereo")
            command = ["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", source]
            if not has_audio:
                command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                af = f"atrim=duration={length},asetpts=PTS-STARTPTS"
            command += ["-filter_complex", f"[0:v:0]{vf}[v];[{0 if has_audio else 1}:a:0]{af}[a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
                        "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-ar", "48000", part]
            run(command)
            timeline.append({"cut": index + 1, "beat_id": cut.get("beat_id"),
                             "source": cut["source"], "source_in": start, "source_out": end,
                             "output_in": position, "output_out": position + length,
                             "text": cut.get("text", ""), "reason": cut.get("reason", ""),
                             "note": "CFR duration rounded to output frame grid; re-transcribe edited audio for captions."})
            position += length
        concat = folder / "concat.txt"
        concat.write_text("".join(f"file '{index:04}.mov'\n" for index in range(len(validated))), encoding='utf-8')
        run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "concat", "-safe", "1",
             "-i", concat, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
             "-movflags", "+faststart", output])
    write_json(map_path, {"output": str(output), "duration": position, "cuts": timeline})
    script_path.write_text("\n\n".join(cut.get("text", "") for cut in cuts) + "\n", encoding='utf-8')
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor").set_defaults(func=doctor)
    p = sub.add_parser("new"); p.add_argument("slug"); p.set_defaults(func=new_project)
    p = sub.add_parser("ingest"); p.add_argument("project", type=Path); p.add_argument("source", type=Path); p.set_defaults(func=ingest)
    p = sub.add_parser("prepare"); p.add_argument("project", type=Path); p.add_argument("source", type=Path)
    p.add_argument("--start", default="0"); p.add_argument("--end"); p.add_argument("--interval", type=float, default=5)
    p.add_argument("--max-frames", type=int, default=120); p.set_defaults(func=prepare)
    p = sub.add_parser("assemble"); p.add_argument("project", type=Path); p.add_argument("--output", type=Path); p.set_defaults(func=assemble)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
