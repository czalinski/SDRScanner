"""Full-screen ADS-B + AIS live map — monitor 1 of the planned two-monitor setup.

Reads dump1090's periodic aircraft.json (see scripts/run_dump1090.sh) and the
AIS listener's ships.json (see src/display/ais_listener.py, fed by
scripts/run_rtl_ais.sh), rendering both as heading-oriented markers over a
cached OpenStreetMap background (src/display/tile_cache.py). Aircraft and
ships are color-coded separately since they otherwise look identical.
"""
import json
import logging
import math
import subprocess
import time
from pathlib import Path

import pygame

from src.display.tile_cache import MapView, zoom_for_radius_miles
from src.scanner.config_loader import load_channel_config

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

REPO_DIR = Path(__file__).resolve().parents[2]
AIRCRAFT_JSON = REPO_DIR / "run" / "adsb-json" / "aircraft.json"
SHIPS_JSON = REPO_DIR / "run" / "adsb-json" / "ships.json"

# Roughly what's visually spottable by eye from the ground on a clear day —
# not the SDR's actual RF reception range (which is far larger, 150nm+).
VISIBLE_RADIUS_MILES = 5
POLL_INTERVAL_S = 1.0

# GNOME Shell only hides its own top bar/dock over a fullscreen window that
# currently has input focus — the fullscreen *state* alone isn't enough. If
# something ever steals focus (Activities/Super key, an accidental click) and
# it doesn't come back, the panels stay visible indefinitely even though the
# window is still technically fullscreen. For an unattended kiosk, self-heal
# by re-asserting fullscreen when focus is actually lost — checked cheaply
# every frame, but only acted on (which recreates the display and causes a
# visible blink) at most once per this interval, and only when truly needed.
#
# Recreating the window (pygame.display.set_mode again) is NOT enough on its
# own to regain focus — confirmed on this hardware: a freshly-mapped
# fullscreen window did not receive _NET_ACTIVE_WINDOW from Mutter without an
# actual input event. Mutter's focus-stealing prevention blocks plain
# window-activation requests (xdotool windowactivate) too. What does work is
# a synthesized input event (see _force_input_focus) — this happens at
# startup and every reassert, so the kiosk self-heals even with no mouse ever
# physically attached; it's a software-level X11 event, not a hardware
# dependency.
FULLSCREEN_REASSERT_S = 10.0
OFFSCREEN_MARGIN_PX = 50

BG_FALLBACK_COLOR = (10, 10, 15)
AIRCRAFT_COLOR = (255, 0, 0)      # bright red
SHIP_COLOR = (0, 0, 139)          # dark blue
LABEL_COLOR = (0, 0, 0)           # black — same for both, only the glyph color distinguishes them
ATTRIBUTION = "© OpenStreetMap contributors"


