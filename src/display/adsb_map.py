"""Full-screen ADS-B live map — monitor 1 of the planned two-monitor setup.

Reads dump1090's periodic aircraft.json (see scripts/start_scanner.sh, which
runs dump1090 with --write-json) and renders tracked aircraft as
heading-oriented markers with callsign/altitude/speed labels over a cached
OpenStreetMap background (src/display/tile_cache.py).
"""
import json
import logging
import math
import time
from pathlib import Path

import pygame

from src.display.tile_cache import MapView
from src.scanner.config_loader import load_channel_config

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

REPO_DIR = Path(__file__).resolve().parents[2]
AIRCRAFT_JSON = REPO_DIR / "run" / "adsb-json" / "aircraft.json"

ZOOM = 9
POLL_INTERVAL_S = 1.0
OFFSCREEN_MARGIN_PX = 50

BG_FALLBACK_COLOR = (10, 10, 15)
AIRCRAFT_COLOR = (255, 200, 0)
LABEL_COLOR = (0, 255, 120)
ATTRIBUTION = "© OpenStreetMap contributors"


def load_aircraft() -> list[dict]:
    try:
        with open(AIRCRAFT_JSON) as f:
            data = json.load(f)
        return data.get("aircraft", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.warning("Could not read %s: %s", AIRCRAFT_JSON, e)
        return []


def _format_altitude(alt) -> str:
    if alt == "ground":
        return "GND"
    if isinstance(alt, (int, float)):
        return f"{alt:.0f}ft"
    return "----ft"


def _format_speed(gs) -> str:
    if isinstance(gs, (int, float)):
        return f"{gs:.0f}kt"
    return "---kt"


def _draw_aircraft_glyph(screen: pygame.Surface, x: int, y: int, track_deg: float) -> None:
    """Small triangle pointing in the aircraft's direction of travel."""
    size = 8
    angle = math.radians(track_deg - 90)  # track 0 = north; screen angle 0 = east
    tip = (x + size * math.cos(angle), y + size * math.sin(angle))
    p1_angle = angle + math.radians(150)
    p2_angle = angle - math.radians(150)
    p1 = (x + size * math.cos(p1_angle), y + size * math.sin(p1_angle))
    p2 = (x + size * math.cos(p2_angle), y + size * math.sin(p2_angle))
    pygame.draw.polygon(screen, AIRCRAFT_COLOR, [tip, p1, p2])


def draw_aircraft(screen: pygame.Surface, view: MapView, font: pygame.font.Font,
                   ac: dict) -> None:
    lat, lon = ac.get("lat"), ac.get("lon")
    if lat is None or lon is None:
        return

    x, y = view.latlon_to_screen(lat, lon)
    m = OFFSCREEN_MARGIN_PX
    if not (-m <= x <= view.screen_w + m and -m <= y <= view.screen_h + m):
        return

    _draw_aircraft_glyph(screen, x, y, ac.get("track", 0.0))

    flight = (ac.get("flight") or ac.get("hex", "?????")).strip()
    label = f"{flight}  {_format_altitude(ac.get('alt_baro'))}  {_format_speed(ac.get('gs'))}"
    text = font.render(label, True, LABEL_COLOR)
    screen.blit(text, (x + 10, y - 8))


def main() -> None:
    cfg = load_channel_config("adsb")
    receiver_lat = cfg["mlat"]["receiver_lat"]
    receiver_lon = cfg["mlat"]["receiver_lon"]

    pygame.init()
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN)
    pygame.display.set_caption("SDRScanner — ADS-B Live Map")
    pygame.mouse.set_visible(False)

    font = pygame.font.SysFont("monospace", 14)
    attrib_font = pygame.font.SysFont("sans", 12)

    log.info("Building map background (zoom=%d, center=%.4f,%.4f)...",
              ZOOM, receiver_lat, receiver_lon)
    view = MapView(receiver_lat, receiver_lon, ZOOM, screen_w, screen_h)
    try:
        background = view.build_background()
    except Exception:
        log.exception("Failed to build map background — falling back to solid color")
        background = pygame.Surface((screen_w, screen_h))
        background.fill(BG_FALLBACK_COLOR)
    log.info("Background ready. Entering main loop.")

    clock = pygame.time.Clock()
    last_poll = 0.0
    aircraft: list[dict] = []

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        now = time.monotonic()
        if now - last_poll >= POLL_INTERVAL_S:
            aircraft = load_aircraft()
            last_poll = now

        screen.blit(background, (0, 0))
        for ac in aircraft:
            draw_aircraft(screen, view, font, ac)

        count_text = font.render(f"{len(aircraft)} aircraft", True, LABEL_COLOR)
        screen.blit(count_text, (10, 10))
        attrib_text = attrib_font.render(ATTRIBUTION, True, (180, 180, 180))
        screen.blit(attrib_text, (10, screen_h - 20))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
