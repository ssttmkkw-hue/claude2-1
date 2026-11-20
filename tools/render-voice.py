"""Pre-render the stand-up lines to MP3 so the show plays in browsers without
speechSynthesis (WeChat's built-in browser, many Android WebViews).

Requires: pip install sherpa-onnx numpy ; ffmpeg ; node
Model:    kokoro-multi-lang-v1_0 from
          https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2

Usage:    python3 tools/render-voice.py --model /path/to/kokoro-multi-lang-v1_0 [--sid 47] [--speed 1.05]

Writes voice/NN.mp3 (one file per script line) and voice/voice.json with each
line's duration and a 40 ms loudness envelope used for lip sync.
"""
import argparse
import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx as sherpa

ROOT = Path(__file__).resolve().parents[1]
FRAME = 0.04  # seconds per envelope sample


def script_lines():
    src = (ROOT / "src/app.html").read_text(encoding="utf-8")
    block = src[src.index("const SCRIPT = ["):src.index("const ROLE_ZH")]
    code = block.replace("const SCRIPT = ", "console.log(JSON.stringify(", 1).rstrip().rstrip(";") + "))"
    return json.loads(subprocess.check_output(["node", "-e", code], text=True))


def engine(model_dir: Path):
    kokoro = sherpa.OfflineTtsKokoroModelConfig(
        model=str(model_dir / "model.onnx"),
        voices=str(model_dir / "voices.bin"),
        tokens=str(model_dir / "tokens.txt"),
        data_dir=str(model_dir / "espeak-ng-data"),
        dict_dir=str(model_dir / "dict"),
        lexicon=f"{model_dir / 'lexicon-us-en.txt'},{model_dir / 'lexicon-zh.txt'}",
    )
    cfg = sherpa.OfflineTtsConfig(
        model=sherpa.OfflineTtsModelConfig(kokoro=kokoro, num_threads=4),
        rule_fsts=f"{model_dir / 'date-zh.fst'},{model_dir / 'number-zh.fst'},{model_dir / 'phone-zh.fst'}",
    )
    return sherpa.OfflineTts(cfg)


def speakable(text: str) -> str:
    t = re.sub(r"[“”\"「」]", "", text)
    t = t.replace("AI", "A I").replace("4K", "四K").replace("token", "偷肯")
    return t


def trim(x: np.ndarray, rate: int) -> np.ndarray:
    peak = float(np.max(np.abs(x))) or 1.0
    idx = np.flatnonzero(np.abs(x) > peak * 0.02)
    x = x[max(0, idx[0] - int(0.03 * rate)): idx[-1] + int(0.08 * rate)]
    fade = int(0.01 * rate)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x * (0.89 / peak)


def envelope(x: np.ndarray, rate: int) -> list:
    n = int(FRAME * rate)
    frames = [float(np.sqrt(np.mean(x[i:i + n] ** 2))) for i in range(0, len(x), n)]
    top = max(frames) or 1.0
    return [round(min(1.0, v / top * 1.25), 2) for v in frames]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--sid", type=int, default=47, help="47 = zf_xiaoxiao")
    ap.add_argument("--speed", type=float, default=1.05)
    args = ap.parse_args()

    out = ROOT / "voice"
    out.mkdir(exist_ok=True)
    tts = engine(args.model)
    manifest = {"frame": FRAME, "lines": []}
    for i, line in enumerate(script_lines()):
        audio = tts.generate(speakable(line["t"]), sid=args.sid, speed=args.speed)
        rate = audio.sample_rate
        x = trim(np.array(audio.samples, dtype=np.float32), rate)
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            with wave.open(tmp.name, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
                w.writeframes((x * 32767).astype(np.int16).tobytes())
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp.name,
                            "-ac", "1", "-b:a", "48k", str(out / f"{i:02d}.mp3")], check=True)
        manifest["lines"].append({"file": f"{i:02d}.mp3", "dur": round(len(x) / rate, 2), "env": envelope(x, rate)})
        print(f"{i:02d} {len(x) / rate:5.2f}s  {line['t']}")
    (out / "voice.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