def load_aircraft() -> list[dict]:
    try:
        with open(AIRCRAFT_JSON) as f:
            data = json.load(f)
        return data.get("aircraft", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.warning("Could not read %s: %s", AIRCRAFT_JSON, e)
        return []


def load_ships() -> list[dict]:
    try:
        with open(SHIPS_JSON) as f:
            data = json.load(f)
        return data.get("ships", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.debug("Could not read %s: %s", SHIPS_JSON, e)
        return []


def _format_altitude(alt) -> str:
    if alt == "ground":
        return "GND"
    if isinstance(alt, (int, float)):
        return f"{alt:.0f}ft"
    return "----ft"


def _format_speed(speed) -> str:
    if isinstance(speed, (int, float)):
        return f"{speed:.0f}kt"
    return "---kt"


def _force_input_focus(screen_w: int, screen_h: int) -> None:
    """Synthesize a click at screen center so Mutter hands the fullscreen
    window input focus. Non-fatal if xdotool is missing or X isn't reachable
    (e.g. running headless in a test) — the map still works, just possibly
    with GNOME's panels visible over it until something else changes focus."""
    try:
        subprocess.run(
            ["xdotool", "mousemove", str(screen_w // 2), str(screen_h // 2),
             "click", "1"],
            timeout=2, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("Could not synthesize focus click: %s", e)


def _draw_glyph(screen: pygame.Surface, x: int, y: int, heading_deg: float, color) -> None:
    """Small triangle pointing in the direction of travel."""
    size = 8
    angle = math.radians(heading_deg - 90)  # 0 = north; screen angle 0 = east
    tip = (x + size * math.cos(angle), y + size * math.sin(angle))
    p1_angle = angle + math.radians(150)
    p2_angle = angle - math.radians(150)
    p1 = (x + size * math.cos(p1_angle), y + size * math.sin(p1_angle))
    p2 = (x + size * math.cos(p2_angle), y + size * math.sin(p2_angle))
    pygame.draw.polygon(screen, color, [tip, p1, p2])


def draw_aircraft(screen: pygame.Surface, view: MapView, font: pygame.font.Font,
                   ac: dict) -> None:
    lat, lon = ac.get("lat"), ac.get("lon")
    if lat is None or lon is None:
        return

    x, y = view.latlon_to_screen(lat, lon)
    m = OFFSCREEN_MARGIN_PX
    if not (-m <= x <= view.screen_w + m and -m <= y <= view.screen_h + m):
        return

    _draw_glyph(screen, x, y, ac.get("track", 0.0), AIRCRAFT_COLOR)

    flight = (ac.get("flight") or ac.get("hex", "?????")).strip()
    label = f"{flight}  {_format_altitude(ac.get('alt_baro'))}  {_format_speed(ac.get('gs'))}"
    text = font.render(label, True, LABEL_COLOR)
    screen.blit(text, (x + 10, y - 8))


def draw_ship(screen: pygame.Surface, view: MapView, font: pygame.font.Font,
              ship: dict) -> None:
    lat, lon = ship.get("lat"), ship.get("lon")
    if lat is None or lon is None:
        return

    x, y = view.latlon_to_screen(lat, lon)
    m = OFFSCREEN_MARGIN_PX
    if not (-m <= x <= view.screen_w + m and -m <= y <= view.screen_h + m):
        return

    _draw_glyph(screen, x, y, ship.get("course") or 0.0, SHIP_COLOR)

    name = ship.get("shipname") or ship.get("callsign") or str(ship.get("mmsi", "?????"))
    label = f"{name}  {_format_speed(ship.get('speed'))}"
    text = font.render(label, True, LABEL_COLOR)
    screen.blit(text, (x + 10, y - 8))


def main() -> None:
    cfg = load_channel_config("adsb")
    receiver_lat = cfg["mlat"]["receiver_lat"]
    receiver_lon = cfg["mlat"]["receiver_lon"]

    pygame.init()
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h

    def _claim_fullscreen():
        s = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN)
        pygame.display.set_caption("SDRScanner — ADS-B Live Map")
        pygame.mouse.set_visible(False)
        _force_input_focus(screen_w, screen_h)
        return s

    screen = _claim_fullscreen()

    font = pygame.font.SysFont("monospace", 14)
    attrib_font = pygame.font.SysFont("sans", 12)

    zoom = zoom_for_radius_miles(receiver_lat, VISIBLE_RADIUS_MILES, screen_h)
    log.info("Building map background (zoom=%d, ~%dmi radius, center=%.6f,%.6f)...",
              zoom, VISIBLE_RADIUS_MILES, receiver_lat, receiver_lon)
    view = MapView(receiver_lat, receiver_lon, zoom, screen_w, screen_h)
    try:
        background = view.build_background()
    except Exception:
        log.exception("Failed to build map background — falling back to solid color")
        background = pygame.Surface((screen_w, screen_h))
        background.fill(BG_FALLBACK_COLOR)
    log.info("Background ready. Entering main loop.")

    clock = pygame.time.Clock()
    last_poll = 0.0
    last_fullscreen_reassert = time.monotonic()
    aircraft: list[dict] = []
    ships: list[dict] = []

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
            ships = load_ships()
            last_poll = now

        lost_focus = not pygame.display.get_active() or not pygame.key.get_focused()
        if lost_focus and now - last_fullscreen_reassert >= FULLSCREEN_REASSERT_S:
            last_fullscreen_reassert = now
            log.warning("Lost window focus/fullscreen — reasserting.")
            screen = _claim_fullscreen()

        screen.blit(background, (0, 0))
        for ac in aircraft:
            draw_aircraft(screen, view, font, ac)
        for ship in ships:
            draw_ship(screen, view, font, ship)

        count_text = font.render(f"{len(aircraft)} aircraft, {len(ships)} ships", True, LABEL_COLOR)
        screen.blit(count_text, (10, 10))
        attrib_text = attrib_font.render(ATTRIBUTION, True, (40, 40, 40))
        screen.blit(attrib_text, (10, screen_h - 20))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
