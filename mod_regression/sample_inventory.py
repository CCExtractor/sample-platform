import json
import subprocess
import hashlib
from pathlib import Path


def _run(cmd):
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None



def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_sample(sample_path: Path) -> dict:
    result = {
        "path": str(sample_path),
        "sha256": sha256sum(sample_path),
        "container": None,
        "streams": [],
        "caption_types_detected": [],
        "duration_sec": None,
    }

    # ---- ffprobe ----
    ffprobe = _run([
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-print_format", "json",
        str(sample_path)
    ])

    if ffprobe and ffprobe.returncode == 0:
        try:
            meta = json.loads(ffprobe.stdout)
            fmt = meta.get("format", {})
            result["container"] = fmt.get("format_name")
            if "duration" in fmt:
                result["duration_sec"] = float(fmt["duration"])

            for s in meta.get("streams", []):
                result["streams"].append({
                    "type": s.get("codec_type"),
                    "codec": s.get("codec_name")
                })
        except (ValueError, KeyError):
            pass

    # ---- CCExtractor ----
    cce = _run([
        "ccextractor",
        str(sample_path),
        "-stdout"
    ])

    if cce and cce.returncode == 0:
        stderr = (cce.stderr or "").lower()
        if "608" in stderr:
            result["caption_types_detected"].append("CEA-608")
        if "708" in stderr:
            result["caption_types_detected"].append("CEA-708")
        if "dvb" in stderr:
            result["caption_types_detected"].append("DVB")

    return result


def inventory_samples(sample_root: Path) -> list:
    inventory = []
    for p in sample_root.rglob("*"):
        if p.is_file():
            inventory.append(probe_sample(p))
    return inventory
