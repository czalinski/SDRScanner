"""
Day/night band switching for the HF (shortwave/HAM) dongle.

HF propagation follows the sun: the higher broadcast bands (13–22 MHz) are
open in daylight, the lower ones (5.9–7.6 MHz) at night. A channel config
with a `bands:` list (config/channels/ham.yaml) gets a BandSwitcher instead
of a single fixed Recorder: it works out whether the sun is up at the
receiver, runs a Recorder tuned to the matching band, and retunes (stop the
Recorder, start a new one) when day turns to night or back.

Each band can list fixed `channels` and/or `scan_ranges` — every
`step_khz` slot in a range becomes a channel, so active broadcasters are
found without a hand-maintained station list (schedules change seasonally).
"""
import logging
import math
import time
from pathlib import Path

from src.scanner.fft_engine import Channel
from src.scanner.recorder import Recorder

log = logging.getLogger(__name__)


# ── Sun position ───────────────────────────────────────────────────────────────

def sun_elevation_deg(lat: float, lon: float, unix_time: float | None = None) -> float:
    """
    Solar elevation in degrees (low-precision almanac formula, ~1° accuracy —
    plenty for deciding day vs night). lon is east-positive.
    """
    t = time.time() if unix_time is None else unix_time
    n = t / 86400.0 + 2440587.5 - 2451545.0          # days since J2000.0
    L = math.radians((280.460 + 0.9856474 * n) % 360.0)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst_deg = ((18.697374558 + 24.06570982441908 * n) % 24.0) * 15.0
    ha = math.radians(gmst_deg + lon) - ra
    phi = math.radians(lat)
    return math.degrees(math.asin(math.sin(phi) * math.sin(dec)
                                  + math.cos(phi) * math.cos(dec) * math.cos(ha)))


def is_daytime(lat: float, lon: float, threshold_deg: float = 0.0,
               unix_time: float | None = None) -> bool:
    return sun_elevation_deg(lat, lon, unix_time) >= threshold_deg


# ── Band → channels ────────────────────────────────────────────────────────────

def band_channels(band: dict, default_mode: str, detect_window: dict) -> list[Channel]:
    """Fixed `channels` plus every slot of each `scan_ranges` entry."""
    out: list[Channel] = []

    def add(name: str, freq_hz: float, mode: str, bandwidth_khz=None):
        kwargs = {}
        if mode in detect_window:
            kwargs["detect_offset_hz"], kwargs["bandwidth_hz"] = detect_window[mode]
        if bandwidth_khz is not None:
            kwargs["bandwidth_hz"] = bandwidth_khz * 1e3
        out.append(Channel(name=name, freq_hz=freq_hz, mode=mode, **kwargs))

    for ch in band.get("channels", []) or []:
        add(ch["name"], ch["freq_mhz"] * 1e6, str(ch.get("mode", default_mode)).lower(),
            ch.get("bandwidth_khz"))

    fixed = {round(c.freq_hz) for c in out}
    for rng in band.get("scan_ranges", []) or []:
        mode = str(rng.get("mode", default_mode)).lower()
        step_hz = rng.get("step_khz", 5) * 1e3
        label = rng.get("label", band["name"])
        f = rng["from_mhz"] * 1e6
        stop = rng["to_mhz"] * 1e6
        while f <= stop + 1:
            if round(f) not in fixed:
                add(f"{label} {f / 1e3:.0f}", f, mode)
            f += step_hz
    return out


# ── Switcher ───────────────────────────────────────────────────────────────────

class BandSwitcher:
    """Owns the Recorder for one band-scheduled device; call tick() periodically."""

    def __init__(self, dev: dict, cfg: dict, lat: float, lon: float,
                 recordings_dir: str | Path, build_channels, check_window):
        self._dev = dev
        self._cfg = cfg
        self._lat, self._lon = lat, lon
        self._recordings_dir = recordings_dir
        self._build_channels = build_channels      # (band) -> list[Channel]
        self._check_window = check_window          # (dev_id, center_hz, fs, channels) -> list
        self._threshold = float(cfg.get("day_sun_elevation_deg", 0.0))
        self._bands = {b["when"]: b for b in cfg["bands"]}
        missing = {"day", "night"} - set(self._bands)
        if missing:
            raise ValueError(f"bands: needs a 'day' and a 'night' entry (missing {sorted(missing)})")
        self._current: str | None = None
        self._rec: Recorder | None = None

    @property
    def current_band(self) -> str | None:
        return self._current

    def wanted_band(self, unix_time: float | None = None) -> str:
        return "day" if is_daytime(self._lat, self._lon, self._threshold, unix_time) else "night"

    def start(self) -> None:
        self.tick()

    def tick(self) -> None:
        want = self.wanted_band()
        if want == self._current:
            return
        band = self._bands[want]
        log.info("[%s] Sun %.1f° → switching to %s band (%s, %.3f MHz)",
                 self._dev["id"], sun_elevation_deg(self._lat, self._lon),
                 want, band["name"], band["center_mhz"])
        if self._rec is not None:
            self._rec.stop()
            self._rec = None
        self._current = want

        center_hz = band["center_mhz"] * 1e6
        fs = float(self._dev["sample_rate"])
        channels = self._check_window(self._dev["id"], center_hz, fs, self._build_channels(band))
        if not channels:
            log.error("[%s] %s band has no usable channels", self._dev["id"], band["name"])
            return
        self._rec = Recorder(
            dev_id=self._dev["id"],
            serial=self._dev["serial"],
            center_freq=center_hz,
            sample_rate=fs,
            channels=channels,
            recordings_dir=self._recordings_dir,
            gain=self._dev.get("gain"),
            ppm=int(self._dev.get("ppm", 0)),
            lo_offset_hz=float(self._dev.get("upconverter_offset_mhz") or 0.0) * 1e6,
            max_segment_s=self._dev.get("max_segment_s"),
            max_active_channels=self._cfg.get("max_active_channels"),
            detector=self._cfg.get("detector"),
        )
        self._rec.start()
        log.info("[%s] %s band: %d channels", self._dev["id"], band["name"], len(channels))

    def stop(self) -> None:
        if self._rec is not None:
            self._rec.stop()
            self._rec = None
