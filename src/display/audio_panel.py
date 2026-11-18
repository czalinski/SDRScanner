"""Audio panel — the right-hand strip of the kiosk display.

Shows what the scanner has played through the speaker: the clip playing now
(with a progress bar) on top, then a list of recent clips, newest first, so
older entries scroll down and off the bottom. Reads run/playback.json, written
by src/scanner/playback_queue.py.
"""
import json
import time
from pathlib import Path

import pygame

REPO_DIR = Path(__file__).resolve().parents[2]
PLAYBACK_JSON = REPO_DIR / "run" / "playback.json"

PANEL_FRACTION = 0.20     # share of the screen width, on the right

BG = (22, 24, 30)
DIVIDER = (60, 64, 74)
TEXT = (235, 236, 240)
MUTED = (150, 155, 168)
HEADER = (120, 126, 140)
NOW_BG = (36, 40, 50)

DEVICES = {               # device id → (display name, accent colour)
    "marine": ("Marine", (80, 150, 255)),
    "railroad": ("Rail", (255, 150, 50)),
    "ham": ("HAM", (90, 205, 120)),
}


def load_history() -> list[dict]:
    try:
        with open(PLAYBACK_JSON) as f:
            return json.load(f).get("history", [])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def describe(entry: dict) -> tuple[str, str, tuple[int, int, int]]:
    """(title, detail, colour) — e.g. ("Marine Ch 14", "Vessel Traffic", blue)."""
    dev = entry.get("device", "")
    dev_name, colour = DEVICES.get(dev, (dev.title() or "?", MUTED))
    channel = entry.get("channel") or "?"
    freq = entry.get("freq_khz")
    freq_txt = f"{freq / 1000:.3f} MHz" if freq else ""

    if dev == "ham":
        # Channel names are "<band> <kHz>" (e.g. "19m 15140") or a station name
        band = channel.split()[0]
        title = f"{dev_name} {freq} kHz" if freq else f"{dev_name} {channel}"
        detail = f"{band} band" if band.endswith("m") and band[:-1].isdigit() else channel
    elif " — " in channel:                         # "Ch 14 — Vessel Traffic"
        short, desc = channel.split(" — ", 1)
        title, detail = f"{dev_name} {short}", desc
    else:                                         # "BNSF Road Ch 7"
        title, detail = f"{dev_name} {channel}", freq_txt
    return title, detail, colour


def _fit(font: pygame.font.Font, text: str, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "…")[0] > width:
        text = text[:-1]
    return text + "…"


def _is_playing(entry: dict, now: float) -> bool:
    # A "playing" entry left behind by a scanner crash/restart must not stick
    end = entry.get("started", 0) + entry.get("duration_s", 0) + 2.0
    return entry.get("status") == "playing" and now <= end


class AudioPanel:
    def __init__(self, rect: pygame.Rect, screen_h: int):
        s = screen_h / 1080.0
        self.rect = rect
        self.pad = int(14 * s)
        self.f_header = pygame.font.SysFont("dejavusans", int(15 * s), bold=True)
        self.f_title = pygame.font.SysFont("dejavusans", int(21 * s), bold=True)
        self.f_detail = pygame.font.SysFont("dejavusans", int(15 * s))
        self.f_now = pygame.font.SysFont("dejavusans", int(26 * s), bold=True)

    def draw(self, screen: pygame.Surface, history: list[dict]) -> None:
        r, pad, now = self.rect, self.pad, time.time()
        screen.fill(BG, r)
        pygame.draw.line(screen, DIVIDER, r.topleft, r.bottomleft, 2)
        x, w = r.x + pad, r.width - 2 * pad
        y = r.y + pad

        # ── Now playing ──────────────────────────────────────────────────────
        y = self._header(screen, "NOW PLAYING", x, y)
        playing = history[0] if history and _is_playing(history[0], now) else None
        card_h = self.f_now.get_height() + self.f_detail.get_height() + 3 * pad
        card = pygame.Rect(r.x + pad // 2, y, r.width - pad, card_h)
        pygame.draw.rect(screen, NOW_BG, card, border_radius=6)
        if playing:
            title, detail, colour = describe(playing)
            pygame.draw.rect(screen, colour, (card.x, card.y, 6, card.h),
                             border_top_left_radius=6, border_bottom_left_radius=6)
            ty = card.y + pad // 2
            screen.blit(self.f_now.render(_fit(self.f_now, title, w), True, TEXT), (x, ty))
            ty += self.f_now.get_height()
            screen.blit(self.f_detail.render(_fit(self.f_detail, detail, w), True, MUTED), (x, ty))
            dur = playing.get("duration_s") or 0
            frac = min(1.0, (now - playing.get("started", now)) / dur) if dur else 1.0
            bar = pygame.Rect(x, card.bottom - pad, w, 4)
            pygame.draw.rect(screen, DIVIDER, bar, border_radius=2)
            pygame.draw.rect(screen, colour, (bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=2)
        else:
            idle = self.f_detail.render("Listening…", True, MUTED)
            screen.blit(idle, (x, card.centery - idle.get_height() // 2))
        y = card.bottom + pad

        # ── Recent clips, newest first ───────────────────────────────────────
        y = self._header(screen, "RECENT", x, y)
        row_h = self.f_title.get_height() + self.f_detail.get_height() + pad
        for entry in history[1:] if playing else history:
            if y + row_h > r.bottom:
                break                              # older entries scroll off
            title, detail, colour = describe(entry)
            pygame.draw.rect(screen, colour, (r.x + pad // 2, y + 3, 4, row_h - pad - 2))
            clock = time.strftime("%H:%M", time.localtime(entry.get("started", now)))
            clock_s = self.f_detail.render(clock, True, MUTED)
            tw = w - clock_s.get_width() - pad // 2
            screen.blit(self.f_title.render(_fit(self.f_title, title, tw), True, TEXT), (x, y))
            screen.blit(clock_s, (x + w - clock_s.get_width(), y + 4))
            dur = entry.get("duration_s", 0)
            bits = [detail, f"{dur:.1f}s" if dur < 10 else f"{dur:.0f}s"]
            if entry.get("status") == "interrupted":
                bits.append("cut off")
            line = " · ".join(b for b in bits if b)
            screen.blit(self.f_detail.render(_fit(self.f_detail, line, w), True, MUTED),
                        (x, y + self.f_title.get_height()))
            y += row_h

    def _header(self, screen: pygame.Surface, text: str, x: int, y: int) -> int:
        screen.blit(self.f_header.render(text, True, HEADER), (x, y))
        return y + self.f_header.get_height() + self.pad // 2
