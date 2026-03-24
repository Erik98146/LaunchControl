import time
import gc
import board
import digitalio
import displayio
import neopixel
import adafruit_imageload
import microcontroller
import watchdog

from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.circle import Circle

import wifi
import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import os

# ===================== USER CONFIG =====================

WIFI_SSID = os.getenv("CIRCUITPY_WIFI_SSID")
WIFI_PASSWORD = os.getenv("CIRCUITPY_WIFI_PASSWORD")
MQTT_BROKER = os.getenv("CIRCUITPY_MQTT_BROKER")

MQTT_PORT = 1883

# ---- Hang diagnostics / safety ----
WATCHDOG_TIMEOUT_S = 12  # seconds; reset if code stalls longer than this
HEARTBEAT_INTERVAL_S = 10
HEAP_REPORT_INTERVAL_S = 30
last_heartbeat = time.monotonic()
last_heap_report = time.monotonic()
last_mqtt_good = time.monotonic()

# Enable watchdog reset (CircuitPython 7+)
try:
    microcontroller.watchdog.timeout = WATCHDOG_TIMEOUT_S
    microcontroller.watchdog.mode = watchdog.WatchDogMode.RESET
    microcontroller.watchdog.feed()
    print('Watchdog enabled:', WATCHDOG_TIMEOUT_S, 's')
except Exception as e:
    print('Watchdog not available:', repr(e))


# MagTag publishes actions here
TOPIC_STARLINK_BUTTON = "magtag/starlink/button"   # "on"/"off"/"timer"
TOPIC_INVERTER_BUTTON = "magtag/inverter/button"   # "1"/"3"/"timer"
TOPIC_TIMER_BUTTON = "magtag/timer/button"         # "true"/"false"
TOPIC_WATER_BUTTON = "magtag/water/button"         # "on"/"off"/"timer"  (page 2)
TOPIC_TIMER_SET = "magtag/timer/set"               # "HH:MM" (page 3 earlier/later)

# Node-RED publishes states here
TOPIC_STARLINK_STATE = "magtag/starlink/state"
TOPIC_INVERTER_STATE = "magtag/inverter/state"
TOPIC_TIMER_STATE = "magtag/timer/state"
TOPIC_WATER_STATE = "magtag/water/state"           # "on"/"off"/"timer"  (page 2)

# Timer time string topic
TOPIC_TIMER_TIME = "magtag/timer/time"

# Thermostat topics (Node-RED publishes states here)
TOPIC_AC_FAN = "magtag/ac/fan"
TOPIC_AC_TEMP = "magtag/ac/temp"
TOPIC_AC_SET = "magtag/ac/set"


# Battery topics
TOPIC_BATTERY_SOC = "magtag/battery/soc"
TOPIC_BATTERY_REMAIN = "magtag/battery/remain"
TOPIC_BATTERY_LOAD = "magtag/battery/load"

# Temperature topics (optional)
TOPIC_TEMP_IN = "magtag/temp/in"
TOPIC_TEMP_OUT = "magtag/temp/out"
TOPIC_TEMP_SET = "magtag/temp/set"
TOPIC_TEMP_CHANGE = "magtag/temp/change"
# =======================================================

# ---------------- Display ----------------
display = board.DISPLAY
try:
    display.auto_refresh = False
except AttributeError:
    pass

W, H = display.width, display.height

BLACK = 0x000000
WHITE = 0xFFFFFF

# ---------------- Fonts ----------------
FONT_MAIN = bitmap_font.load_font("/fonts/ArialNarrow-Bold-16.bdf")
FONT_STATUS = bitmap_font.load_font("/fonts/ArialNarrow-Bold-16.bdf")
FONT_TIMER_BIG = bitmap_font.load_font("/fonts/ArialNarrow-Bold-20.bdf")  # page 3 label + time

# ---------------- Persistent Brightness ----------------
BRIGHTNESS_LEVELS = [0.05, 0.25, 0.50, 0.75, 1.00]
NVM_BRIGHTNESS_INDEX_ADDR = 0  # first byte of NVM


def load_brightness_index() -> int:
    try:
        raw = microcontroller.nvm[NVM_BRIGHTNESS_INDEX_ADDR]
        if raw == 0xFF:
            return 1  # default 25%
        idx = int(raw)
        if 0 <= idx < len(BRIGHTNESS_LEVELS):
            return idx
    except Exception:
        pass
    return 1


def save_brightness_index(idx: int) -> None:
    idx = max(0, min(len(BRIGHTNESS_LEVELS) - 1, int(idx)))
    try:
        microcontroller.nvm[NVM_BRIGHTNESS_INDEX_ADDR] = idx
    except Exception as e:
        print("NVM save failed:", repr(e))


brightness_index = load_brightness_index()

# ---------------- NeoPixels ----------------
pixels = neopixel.NeoPixel(
    board.NEOPIXEL,
    4,
    brightness=BRIGHTNESS_LEVELS[brightness_index],
    auto_write=False,
)

LED_ON_SECONDS = 5.0
led_off_at = 0.0


def leds_on():
    pixels.fill((255, 255, 255))
    pixels.show()


def leds_off():
    pixels.fill((0, 0, 0))
    pixels.show()


def apply_brightness():
    pixels.brightness = BRIGHTNESS_LEVELS[brightness_index]


leds_off()

# ---------------- Buttons ----------------
button_pins = [board.BUTTON_A, board.BUTTON_B, board.BUTTON_C, board.BUTTON_D]
buttons = []
for pin in button_pins:
    b = digitalio.DigitalInOut(pin)
    b.direction = digitalio.Direction.INPUT
    b.pull = digitalio.Pull.UP
    buttons.append(b)

last_pressed = [False] * 4
last_debounce_time = [0.0] * 4
DEBOUNCE_S = 0.03

press_start_time = [0.0] * 4
LONG_PRESS_S = 2.0

# Track which page the press STARTED on (prevents page-change release side effects)
press_start_page = [0] * 4

# UI placement: aligned to buttons
button_center_fracs = [0.145, 0.385, 0.625, 0.865]
X_NUDGE = -18
Y_NUDGE = +28

base_y = H - 36
row_y = base_y + Y_NUDGE
x_positions = [int(W * f) + X_NUDGE for f in button_center_fracs]

# ---------------- Manual e-ink refresh ----------------
dirty = True
last_refresh_time = 0.0
MIN_REFRESH_INTERVAL_S = 0.9


def try_refresh(now: float):
    global dirty, last_refresh_time, battery_pending_refresh, battery_bootstrap_refresh_request
    if not dirty:
        return
    if hasattr(display, "busy") and display.busy:
        return
    if (now - last_refresh_time) < MIN_REFRESH_INTERVAL_S:
        return
    try:
        display.refresh()
        last_refresh_time = now
        dirty = False
        # Clear one-shot battery bootstrap refresh request once we succeed
        if battery_bootstrap_refresh_request:
            battery_bootstrap_refresh_request = False
    except RuntimeError:
        pass


