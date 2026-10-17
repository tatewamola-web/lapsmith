"""Voice output: a human-sounding race-engineer voice for callouts.

Uses Piper — an open-source neural text-to-speech model that runs locally
(no internet, no API key). Windows' built-in SAPI voices are the robotic
ones; a neural voice is the difference between a sat-nav and an engineer.

Design:
  * one worker thread owns synthesis + playback, so the engine loop never
    blocks on audio
  * every phrase is synthesized once and cached as a WAV — repeats (the
    same callout every lap, "car left") play instantly
  * urgent messages (spotter) cut off whatever is playing and jump the queue
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Piper voice model, downloaded into data/voices (see README)
DEFAULT_MODEL = "en_US-ryan-high.onnx"

_NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def _num(n: str) -> str:
    try:
        i = int(n)
    except ValueError:
        return n
    return _NUMBERS[i] if 0 <= i < len(_NUMBERS) else n


def speakable_corner(label: str) -> str:
    """'T1' -> 'Turn one', 'T4-5' -> 'Turns four and five',
    'T8-9-10' -> 'Turns eight to ten', 'T6b' -> 'Next one'."""
    if not label.startswith("T"):
        return label
    body = label[1:]
    if body.endswith("b"):
        return "Next one"
    parts = body.split("-")
    if len(parts) == 1:
        return f"Turn {_num(parts[0])}"
    if len(parts) == 2:
        return f"Turns {_num(parts[0])} and {_num(parts[1])}"
    return f"Turns {_num(parts[0])} to {_num(parts[-1])}"


def speakable_callout(corner: str, text: str) -> str:
    """Written callout -> how an engineer would say it on the radio.
    'Brake slightly later, throttle sooner' ->
    'Turn one. Brake a touch later, then throttle sooner.'"""
    t = text.replace("slightly", "a touch")
    hints = [h.strip() for h in t.split(",") if h.strip()]
    if not hints:
        return ""
    spoken = hints[0][0].upper() + hints[0][1:]
    if len(hints) > 1:
        spoken += ", then " + hints[1]
    return f"{speakable_corner(corner)}. {spoken}."


class Voice:
    def __init__(self, data_dir: Path, model: str = DEFAULT_MODEL):
        self.model_path = Path(data_dir) / "voices" / model
        self.cache_dir = Path(data_dir) / "voice_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._q: "queue.PriorityQueue[tuple[int, float, str]]" = queue.PriorityQueue()
        self._interrupt = threading.Event()
        self._voice = None
        self._ok = None  # None = not tried yet
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True, name="voice").start()

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    # -- public -----------------------------------------------------------

    def say(self, text: str, urgent: bool = False) -> None:
        """Queue a phrase. Urgent phrases cut off the current one."""
        if not text:
            return
        if urgent:
            self._drain()
            self._interrupt.set()
        self._q.put((0 if urgent else 1, time.monotonic(), text))

    def prewarm(self, phrases: list[str]) -> None:
        """Synthesize phrases into the cache ahead of time (background)."""
        def run():
            for p in phrases:
                self._wav_for(p)
        threading.Thread(target=run, daemon=True, name="voice-prewarm").start()

    # -- internals --------------------------------------------------------

    def _drain(self) -> None:
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def _load(self) -> bool:
        if self._ok is not None:
            return self._ok
        try:
            from piper import PiperVoice
            self._voice = PiperVoice.load(str(self.model_path))
            self._ok = True
            logger.info("voice: loaded %s", self.model_path.name)
        except Exception as e:  # missing model or piper not installed
            logger.warning("voice unavailable: %s", e)
            self._ok = False
        return self._ok

    def _wav_for(self, text: str) -> Optional[Path]:
        path = self.cache_dir / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".wav")
        if path.exists():
            return path
        with self._lock:
            if not self._load():
                return None
            tmp = path.with_suffix(".tmp")
            try:
                syn = None
                try:
                    from piper import SynthesisConfig
                    # slightly brisk, with natural variation in pitch/timing
                    syn = SynthesisConfig(length_scale=0.92, noise_scale=0.6, noise_w_scale=0.8)
                except ImportError:
                    pass
                with wave.open(str(tmp), "wb") as w:
                    if syn is not None:
                        self._voice.synthesize_wav(text, w, syn_config=syn)
                    else:
                        self._voice.synthesize_wav(text, w)
                tmp.replace(path)
            except Exception:
                logger.exception("voice: synthesis failed")
                return None
        return path

    def _worker(self) -> None:
        import winsound
        while True:
            _, _, text = self._q.get()
            self._interrupt.clear()
            path = self._wav_for(text)
            if path is None:
                continue
            with wave.open(str(path)) as w:
                duration = w.getnframes() / float(w.getframerate())
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            # wait out the clip unless something urgent interrupts it
            if self._interrupt.wait(duration + 0.15):
                winsound.PlaySound(None, 0)