# ---------------- Helpers ----------------
PAD_X = 4
PAD_Y = 2


def load_bmp_tilegrid(path: str) -> displayio.TileGrid:
    bm, pal = adafruit_imageload.load(
        path, bitmap=displayio.Bitmap, palette=displayio.Palette
    )
    return displayio.TileGrid(bm, pixel_shader=pal)


def make_invert_label(group: displayio.Group, font, text: str, x: int, y: int):
    lbl = label.Label(font, text=text, color=BLACK)
    lbl.anchor_point = (0.5, 0.5)
    lbl.anchored_position = (x, y)

    tw = lbl.bounding_box[2]
    th = lbl.bounding_box[3]
    box_w = tw + PAD_X * 2
    box_h = th + PAD_Y * 2

    bm = displayio.Bitmap(box_w, box_h, 2)
    pal = displayio.Palette(2)
    pal[0] = BLACK
    pal[1] = BLACK
    pal.make_transparent(0)

    tile = displayio.TileGrid(bm, pixel_shader=pal)
    tile.x = int(x - box_w // 2)
    tile.y = int(y - box_h // 2)

    group.append(tile)
    group.append(lbl)
    return bm, lbl


def parse_hhmm_to_minutes(s: str):
    """Return minutes since midnight, or None if invalid."""
    if not s:
        return None
    s = s.strip()
    if len(s) < 4:
        return None
    try:
        parts = s.split(":")
        if len(parts) != 2:
            return None
        hh = int(parts[0])
        mm = int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        return hh * 60 + mm
    except Exception:
        return None


def minutes_to_hhmm(m: int) -> str:
    m = int(m) % (24 * 60)
    hh = m // 60
    mm = m % 60
    return "{:02d}:{:02d}".format(hh, mm)


def trim_after_hrs(s: str) -> str:
    """Return everything up to and including 'hrs' (case-insensitive)."""
    if not s:
        return ""
    s = s.strip()
    idx = s.lower().find("hrs")
    if idx == -1:
        return s
    return s[: idx + 3]


def trim_after_w(s: str) -> str:
    """Return everything up to and including the first 'W' (case-insensitive)."""
    if not s:
        return ""
    s = s.strip()
    # Find first 'w' or 'W'
    for i, ch in enumerate(s):
        if ch == "W" or ch == "w":
            return s[: i + 1]
    return s


# ===================== Pages =====================
PAGE_MAIN = 0
PAGE_SECOND = 1
PAGE_THIRD = 2
PAGE_FOUR = 3
current_page = PAGE_MAIN

LINE_PX = 13

# ---- LOS (MQTT disconnected indicator) ----
LOS_MARGIN_X = 8
LOS_MARGIN_Y = 8
LOS_OFFSET = 20  # tighter vertical spacing between letters

def add_los_label(group: displayio.Group):
    g = displayio.Group()
    base_x = W - LOS_MARGIN_X
    base_y = H - LOS_MARGIN_Y

    lbl_l = label.Label(FONT_TIMER_BIG, text="L", color=BLACK)
    lbl_o = label.Label(FONT_TIMER_BIG, text="O", color=BLACK)
    lbl_s = label.Label(FONT_TIMER_BIG, text="S", color=BLACK)

    # Stack bottom-right with custom spacing
    for idx, lbl in enumerate((lbl_l, lbl_o, lbl_s)):
        lbl.anchor_point = (1.0, 1.0)
        lbl.anchored_position = (base_x, base_y - (LOS_OFFSET * (2 - idx)))
        g.append(lbl)

    g.hidden = True
    group.append(g)
    return g


# ---- Page 1 ----
main_group = displayio.Group()
main_group.append(load_bmp_tilegrid("/images/background.bmp"))

# Battery display (upper-left on main page)
# Adjustable spacing between lines:
BATTERY_LINE_SPACING = 20  # pixels between SOC/Load line and Remaining line

# Battery refresh throttling:
BATTERY_REFRESH_INTERVAL_S = 60 * 60  # 60 minutes
battery_pending_refresh = False

# Track first battery messages after MQTT connect (one forced refresh)
battery_soc_seen = False
battery_remain_seen = False
battery_load_seen = False
battery_bootstrap_refresh_done = False
battery_bootstrap_refresh_request = False

battery_soc_value = ""
battery_remain_value = ""
battery_load_value = ""

BATTERY_X = 10
BATTERY_Y = 10

battery_soc_lbl = label.Label(FONT_TIMER_BIG, text="Battery: ", color=BLACK)
battery_soc_lbl.anchor_point = (0.0, 0.0)
battery_soc_lbl.anchored_position = (BATTERY_X, BATTERY_Y)
main_group.append(battery_soc_lbl)

battery_remain_lbl = label.Label(FONT_MAIN, text="Remaining: ", color=BLACK)
battery_remain_lbl.anchor_point = (0.0, 0.0)
battery_remain_lbl.anchored_position = (BATTERY_X, BATTERY_Y + BATTERY_LINE_SPACING)
main_group.append(battery_remain_lbl)

# In/Out temperature display (main page) - updated on cadence, not per MQTT message.
# Place in the top-right corner and use FONT_MAIN as requested.
TEMP_RIGHT_MARGIN = 6
TEMP_TOP_MARGIN = 6
TEMP_LINE_SPACING = 18  # pixels between In and Out lines
TEMP_REFRESH_INTERVAL_S = 10 * 60  # 10 minutes
temp_pending_refresh = False
last_temp_refresh = 0.0

temp_in_value = ""
temp_out_value = ""
temp_set_value = ""

temp_in_lbl = label.Label(FONT_MAIN, text="In: --", color=BLACK)
temp_in_lbl.anchor_point = (1.0, 0.0)
temp_in_lbl.anchored_position = (W - TEMP_RIGHT_MARGIN, TEMP_TOP_MARGIN)
main_group.append(temp_in_lbl)

temp_out_lbl = label.Label(FONT_MAIN, text="Out: --", color=BLACK)
temp_out_lbl.anchor_point = (1.0, 0.0)
temp_out_lbl.anchored_position = (W - TEMP_RIGHT_MARGIN, TEMP_TOP_MARGIN + TEMP_LINE_SPACING)
main_group.append(temp_out_lbl)

def _maybe_request_battery_bootstrap_refresh():
    """Request exactly one forced refresh once SOC, Remaining, and Load have been received after MQTT connect."""
    global battery_bootstrap_refresh_done, battery_bootstrap_refresh_request, dirty
    if battery_bootstrap_refresh_done:
        return
    if battery_soc_seen and battery_remain_seen and battery_load_seen:
        battery_bootstrap_refresh_done = True
        battery_bootstrap_refresh_request = True
        dirty = True

NAMES_MAIN = ["Starlink", "Inverter", "Timer", "Next"]
states_main = [False, False, False, False]
main_bg_bitmaps = []
main_text_labels = []

for i, name in enumerate(NAMES_MAIN):
    bm, lbl = make_invert_label(main_group, FONT_MAIN, name, x_positions[i], row_y)
    main_bg_bitmaps.append(bm)
    main_text_labels.append(lbl)

starlink_timer_lbl = label.Label(FONT_MAIN, text="", color=BLACK)
starlink_timer_lbl.anchor_point = (0.5, 0.5)
starlink_timer_lbl.anchored_position = (x_positions[0], row_y - (4 * LINE_PX))
main_group.append(starlink_timer_lbl)

inverter_timer_lbl = label.Label(FONT_MAIN, text="", color=BLACK)
inverter_timer_lbl.anchor_point = (0.5, 0.5)
inverter_timer_lbl.anchored_position = (x_positions[1], row_y - (4 * LINE_PX))
main_group.append(inverter_timer_lbl)

timer_time_lbl = label.Label(FONT_MAIN, text="", color=BLACK)
timer_time_lbl.anchor_point = (0.5, 0.5)
timer_time_lbl.anchored_position = (x_positions[2], row_y - (4 * LINE_PX))
main_group.append(timer_time_lbl)


timer_time_value = ""
timer_enabled = False

starlink_enabled = False
starlink_timer_mode = False

inverter_enabled = False
inverter_timer_mode = False


def set_main_label_state(i: int, on: bool):
    global dirty
    states_main[i] = on
    main_bg_bitmaps[i].fill(1 if on else 0)
    main_text_labels[i].color = WHITE if on else BLACK
    dirty = True


# ---- Page 2 ----
second_group = displayio.Group()
second_group.append(load_bmp_tilegrid("/images/background2.bmp"))

page2_labels = ["Back", "Water", "Thermostat", "Bright"]
page2_bg_bitmaps = []
page2_text_labels = []
page2_states = [False, False, False, False]

for i, name in enumerate(page2_labels):
    bm, lbl = make_invert_label(second_group, FONT_MAIN, name, x_positions[i], row_y)
    page2_bg_bitmaps.append(bm)
    page2_text_labels.append(lbl)

water_timer_lbl = label.Label(FONT_MAIN, text="", color=BLACK)
water_timer_lbl.anchor_point = (0.5, 0.5)
water_timer_lbl.anchored_position = (x_positions[1], row_y - (4 * LINE_PX))
second_group.append(water_timer_lbl)

water_enabled = False
water_timer_mode = False


def set_page2_label_state(i: int, on: bool):
    global dirty
    page2_states[i] = on
    page2_bg_bitmaps[i].fill(1 if on else 0)
    page2_text_labels[i].color = WHITE if on else BLACK
    dirty = True


# ---- Page 3 ----
third_group = displayio.Group()
third_group.append(load_bmp_tilegrid("/images/background3.bmp"))

page3_labels = ["Back", "Earlier", "Later", ""]
page3_bg_bitmaps = []
page3_text_labels = []
page3_states = [False, False, False, False]

for i, name in enumerate(page3_labels):
    if name != "":
        bm, lbl = make_invert_label(third_group, FONT_MAIN, name, x_positions[i], row_y)
        page3_bg_bitmaps.append(bm)
        page3_text_labels.append(lbl)
    else:
        page3_bg_bitmaps.append(None)
        page3_text_labels.append(None)

# Center between "Earlier" and "Later"
page3_center_x = (x_positions[1] + x_positions[2]) // 2
page3_center_y = H // 2

# Move up by half a text line
HALF_LINE = LINE_PX // 2  # 6 px

page3_title_lbl = label.Label(FONT_TIMER_BIG, text="TIMER OFF TIME:", color=BLACK)
page3_title_lbl.anchor_point = (0.5, 0.5)
page3_title_lbl.anchored_position = (page3_center_x, page3_center_y - 18 - HALF_LINE)
third_group.append(page3_title_lbl)

page3_time_lbl = label.Label(FONT_TIMER_BIG, text="", color=BLACK)
page3_time_lbl.anchor_point = (0.5, 0.5)
page3_time_lbl.anchored_position = (page3_center_x, page3_center_y + 10 - HALF_LINE)
third_group.append(page3_time_lbl)


# ---- Page 4 (Thermostat) ----
fourth_group = displayio.Group()
fourth_group.append(load_bmp_tilegrid("/images/background4.bmp"))

page4_labels = ["Back", "Down", "Up", "Mode"]
page4_bg_bitmaps = []
page4_text_labels = []
page4_states = [False, False, False, False]

for i, name in enumerate(page4_labels):
    bm, lbl = make_invert_label(fourth_group, FONT_MAIN, name, x_positions[i], row_y)
    page4_bg_bitmaps.append(bm)
    page4_text_labels.append(lbl)

# Fan status (formatted like timer text above Starlink)
fan_status_lbl = label.Label(FONT_MAIN, text="", color=BLACK)
fan_status_lbl.anchor_point = (0.5, 0.5)
fan_status_lbl.anchored_position = (x_positions[3], row_y - (4 * LINE_PX))
fourth_group.append(fan_status_lbl)

# Large temp / setpoint lines (formatted like page 3 timer text)
page4_center_x = (x_positions[1] + x_positions[2]) // 2
page4_center_y = H // 2

page4_temp_lbl = label.Label(FONT_TIMER_BIG, text="Current Temp: ", color=BLACK)
page4_temp_lbl.anchor_point = (0.5, 0.5)
# moved up one additional half line (total: one full line vs page3 baseline)
page4_temp_lbl.anchored_position = (page4_center_x, page4_center_y - 18 - (HALF_LINE * 2))
fourth_group.append(page4_temp_lbl)

page4_set_lbl = label.Label(FONT_TIMER_BIG, text="Set: ", color=BLACK)
page4_set_lbl.anchor_point = (0.5, 0.5)
page4_set_lbl.anchored_position = (page4_center_x, page4_center_y + 10 - (HALF_LINE * 2))
fourth_group.append(page4_set_lbl)

# Create LOS indicators (one per page group)
los_main_lbl = add_los_label(main_group)
los_second_lbl = add_los_label(second_group)
los_third_lbl = add_los_label(third_group)
los_fourth_lbl = add_los_label(fourth_group)



ac_fan_value = ""
ac_temp_value = ""
ac_set_value = ""


los_main_lbl = add_los_label(main_group)
los_second_lbl = add_los_label(second_group)
los_third_lbl = add_los_label(third_group)
los_fourth_lbl = add_los_label(fourth_group)


# ---- WiFi/MQTT indicators (page 2) ----
STATUS_X = 10
STATUS_Y_WIFI = 10
STATUS_Y_MQTT = 32
STATUS_RADIUS = 6
STATUS_LABEL_X_OFFSET = 8

wifi_circle = Circle(
    STATUS_X + STATUS_RADIUS,
    STATUS_Y_WIFI + STATUS_RADIUS,
    STATUS_RADIUS,
    outline=BLACK,
    fill=None,
)
second_group.append(wifi_circle)

wifi_lbl = label.Label(FONT_STATUS, text="WiFi", color=BLACK)
wifi_lbl.anchor_point = (0.0, 0.0)
wifi_lbl.anchored_position = (
    STATUS_X + STATUS_RADIUS * 2 + STATUS_LABEL_X_OFFSET,
    STATUS_Y_WIFI,
)
second_group.append(wifi_lbl)

mqtt_circle = Circle(
    STATUS_X + STATUS_RADIUS,
    STATUS_Y_MQTT + STATUS_RADIUS,
    STATUS_RADIUS,
    outline=BLACK,
    fill=None,
)
second_group.append(mqtt_circle)

mqtt_lbl = label.Label(FONT_STATUS, text="MQTT", color=BLACK)
mqtt_lbl.anchor_point = (0.0, 0.0)
mqtt_lbl.anchored_position = (
    STATUS_X + STATUS_RADIUS * 2 + STATUS_LABEL_X_OFFSET,
    STATUS_Y_MQTT,
)
second_group.append(mqtt_lbl)


_last_wifi_connected = None
_last_mqtt_connected = None

_last_los_mqtt_connected = None

_last_los_show = None

def update_los_indicator(force=False):
    # Only trigger a display refresh when LOS visibility actually changes.
    global dirty, _last_los_show

    los_show = not mqtt_connected
    if (not force) and (_last_los_show is not None) and (los_show == _last_los_show):
        return

    # Update all pages (only the active root_group is visible)
    target_hidden = not los_show
    if los_main_lbl.hidden != target_hidden:
        los_main_lbl.hidden = target_hidden
    if los_second_lbl.hidden != target_hidden:
        los_second_lbl.hidden = target_hidden
    if los_third_lbl.hidden != target_hidden:
        los_third_lbl.hidden = target_hidden
    if los_fourth_lbl.hidden != target_hidden:
        los_fourth_lbl.hidden = target_hidden

    _last_los_show = los_show
    dirty = True

def set_circle_connected(circle_obj: Circle, connected: bool):
    circle_obj.outline = BLACK
    circle_obj.fill = BLACK if connected else None


# ===================== MQTT / Network =====================
def _mac_hex():
    return "".join("{:02X}".format(b) for b in wifi.radio.mac_address)


MQTT_CLIENT_ID = "magtag-" + _mac_hex()
print("MQTT client_id:", MQTT_CLIENT_ID)

# NOTE ON DESIGN:
# We run WiFi + MQTT through a small state machine with exponential backoff.
# This avoids tight reconnect loops (which can wedge sockets on embedded WiFi stacks),
# and lets us escalate recovery (WiFi reconnect / radio cycle) after repeated failures.

mqtt = None
mqtt_connected = False

# Broker / MQTT tuning
MQTT_KEEP_ALIVE = 60          # shorter keepalive tends to recover NAT/AP idle timeouts better
MQTT_SOCKET_TIMEOUT = 0.25    # connect/IO socket timeout (seconds) - must be <= MQTT_LOOP_TIMEOUT
MQTT_RECV_TIMEOUT = 10.0      # overall receive timeout (seconds)

# Service cadence
MQTT_LOOP_TIMEOUT = 0.50   # must be >= MQTT_SOCKET_TIMEOUT (MiniMQTT requirement)
MQTT_LOOP_INTERVAL_S = 0.05

# Health / recovery
MQTT_STALL_RESET_S = 45       # seconds without a successful mqtt.loop before forcing reconnect

# Backoff strategy
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 300.0         # cap at 5 minutes
BACKOFF_JITTER_MAX_S = 5.0
FAILS_BEFORE_WIFI_RECONNECT = 3
FAILS_BEFORE_RADIO_CYCLE = 6

# Publish pacing
PUBLISH_MIN_INTERVAL_S = 0.35
MQTT_GOOD_WINDOW_S = 3.0

# Timers / bookkeeping
next_mqtt_loop = 0.0
last_mqtt_good = 0.0
last_publish_attempt = 0.0

# Connection manager state
_net_failures = 0
_next_net_action = 0.0
_last_wifi_ok = False

# Publish queues
pending_starlink_payloads = []
pending_inverter_payloads = []
pending_timer_payloads = []
pending_timer_set_payloads = []
pending_water_payloads = []

next_gc = 0.0
GC_INTERVAL_S = 30.0

next_status_poll = 0.0
STATUS_POLL_S = 0.5


def _backoff_seconds(failures: int) -> float:
    # Exponential backoff with a small jitter.
    # failures=0 => immediate retry.
    if failures <= 0:
        return 0.0
    # 2, 4, 8, 16, ... seconds capped
    delay = BACKOFF_BASE_S * (2 ** (failures - 1))
    if delay > BACKOFF_MAX_S:
        delay = BACKOFF_MAX_S
    # Jitter (simple; avoids synchronizing with broker/AP timers)
    jitter = (time.monotonic() * 1000) % (BACKOFF_JITTER_MAX_S * 1000) / 1000.0
    return delay + jitter


def update_status_shapes(force=False):
    global _last_wifi_connected, _last_mqtt_connected, dirty

    wifi_ok = bool(wifi.radio.connected)
    mqtt_ok = bool(mqtt_connected)

    if force or (wifi_ok != _last_wifi_connected):
        set_circle_connected(wifi_circle, wifi_ok)
        _last_wifi_connected = wifi_ok
        dirty = True

    if force or (mqtt_ok != _last_mqtt_connected):
        set_circle_connected(mqtt_circle, mqtt_ok)
        _last_mqtt_connected = mqtt_ok
        dirty = True

    # Keep LOS indicator in sync on all pages
    update_los_indicator(force=force)


def show_page(page: int):
    global current_page, dirty
    if page == current_page:
        return
    current_page = page
    update_los_indicator(force=False)
    if current_page == PAGE_MAIN:
        display.root_group = main_group
    elif current_page == PAGE_SECOND:
        update_status_shapes(force=True)
        display.root_group = second_group
    elif current_page == PAGE_THIRD:
        display.root_group = third_group
    else:  # PAGE_FOUR
        display.root_group = fourth_group
    dirty = True


def _parse_on_off(msg: str) -> bool:
    return (msg or "").strip().upper() in ("1", "ON", "TRUE", "YES", "HIGH")


def mqtt_on_message(client, topic, message):
    global dirty, timer_time_value, timer_enabled
    global starlink_enabled, starlink_timer_mode
    global inverter_enabled, inverter_timer_mode
    global water_enabled, water_timer_mode
    global ac_fan_value, ac_temp_value, ac_set_value
    global battery_soc_value, battery_remain_value, battery_load_value
    global battery_pending_refresh
    global battery_soc_seen, battery_remain_seen, battery_load_seen
    global battery_bootstrap_refresh_done, battery_bootstrap_refresh_request
    global temp_in_value, temp_out_value
    global temp_set_value
    global temp_pending_refresh

    if isinstance(message, bytes):
        message = message.decode("utf-8", "ignore")

    msg = (message or "").strip()
    msg_upper = msg.upper()

    if topic == TOPIC_STARLINK_STATE:
        if msg_upper == "TIMER":
            starlink_timer_mode = True
            starlink_enabled = True
            set_main_label_state(0, True)
            if starlink_timer_lbl.text != "Timer":
                starlink_timer_lbl.text = "Timer"
                starlink_timer_lbl.color = BLACK
                dirty = True
        else:
            starlink_timer_mode = False
            if starlink_timer_lbl.text != "":
                starlink_timer_lbl.text = ""
                dirty = True
            starlink_enabled = _parse_on_off(msg)
            set_main_label_state(0, starlink_enabled)
        print("MQTT RX starlink =", message)

    elif topic == TOPIC_INVERTER_STATE:
        if msg_upper == "TIMER":
            inverter_timer_mode = True
            inverter_enabled = True
            set_main_label_state(1, True)
            if inverter_timer_lbl.text != "Timer":
                inverter_timer_lbl.text = "Timer"
                inverter_timer_lbl.color = BLACK
                dirty = True
        elif msg_upper == "3":
            inverter_timer_mode = False
            inverter_enabled = True
            if inverter_timer_lbl.text != "":
                inverter_timer_lbl.text = ""
                dirty = True
            set_main_label_state(1, True)
        elif msg_upper == "1":
            inverter_timer_mode = False
            inverter_enabled = False
            if inverter_timer_lbl.text != "":
                inverter_timer_lbl.text = ""
                dirty = True
            set_main_label_state(1, False)
        else:
            inverter_timer_mode = False
            inverter_enabled = False
            if inverter_timer_lbl.text != "":
                inverter_timer_lbl.text = ""
                dirty = True
            set_main_label_state(1, False)
        print("MQTT RX inverter =", message)

    elif topic == TOPIC_TIMER_STATE:
        timer_enabled = _parse_on_off(msg)
        set_main_label_state(2, timer_enabled)

        if timer_enabled and timer_time_value:
            if timer_time_lbl.text != timer_time_value:
                timer_time_lbl.text = timer_time_value
                timer_time_lbl.color = BLACK
                dirty = True
        else:
            if timer_time_lbl.text != "":
                timer_time_lbl.text = ""
                dirty = True
        print("MQTT RX timer =", message)

    elif topic == TOPIC_TIMER_TIME:
        timer_time_value = msg

        if timer_enabled and timer_time_value:
            if timer_time_lbl.text != timer_time_value:
                timer_time_lbl.text = timer_time_value
                timer_time_lbl.color = BLACK
                dirty = True

        if page3_time_lbl.text != timer_time_value:
            page3_time_lbl.text = timer_time_value
            dirty = True

        print("MQTT RX timer time =", message)

    elif topic == TOPIC_WATER_STATE:
        if msg_upper == "TIMER":
            water_timer_mode = True
            water_enabled = True
            set_page2_label_state(1, True)
            if water_timer_lbl.text != "Timer":
                water_timer_lbl.text = "Timer"
                water_timer_lbl.color = BLACK
                dirty = True
        else:
            water_timer_mode = False
            if water_timer_lbl.text != "":
                water_timer_lbl.text = ""
                dirty = True
            water_enabled = _parse_on_off(msg)
            set_page2_label_state(1, water_enabled)
        print("MQTT RX water =", message)

    elif topic == TOPIC_AC_FAN:
        ac_fan_value = msg
        if fan_status_lbl.text != ac_fan_value:
            fan_status_lbl.text = ac_fan_value
            fan_status_lbl.color = BLACK
            if current_page == PAGE_FOUR:
                dirty = True
        print("MQTT RX ac fan =", message)

    elif topic == TOPIC_AC_TEMP:
        ac_temp_value = msg
        new_text = "Current Temp: " + ac_temp_value
        if page4_temp_lbl.text != new_text:
            page4_temp_lbl.text = new_text
            if current_page == PAGE_FOUR:
                dirty = True
        print("MQTT RX ac temp =", message)

    elif topic == TOPIC_AC_SET:
        ac_set_value = msg
        new_text = "Set: " + ac_set_value
        if page4_set_lbl.text != new_text:
            page4_set_lbl.text = new_text
            if current_page == PAGE_FOUR:
                dirty = True
        print("MQTT RX ac set =", message)

    elif topic == TOPIC_BATTERY_SOC:
        battery_soc_value = msg
        battery_soc_seen = True

        soc_text = "Battery: " + battery_soc_value + "%"

        load_trimmed = trim_after_w(battery_load_value) if battery_load_value else ""
        if load_trimmed:
            soc_text = soc_text + "    " + load_trimmed  # 4 spaces before load

        if battery_soc_lbl.text != soc_text:
            battery_soc_lbl.text = soc_text
            battery_soc_lbl.color = BLACK
            battery_pending_refresh = True

        _maybe_request_battery_bootstrap_refresh()
        print("MQTT RX battery soc =", message)

    elif topic == TOPIC_BATTERY_REMAIN:
        battery_remain_value = trim_after_hrs(msg)
        battery_remain_seen = True

        new_text = "Remaining: " + battery_remain_value
        if battery_remain_lbl.text != new_text:
            battery_remain_lbl.text = new_text
            battery_remain_lbl.color = BLACK
            battery_pending_refresh = True

        _maybe_request_battery_bootstrap_refresh()
        print("MQTT RX battery remain =", message)

    elif topic == TOPIC_BATTERY_LOAD:
        battery_load_value = msg
        battery_load_seen = True

        load_trimmed = trim_after_w(battery_load_value)

        soc_text = "Battery: " + battery_soc_value + "%" if battery_soc_value else "Battery: "
        if load_trimmed:
            soc_text = soc_text + "    " + load_trimmed  # 4 spaces before load

        if battery_soc_lbl.text != soc_text:
            battery_soc_lbl.text = soc_text
            battery_soc_lbl.color = BLACK
            battery_pending_refresh = True

        _maybe_request_battery_bootstrap_refresh()
        print("MQTT RX battery load =", message)


    elif topic == TOPIC_TEMP_IN:
        temp_in_value = msg
        new_text = "In: " + (temp_in_value if temp_in_value else "--")
        if temp_in_lbl.text != new_text:
            temp_in_lbl.text = new_text
            temp_in_lbl.color = BLACK
            temp_pending_refresh = True
        print("MQTT RX temp in =", message)

    elif topic == TOPIC_TEMP_OUT:
        temp_out_value = msg
        new_text = "Out: " + (temp_out_value if temp_out_value else "--")
        if temp_out_lbl.text != new_text:
            temp_out_lbl.text = new_text
            temp_out_lbl.color = BLACK
            temp_pending_refresh = True
        print("MQTT RX temp out =", message)


    elif topic == TOPIC_TEMP_SET:
        # Store the setpoint used by Up/Down buttons (page 4).
        # Do not force an immediate eInk refresh here.
        temp_set_value = msg
        print("MQTT RX temp set =", message)


def _tcp_probe_to_broker() -> bool:
    """Quickly verify broker TCP accept() before doing a full MQTT connect."""
    try:
        pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
        sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect((MQTT_BROKER, MQTT_PORT))
        sock.close()
        return True
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False


def _mqtt_disconnect_local():
    """Drop local MQTT state and update UI (LOS/status) without spamming refreshes."""
    global mqtt, mqtt_connected
    if mqtt is not None:
        # Best-effort polite disconnect; these may not exist in all MiniMQTT versions.
        try:
            if hasattr(mqtt, "disconnect"):
                mqtt.disconnect()
        except Exception:
            pass
        try:
            if hasattr(mqtt, "deinit"):
                mqtt.deinit()
        except Exception:
            pass
    mqtt = None
    mqtt_connected = False
    update_los_indicator(force=False)
    if current_page == PAGE_SECOND:
        update_status_shapes(force=False)


def _mqtt_connect_and_subscribe():
    """Create a fresh MiniMQTT client and subscribe to all topics."""
    global mqtt, mqtt_connected, last_mqtt_good
    pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)

    mqtt = MQTT.MQTT(
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        socket_pool=pool,
        keep_alive=MQTT_KEEP_ALIVE,
        client_id=MQTT_CLIENT_ID,
        socket_timeout=MQTT_SOCKET_TIMEOUT,
        recv_timeout=MQTT_RECV_TIMEOUT,
    )
    mqtt.on_message = mqtt_on_message

    print("MQTT connecting to", MQTT_BROKER, MQTT_PORT, "...")
    rc = mqtt.connect()
    print("MQTT rc:", rc)

    if rc != 0:
        raise RuntimeError("MQTT connect returned rc={}".format(rc))

    mqtt_connected = True
    last_mqtt_good = time.monotonic()  # mark good immediately after connect()

    # Reset battery bootstrap refresh tracking for this MQTT session
    global battery_soc_seen, battery_remain_seen, battery_load_seen
    global battery_bootstrap_refresh_done, battery_bootstrap_refresh_request
    battery_soc_seen = False
    battery_remain_seen = False
    battery_load_seen = False
    battery_bootstrap_refresh_done = False
    battery_bootstrap_refresh_request = False

    mqtt.subscribe(TOPIC_STARLINK_STATE)
    mqtt.subscribe(TOPIC_INVERTER_STATE)
    mqtt.subscribe(TOPIC_TIMER_STATE)
    mqtt.subscribe(TOPIC_TIMER_TIME)
    mqtt.subscribe(TOPIC_WATER_STATE)
    mqtt.subscribe(TOPIC_AC_FAN)
    mqtt.subscribe(TOPIC_AC_TEMP)
    mqtt.subscribe(TOPIC_AC_SET)
    mqtt.subscribe(TOPIC_BATTERY_SOC)
    mqtt.subscribe(TOPIC_BATTERY_REMAIN)
    mqtt.subscribe(TOPIC_BATTERY_LOAD)
    mqtt.subscribe(TOPIC_TEMP_IN)
    mqtt.subscribe(TOPIC_TEMP_OUT)
    mqtt.subscribe(TOPIC_TEMP_SET)
    print("MQTT subscribed.")

    update_los_indicator(force=False)
    if current_page == PAGE_SECOND:
        update_status_shapes(force=False)


def _wifi_connect_if_needed():
    global _last_wifi_ok
    if wifi.radio.connected:
        _last_wifi_ok = True
        return True
    try:
        print("WiFi connecting...")
        wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
        print("WiFi connected:", wifi.radio.ipv4_address)
        _last_wifi_ok = True
        return True
    except Exception as e:
        print("WiFi failed:", repr(e))
        _last_wifi_ok = False
        return False


def _wifi_disconnect():
    try:
        wifi.radio.disconnect()
    except Exception:
        pass


def _wifi_cycle_radio():
    """Harder recovery step: toggle the radio power."""
    try:
        # Not all CP builds expose wifi.radio.enabled, so guard.
        if hasattr(wifi.radio, "enabled"):
            wifi.radio.enabled = False
            time.sleep(1.0)
            wifi.radio.enabled = True
    except Exception:
        pass


def ensure_network(now):
    """State-machine network service: WiFi -> broker probe -> MQTT connect, with exponential backoff."""
    global _net_failures, _next_net_action

    if mqtt_connected and mqtt is not None:
        return

    if now < _next_net_action:
        return

    # Step 1: WiFi
    if not _wifi_connect_if_needed():
        _mqtt_disconnect_local()
        _net_failures += 1
        delay = _backoff_seconds(_net_failures)
        print("NET backoff", _net_failures, "failures; retry in", delay, "s")
        _next_net_action = now + delay
        return

    # Step 2: Broker reachable (TCP probe)
    if not _tcp_probe_to_broker():
        print("TCP probe failed to broker")
        _mqtt_disconnect_local()
        _net_failures += 1
        delay = _backoff_seconds(_net_failures)
        print("NET backoff", _net_failures, "failures; retry in", delay, "s")
        if _net_failures >= FAILS_BEFORE_WIFI_RECONNECT:
            _wifi_disconnect()
        if _net_failures >= FAILS_BEFORE_RADIO_CYCLE:
            _wifi_cycle_radio()
            _wifi_disconnect()
        _next_net_action = now + delay
        return

    # Step 3: MQTT connect
    try:
        _mqtt_disconnect_local()  # always start with a clean MQTT object
        _mqtt_connect_and_subscribe()
        _net_failures = 0
        _next_net_action = now + 1.0  # small guard
    except Exception as e:
        print("MQTT connect failed:", repr(e))
        _mqtt_disconnect_local()
        _net_failures += 1
        delay = _backoff_seconds(_net_failures)
        print("NET backoff", _net_failures, "failures; retry in", delay, "s")
        if _net_failures >= FAILS_BEFORE_WIFI_RECONNECT:
            _wifi_disconnect()
        if _net_failures >= FAILS_BEFORE_RADIO_CYCLE:
            _wifi_cycle_radio()
            _wifi_disconnect()
        _next_net_action = now + delay


def service_mqtt(now):
    """Run mqtt.loop() on a steady cadence; drop/recover on stalls or exceptions."""
    global next_mqtt_loop, last_mqtt_good, _next_net_action, _net_failures
    if mqtt is None or not mqtt_connected:
        return
    if now < next_mqtt_loop:
        return
    next_mqtt_loop = now + MQTT_LOOP_INTERVAL_S

    # Stall watchdog: if mqtt.loop hasn't succeeded recently, force disconnect
    if (now - last_mqtt_good) > MQTT_STALL_RESET_S:
        print("mqtt stalled; forcing reconnect", now - last_mqtt_good, "s")
        _mqtt_disconnect_local()
        _net_failures = max(_net_failures, 1)
        _next_net_action = now + _backoff_seconds(_net_failures)
        return

    try:
        # Some MiniMQTT versions support timeout kwarg; others don't.
        try:
            mqtt.loop(timeout=MQTT_LOOP_TIMEOUT)
        except TypeError:
            mqtt.loop()
        last_mqtt_good = now
    except Exception as e:
        print("MQTT loop error:", repr(e))
        _mqtt_disconnect_local()
        _net_failures = max(_net_failures, 1)
        _next_net_action = now + _backoff_seconds(_net_failures)


def queue_starlink(payload: str):
    pending_starlink_payloads.append(payload)
    print("Queued Starlink ->", payload)


def queue_inverter(payload: str):
    pending_inverter_payloads.append(payload)
    print("Queued Inverter ->", payload)


def queue_water(payload: str):
    pending_water_payloads.append(payload)
    print("Queued Water ->", payload)


def queue_timer_set(payload: str):
    pending_timer_set_payloads.append(payload)
    print("Queued Timer SET ->", payload)


def queue_timer_toggle():
    global timer_enabled, timer_time_value, dirty

    next_state = not timer_enabled
    payload = "true" if next_state else "false"
    pending_timer_payloads.append(payload)
    print("Queued Timer toggle ->", payload)

    timer_enabled = next_state
    set_main_label_state(2, timer_enabled)

    if timer_enabled and timer_time_value:
        if timer_time_lbl.text != timer_time_value:
            timer_time_lbl.text = timer_time_value
            timer_time_lbl.color = BLACK
            dirty = True
    else:
        if timer_time_lbl.text != "":
            timer_time_lbl.text = ""
            dirty = True


def handle_starlink_short_press():
    global starlink_enabled, starlink_timer_mode, dirty
    if starlink_timer_mode:
        starlink_timer_mode = False
        starlink_enabled = True
        set_main_label_state(0, True)
        if starlink_timer_lbl.text != "":
            starlink_timer_lbl.text = ""
            dirty = True
        queue_starlink("on")
        return
    starlink_timer_mode = False
    if starlink_timer_lbl.text != "":
        starlink_timer_lbl.text = ""
        dirty = True
    starlink_enabled = not starlink_enabled
    set_main_label_state(0, starlink_enabled)
    queue_starlink("on" if starlink_enabled else "off")


def handle_starlink_long_press():
    global starlink_enabled, starlink_timer_mode, dirty
    starlink_timer_mode = True
    starlink_enabled = True
    set_main_label_state(0, True)
    if starlink_timer_lbl.text != "Timer":
        starlink_timer_lbl.text = "Timer"
        starlink_timer_lbl.color = BLACK
        dirty = True
    queue_starlink("timer")


def handle_inverter_short_press():
    global inverter_enabled, inverter_timer_mode, dirty
    if inverter_timer_mode:
        inverter_timer_mode = False
        inverter_enabled = True
        set_main_label_state(1, True)
        if inverter_timer_lbl.text != "":
            inverter_timer_lbl.text = ""
            dirty = True
        queue_inverter("3")
        return
    inverter_timer_mode = False
    if inverter_timer_lbl.text != "":
        inverter_timer_lbl.text = ""
        dirty = True
    inverter_enabled = not inverter_enabled
    set_main_label_state(1, inverter_enabled)
    queue_inverter("3" if inverter_enabled else "1")


def handle_inverter_long_press():
    global inverter_enabled, inverter_timer_mode, dirty
    inverter_timer_mode = True
    inverter_enabled = True
    set_main_label_state(1, True)
    if inverter_timer_lbl.text != "Timer":
        inverter_timer_lbl.text = "Timer"
        inverter_timer_lbl.color = BLACK
        dirty = True
    queue_inverter("timer")


def handle_water_short_press():
    global water_enabled, water_timer_mode
    global ac_fan_value, ac_temp_value, ac_set_value, dirty
    if water_timer_mode:
        water_timer_mode = False
        water_enabled = True
        set_page2_label_state(1, True)
        if water_timer_lbl.text != "":
            water_timer_lbl.text = ""
            dirty = True
        queue_water("on")
        return
    water_timer_mode = False
    if water_timer_lbl.text != "":
        water_timer_lbl.text = ""
        dirty = True
    water_enabled = not water_enabled
    set_page2_label_state(1, water_enabled)
    queue_water("on" if water_enabled else "off")


def handle_water_long_press():
    global water_enabled, water_timer_mode
    global ac_fan_value, ac_temp_value, ac_set_value, dirty
    water_timer_mode = True
    water_enabled = True
    set_page2_label_state(1, True)
    if water_timer_lbl.text != "Timer":
        water_timer_lbl.text = "Timer"
        water_timer_lbl.color = BLACK
        dirty = True
    queue_water("timer")


def adjust_timer_time(delta_minutes: int):
    """Adjust timer_time_value by delta_minutes (wrap 24h), update UI, publish magtag/timer/set."""
    global timer_time_value, dirty

    m = parse_hhmm_to_minutes(timer_time_value)
    if m is None:
        m = 0  # default if unknown
    m = (m + int(delta_minutes)) % (24 * 60)
    timer_time_value = minutes_to_hhmm(m)

    # Update page 3 always
    if page3_time_lbl.text != timer_time_value:
        page3_time_lbl.text = timer_time_value
        dirty = True

    # Update page 1 timer-time label only if enabled
    if timer_enabled and timer_time_value:
        if timer_time_lbl.text != timer_time_value:
            timer_time_lbl.text = timer_time_value
            timer_time_lbl.color = BLACK
            dirty = True

    queue_timer_set(timer_time_value)


def can_publish(now) -> bool:
    if mqtt is None or not mqtt_connected:
        return False
    if (now - last_mqtt_good) > MQTT_GOOD_WINDOW_S:
        return False
    return True


def service_publish_queue(now):
    """Publish queued button actions at a controlled cadence.

    This prevents spamming the broker, but ensures queued actions do get sent.
    """
    global last_publish_attempt

    if not can_publish(now):
        return
    if (now - last_publish_attempt) < PUBLISH_MIN_INTERVAL_S:
        return

    topic = None
    payload = None

    if pending_starlink_payloads:
        topic = TOPIC_STARLINK_BUTTON
        payload = pending_starlink_payloads.pop(0)
    elif pending_inverter_payloads:
        topic = TOPIC_INVERTER_BUTTON
        payload = pending_inverter_payloads.pop(0)
    elif pending_water_payloads:
        topic = TOPIC_WATER_BUTTON
        payload = pending_water_payloads.pop(0)
    elif pending_timer_set_payloads:
        topic = TOPIC_TIMER_SET
        payload = pending_timer_set_payloads.pop(0)
    elif pending_timer_payloads:
        topic = TOPIC_TIMER_BUTTON
        payload = pending_timer_payloads.pop(0)
    else:
        return

    # Attempt publish; if it fails, requeue at the front so it isn't lost.
    last_publish_attempt = now
    try:
        mqtt.publish(topic, payload)
        print("MQTT TX", payload, "->", topic)
    except Exception as e:
        print("MQTT publish failed (requeued):", repr(e))
        try:
            if topic == TOPIC_STARLINK_BUTTON:
                pending_starlink_payloads.insert(0, payload)
            elif topic == TOPIC_INVERTER_BUTTON:
                pending_inverter_payloads.insert(0, payload)
            elif topic == TOPIC_WATER_BUTTON:
                pending_water_payloads.insert(0, payload)
            elif topic == TOPIC_TIMER_SET:
                pending_timer_set_payloads.insert(0, payload)
            elif topic == TOPIC_TIMER_BUTTON:
                pending_timer_payloads.insert(0, payload)
        except Exception:
            pass
        _mqtt_disconnect_local()
        return


def publish_temp_change(delta):
    """Publish a +/- 1 change using TOPIC_TEMP_SET as the current value."""
    global temp_set_value

    # Determine current setpoint
    current = None
    try:
        if temp_set_value is not None and str(temp_set_value).strip() != "":
            current = int(float(str(temp_set_value).strip()))
    except Exception:
        current = None

    # Fallback to AC set if temp/set hasn't arrived yet
    if current is None:
        try:
            if ac_set_value is not None and str(ac_set_value).strip() != "":
                current = int(float(str(ac_set_value).strip()))
        except Exception:
            current = None

    if current is None:
        print("Temp change ignored (no current setpoint yet)")
        return

    new_val = current + int(delta)

    if mqtt is None or not mqtt_connected:
        print("Temp change ignored (MQTT not connected)")
        return

    # Publish immediately (do not queue; user expects instant response)
    try:
        mqtt.publish(TOPIC_TEMP_CHANGE, str(new_val))
        temp_set_value = str(new_val)  # optimistic local update for rapid button presses
        print("MQTT TX temp change =", new_val)
    except Exception as e:
        print("MQTT publish temp change failed:", repr(e))


    return


# ===================== Init =====================
for i in range(4):
    set_main_label_state(i, False)
for i in range(4):
    set_page2_label_state(i, False)

page3_time_lbl.text = timer_time_value

apply_brightness()
display.root_group = main_group
update_los_indicator(force=False)
dirty = True
try_refresh(time.monotonic())

# ===================== Main loop =====================
while True:
    # Feed watchdog early each loop to guard against hangs in network/display drivers
    try:
        microcontroller.watchdog.feed()
    except Exception:
        pass

    now = time.monotonic()
    if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
        print('heartbeat', now)
        last_heartbeat = now
    if now - last_heap_report >= HEAP_REPORT_INTERVAL_S:
        try:
            import gc
            gc.collect()
            free = gc.mem_free()
            alloc = gc.mem_alloc()
            print('heap free/alloc:', free, '/', alloc)
        except Exception as e:
            print('heap report failed:', repr(e))
        last_heap_report = now

    now = time.monotonic()

    if now >= next_gc:
        next_gc = now + GC_INTERVAL_S
        gc.collect()

    if current_page == PAGE_SECOND and now >= next_status_poll:
        next_status_poll = now + STATUS_POLL_S
        update_status_shapes(force=False)

    for i, b in enumerate(buttons):
        pressed = not b.value

        if pressed != last_pressed[i] and (now - last_debounce_time[i]) > DEBOUNCE_S:
            last_pressed[i] = pressed
            last_debounce_time[i] = now

            if pressed:
                press_start_time[i] = now
                press_start_page[i] = current_page

                leds_on()
                led_off_at = now + LED_ON_SECONDS

                if current_page == PAGE_MAIN:
                    if i == 3:
                        show_page(PAGE_SECOND)
                        dirty = True

                elif current_page == PAGE_SECOND:
                    if i == 0:
                        show_page(PAGE_MAIN)
                        dirty = True
                    elif i == 2:
                        show_page(PAGE_FOUR)
                        dirty = True
                    elif i == 3:
                        brightness_index = (brightness_index + 1) % len(BRIGHTNESS_LEVELS)
                        save_brightness_index(brightness_index)
                        apply_brightness()
                        pixels.show()
                        print("Brightness set to", int(BRIGHTNESS_LEVELS[brightness_index] * 100), "%")
                        dirty = True

                elif current_page == PAGE_THIRD:
                    if i == 0:
                        show_page(PAGE_MAIN)
                        dirty = True
                    # Earlier/Later handled on RELEASE

                else:  # PAGE_FOUR
                    if i == 0:
                        show_page(PAGE_MAIN)
                        dirty = True
                    elif i == 1:
                        # Down button: decrement setpoint by 1
                        publish_temp_change(-1)
                    elif i == 2:
                        # Up button: increment setpoint by 1
                        publish_temp_change(1)
            else:
                held = now - press_start_time[i]
                started_on = press_start_page[i]

                if started_on == PAGE_MAIN:
                    if i == 0:
                        if held >= LONG_PRESS_S:
                            handle_starlink_long_press()
                        else:
                            handle_starlink_short_press()
                        dirty = True
                    elif i == 1:
                        if held >= LONG_PRESS_S:
                            handle_inverter_long_press()
                        else:
                            handle_inverter_short_press()
                        dirty = True
                    elif i == 2:
                        if held >= LONG_PRESS_S:
                            page3_time_lbl.text = timer_time_value
                            show_page(PAGE_THIRD)
                            dirty = True
                        else:
                            queue_timer_toggle()
                            dirty = True

                elif started_on == PAGE_SECOND and i == 1:
                    if held >= LONG_PRESS_S:
                        handle_water_long_press()
                    else:
                        handle_water_short_press()
                    dirty = True

                elif started_on == PAGE_THIRD:
                    # Earlier/Later adjust by 30 minutes and publish to magtag/timer/set
                    if i == 1:
                        adjust_timer_time(-30)
                    elif i == 2:
                        adjust_timer_time(+30)

    if led_off_at and now >= led_off_at:
        leds_off()
        led_off_at = 0.0

    ensure_network(now)
    service_mqtt(now)
    service_publish_queue(now)


    # Battery refresh throttling:
    # If battery topics updated but nothing else caused a refresh, allow one refresh
    # 60 minutes after the last refresh time.
    if battery_pending_refresh and (now - last_refresh_time) >= BATTERY_REFRESH_INTERVAL_S:
        dirty = True
        battery_pending_refresh = False

    # In/Out temp refresh throttling (main page):
    if temp_pending_refresh and (now - last_refresh_time) >= TEMP_REFRESH_INTERVAL_S:
        dirty = True
        temp_pending_refresh = False

    # One forced refresh after first receipt of SOC+Remaining+Load following MQTT connect
    if battery_bootstrap_refresh_request:
        dirty = True
    try_refresh(now)
    time.sleep(0.01)