#!/usr/bin/env python3
"""
give_laptop_ac - Full-hardware TUI for MSI laptops with msi-ec kernel module.
Supports: Cyborg 15 A12U, and compatible MSI laptops.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import pynvml
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Container, Grid, Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    Collapsible,
    DataTable,
    Footer,
    Header,
    Label,
    Static,
    Sparkline,
    TabbedContent,
    TabPane,
)
from textual.widgets._header import HeaderTitle

from config import (
    AlertsConfig,
    FanCurve,
    LoggingConfig,
    Settings,
    load_config,
    save_config,
)
from hardware import WriteResult, apply_verified, read_attr, write_verified
from fan_backend import BackendError, FanBackend
from telemetry import TelemetrySampler, number
from dashboard import OverviewCard, reading

# ─── constants & paths ──────────────────────────────────────────────────────
MSI_EC = Path("/sys/devices/platform/msi-ec")
POWER_SUPPLY = Path("/sys/class/power_supply")
LEDS = Path("/sys/class/leds")

# ─── helpers ────────────────────────────────────────────────────────────────

def ec_read(rel: str) -> Optional[str]:
    return read_attr(MSI_EC / rel)


def ec_write(rel: str, val: str) -> WriteResult:
    return write_verified(MSI_EC / rel, val)


def _bat_thresh_path(kind: str = "end") -> Optional[Path]:
    for supply in sorted(POWER_SUPPLY.glob("*")):
        attribute = supply / f"charge_control_{kind}_threshold"
        if attribute.exists():
            return attribute
    return None


def read_bat_limit(kind: str = "end") -> Optional[int]:
    value = number(read_attr(_bat_thresh_path(kind)))
    return int(value) if value is not None else None


def write_bat_limit(pct: int, kind: str = "end") -> WriteResult:
    if not 0 <= pct <= 100:
        return WriteResult(False, "Battery threshold must be between 0 and 100%")
    return write_verified(_bat_thresh_path(kind), str(pct))


def _kbd_path() -> Optional[Path]:
    for directory in (LEDS / "msiacpi::kbd_backlight", MSI_EC / "leds"):
        if (directory / "brightness").exists():
            return directory
    return None


def kbd_max() -> int:
    directory = _kbd_path()
    value = number(read_attr(directory / "max_brightness")) if directory else None
    return int(value) if value is not None else 0


def read_kbd() -> Optional[int]:
    directory = _kbd_path()
    value = number(read_attr(directory / "brightness")) if directory else None
    return int(value) if value is not None else None


def write_kbd(level: int) -> WriteResult:
    directory = _kbd_path()
    if not 0 <= level <= kbd_max():
        return WriteResult(False, "Keyboard brightness is outside the supported range")
    return write_verified(directory / "brightness" if directory else None, str(level))


# ─── widgets ────────────────────────────────────────────────────────────────

class SparkCard(Container):
    def __init__(self, spark_id: str, title: str, color: str = "dodgerblue", **kwargs):
        super().__init__(**kwargs)
        self.spark_id = spark_id
        self.title_text = title
        self.color = color
        self.history: list[float] = []
        self._sparkline: Sparkline | None = None
        self._value = Static("N/A", classes="spark-value")

    def compose(self) -> ComposeResult:
        color = Color.parse(self.color)
        title = Label(self.title_text, classes="spark-title")
        title.styles.color = color
        yield title
        yield self._value
        self._sparkline = Sparkline([], min_color=color.with_alpha(0.4), max_color=color)
        self._sparkline.display = False
        yield self._sparkline

    def update(self, value: float | None, reason: str = "No current reading from this sensor") -> None:
        value = number(value)
        self._value.update("N/A" if value is None else f"{value:.1f}")
        self.tooltip = reason if value is None else None
        if self._sparkline is not None:
            self._sparkline.display = value is not None
        if value is None:
            self.history.clear()
            if self._sparkline is not None:
                self._sparkline.data = []
            return
        self.history.append(value)
        if len(self.history) > 60:
            self.history.pop(0)
        if self._sparkline is not None:
            # A new list tells Textual to redraw the chart after each sample.
            self._sparkline.data = self.history.copy()


class CoreBar(Static):
    def __init__(self, core: int, **kwargs):
        super().__init__(**kwargs)
        self.core = core
        self.history: list[float] = []

    def compose(self) -> ComposeResult:
        core_count = psutil.cpu_count(logical=True) or 4
        color = Color.from_hsl(self.core / core_count, 0.7, 0.65)
        label = Label(f"Core {self.core}", classes="core-label")
        label.styles.color = color
        yield label
        sparkline = Sparkline(
            [], id=f"core-{self.core}", min_color=color.with_alpha(0.4), max_color=color
        )
        sparkline.display = False
        yield sparkline

    def update(self, pct: float | None) -> None:
        if pct is None:
            self.history.clear()
        else:
            self.history.append(pct)
        if len(self.history) > 60:
            self.history.pop(0)
        try:
            sparkline = self.query_one(f"#core-{self.core}", Sparkline)
            sparkline.display = pct is not None
            sparkline.data = self.history.copy()
        except Exception:
            pass


class IoCard(Static):
    def __init__(self, io_id: str, **kwargs):
        super().__init__(**kwargs)
        self.io_id = io_id
        self.history: list[float] = []

    def compose(self) -> ComposeResult:
        yield Label(self.io_id.upper().replace("-", " "), classes="io-label")
        yield Sparkline([], id=self.io_id)

    def update(self, value: float) -> None:
        self.history.append(value)
        if len(self.history) > 60:
            self.history.pop(0)
        try:
            self.query_one(f"#{self.io_id}", Sparkline).data = self.history.copy()
        except Exception:
            pass


class CtrlRow(Static):
    def __init__(self, label: str, options: list[tuple[str, str]], cid: str, id: str | None = None):
        super().__init__(id=id)
        self.label = label
        self.options = options
        self.cid = cid
        self._active_val: str = ""

    def compose(self) -> ComposeResult:
        yield Label(self.label, classes="cr-lbl")
        with Horizontal(classes="cr-opts"):
            for lbl, val in self.options:
                yield Button(lbl, id=f"{self.cid}-{val}", classes="cbtn")

    def activate(self, val: str) -> None:
        self._active_val = val
        for _, v in self.options:
            try:
                btn = self.query_one(f"#{self.cid}-{v}", Button)
                btn.set_class(v == val, "-on")
            except Exception:
                pass

    @on(Button.Pressed, ".cbtn")
    def on_cbtn(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid.startswith(f"{self.cid}-"):
            val = bid.removeprefix(f"{self.cid}-")
            self.app._write_ec(f"{self.cid}_mode", val)


# ─── main app ────────────────────────────────────────────────────────────────

class GiveLaptopAC(App):
    TITLE = "give_laptop_ac"
    SUB_TITLE = "MSI Cyborg 15 A12U"
    AUTO_FOCUS = "#dash-scroll"
    BINDINGS = [
        ("d", "show_tab('dash')", "Dash"),
        ("o", "show_tab('ctrl')", "Controls"),
        ("p", "show_tab('procs')", "Procs"),
        Binding("j", "navigate('scroll_down')", "Scroll", key_display="j/k"),
        Binding("k", "navigate('scroll_up')", "", show=False),
        Binding("f", "navigate('page_down')", "Page", key_display="f/b"),
        Binding("b", "navigate('page_up')", "", show=False),
        Binding("h", "navigate('scroll_left')", "", show=False),
        Binding("l", "navigate('scroll_right')", "", show=False),
        ("q", "quit", "Quit"),
        Binding("1", "show_tab('dash')", "", show=False),
        Binding("2", "show_tab('ctrl')", "", show=False),
        Binding("3", "show_tab('procs')", "", show=False),
        Binding("v", "toggle_details", "", show=False),
        ("c", "boost", "Boost"),
        ("r", "refresh_now", "Refresh"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._config: Settings = load_config()
        self._sort: str = "cpu"
        self._pids: list[int] = []
        self._nvml_ok: bool = False
        self._nvml_reason = "NVIDIA NVML has not been probed"
        self._nvml_retry_at = 0.0
        self._gpu_name = "NVIDIA GPU"
        self._status_until = 0.0
        self._fan_backend = FanBackend()
        self._backend_busy = False
        self._backend_probing = False
        self._spark_cards: dict[str, SparkCard] = {}  # Store references to spark cards
        self._connect_nvml()
        self._telemetry = TelemetrySampler(
            ec_read,
            nvml_available=self._nvml_ok,
            nvml_reason=self._nvml_reason,
        )

    def _connect_nvml(self) -> bool:
        """Connect or reconnect telemetry after a sleeping dGPU becomes active."""
        if self._nvml_ok:
            return True
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            self._gpu_name = name.decode(errors="replace") if isinstance(name, bytes) else str(name)
            self._nvml_ok = True
            self._nvml_reason = ""
        except Exception as error:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml_ok = False
            self._nvml_reason = f"NVIDIA telemetry unavailable: {error}"
            self._nvml_retry_at = time.monotonic() + 30
        return self._nvml_ok

    CSS = """
    Screen { background: transparent; }
    Header, Footer, TabbedContent, TabbedContent > ContentSwitcher, TabPane,
    #dash-scroll, #ctrl-scroll {
        background: transparent;
    }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; padding: 1 1 0 1; }

    /* ── dashboard ── */
    #dash-scroll, #ctrl-scroll {
        height: 1fr;
        scrollbar-gutter: stable;
    }
    #dash-heading { height: 1; text-style: bold; color: $text; }
    #dash-context { height: auto; color: $text-muted; margin-bottom: 1; }
    #overview-grid { height: 12; grid-size: 2; grid-rows: 6; grid-gutter: 0 1; }
    #dash-scroll.wide #overview-grid { height: 6; grid-size: 4; }
    #dash-scroll.narrow #overview-grid { height: 24; grid-size: 1; }
    OverviewCard { height: 6; border: round $surface-lighten-2; padding: 0 1; }
    .overview-title, .overview-value, .overview-detail { height: 1; }
    .overview-title { text-style: bold; }
    .overview-value { text-style: bold; }
    .overview-detail { color: $text-muted; }
    OverviewCard Sparkline { height: 1; min-width: 0; }
    #dash-cooling, #dash-activity { height: auto; padding: 0 1; }
    #dash-cooling { color: #4dabf7; margin-top: 1; }
    #dash-activity { color: #20c997; margin-bottom: 1; }
    #dash-details, #core-details { height: auto; padding: 0; margin: 0; border: none; }
    #dash-details > Contents, #core-details > Contents { padding: 0; }
    .section {
        height: auto;
        margin-bottom: 0;
        padding: 0 1;
    }
    .section-title {
        color: $primary;
        text-style: bold;
        margin: 0 0;
        padding: 0 1;
        height: 1;
    }
    #row1, #row2, #row3, #row4, #row5, #row6, #row7, #row8 { height: auto; margin-bottom: 1; }
    #core-box {
        border: round $primary;
        border-title-align: left;
        padding: 1;
        height: auto;
    }
    #core-box > Horizontal, #core-left, #core-right { height: auto; }
    CoreBar { height: 4; }
    .core-label { width: 8; color: $text-muted; }
    .io-label { width: 10; color: $text-muted; }
    .spark-title { color: $text-muted; margin-bottom: 0; height: 1; }
    .spark-value { height: 1; text-style: bold; }
    Sparkline { height: 3; min-width: 10; }
    SparkCard Sparkline { height: 2; }
    SparkCard { height: 4; width: 1fr; margin: 0 1; }
    Horizontal { width: 1fr; }

    /* ── controls ── */
    #presets, #hwbox, #extrabox, CtrlRow { width: auto; min-width: 100%; }
    #preset-row, .cr-opts, .ex-row { width: auto; min-width: 100%; }
    #presets { height: 5; margin-bottom: 1; }
    #preset-row Button.-on { background: $primary; color: $text; }
    #hwbox { height: auto; margin-bottom: 1; }
    #extrabox { height: auto; }
    .cr-lbl { width: 14; color: $text-muted; }
    .cr-opts { height: 3; }
    .cbtn { margin-right: 1; }
    .cbtn.-on { background: $primary; color: $text; }
    .ex-row { height: 3; margin-bottom: 1; }
    .ex-lbl { width: 14; color: $text-muted; }
    .tbtn { margin-right: 1; }
    .tbtn.-on { background: $success; color: $text; }
    .bl-btn, .bcs-btn, .bce-btn, .kbd-btn { margin-right: 1; min-width: 5; }
    .bl-btn.-on, .bcs-btn.-on, .bce-btn.-on, .kbd-btn.-on { background: $primary; color: $text; }

    /* ── processes ── */
    #proc-bar { height: 4; overflow-x: auto; }
    #proc-bar Button { min-width: 0; }
    .sort-btn { margin-right: 1; }
    .sort-btn.-on { background: $primary; color: $text; }
    #kill-btn { margin-left: 1; background: $error; }
    #drop-btn { margin-left: 1; }
    #proc-status { margin-left: 2; color: $text-muted; }
    DataTable { height: 1fr; }

    /* ── global ── */
    #status { height: 1; background: $panel; color: $text-muted; padding: 0 2; }
    #backend-status, #curve-points { height: auto; width: 1fr; padding: 0 1; }
    #backend-status { color: $text-muted; }
    #curve-points { color: #4dabf7; }
    #cooling-box { height: auto; width: 1fr; border: round $primary; padding: 0 1; margin-top: 1; }
    #curve-actions { height: 6; grid-size: 3; grid-rows: 3; grid-gutter: 0 1; }
    #curve-actions Button { width: 1fr; min-width: 0; }
    #curve-setup-help { height: auto; color: $text-muted; display: none; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs", initial="dash"):

            # ── 📊 Dashboard ─────────────────────────────────────────────
            with TabPane("📊 Dashboard", id="dash"):
                with ScrollableContainer(id="dash-scroll"):
                    yield Static("OVERVIEW · v: detailed charts", id="dash-heading", markup=False)
                    yield Static("Reading hardware state…", id="dash-context", markup=False)
                    with Grid(id="overview-grid"):
                        yield OverviewCard("CPU", "#f783ac", id="overview-cpu")
                        yield OverviewCard("GPU", "#ff922b", id="overview-gpu")
                        yield OverviewCard("MEMORY", "#9775fa", id="overview-memory")
                        yield OverviewCard("BATTERY", "#51cf66", id="overview-battery")
                    yield Static("Cooling · waiting for readings", id="dash-cooling", markup=False)
                    yield Static("Activity · waiting for readings", id="dash-activity", markup=False)
                    with Collapsible(title="Sensor charts · v to expand/collapse", collapsed=True, id="dash-details"):
                        yield from self._compose_sensor_charts()
                    with Collapsible(title="CPU cores", collapsed=True, id="core-details"):
                        n = psutil.cpu_count(logical=True) or 4
                        with Container(id="core-box"):
                            with Horizontal():
                                with Vertical(id="core-left"):
                                    for i in range(n // 2):
                                        yield CoreBar(i)
                                with Vertical(id="core-right"):
                                    for i in range(n // 2, n):
                                        yield CoreBar(i)

            yield from self._compose_controls_and_processes()

        yield Footer(compact=True, show_command_palette=False)
        yield Static("", id="status")

    def _compose_sensor_charts(self) -> ComposeResult:
        # Create and store spark cards for later updates
        self._spark_cards["sc-ct"] = SparkCard("sc-ct", "CPU Temp °C", "#ff6b6b")
        self._spark_cards["sc-gt"] = SparkCard("sc-gt", "GPU Temp °C", "#ffa94d")
        self._spark_cards["sc-cp"] = SparkCard("sc-cp", "CPU Pkg W", "#ffd43b")
        self._spark_cards["sc-gp"] = SparkCard("sc-gp", "GPU Power W", "#c0eb75")
        self._spark_cards["sc-cf"] = SparkCard("sc-cf", "CPU Fan %", "#4dabf7")
        self._spark_cards["sc-gf"] = SparkCard("sc-gf", "GPU Fan %", "#3bc9db")
        self._spark_cards["sc-ram"] = SparkCard("sc-ram", "RAM %", "#9775fa")
        self._spark_cards["sc-vram"] = SparkCard("sc-vram", "VRAM %", "#da77f2")
        self._spark_cards["sc-bat"] = SparkCard("sc-bat", "Battery %", "#51cf66")
        self._spark_cards["sc-cu"] = SparkCard("sc-cu", "CPU Load %", "#f783ac")
        self._spark_cards["sc-gu"] = SparkCard("sc-gu", "GPU Load %", "#ff922b")
        self._spark_cards["sc-freq"] = SparkCard("sc-freq", "CPU MHz", "#a9e34b")
        self._spark_cards["sc-netu"] = SparkCard("sc-netu", "Net ↑ MB/s", "#20c997")
        self._spark_cards["sc-netd"] = SparkCard("sc-netd", "Net ↓ MB/s", "#66d9e8")
        self._spark_cards["sc-diskr"] = SparkCard("sc-diskr", "Disk R MB/s", "#748ffc")
        self._spark_cards["sc-diskw"] = SparkCard("sc-diskw", "Disk W MB/s", "#e599f7")
        self._spark_cards["sc-volt"] = SparkCard("sc-volt", "CPU Volt", "#ffec99")
        self._spark_cards["sc-gvolt"] = SparkCard("sc-gvolt", "GPU Volt", "#ffc9c9")
        self._spark_cards["sc-cclk"] = SparkCard("sc-cclk", "CPU Clk MHz", "#a5d8ff")
        self._spark_cards["sc-gclk"] = SparkCard("sc-gclk", "GPU Clk MHz", "#96f2d7")

        # ── Thermal ──
        with Container(id="section-thermal", classes="section"):
            yield Label("🌡 Thermal", classes="section-title")
            with Horizontal(id="row1"):
                yield self._spark_cards["sc-ct"]
                yield self._spark_cards["sc-gt"]

        # ── Power ──
        with Container(id="section-power", classes="section"):
            yield Label("⚡ Power", classes="section-title")
            with Horizontal(id="row2"):
                yield self._spark_cards["sc-cp"]
                yield self._spark_cards["sc-gp"]

        # ── Fans ──
        with Container(id="section-fans", classes="section"):
            yield Label("🌀 Fans", classes="section-title")
            with Horizontal(id="row3"):
                yield self._spark_cards["sc-cf"]
                yield self._spark_cards["sc-gf"]

        # ── Memory ──
        with Container(id="section-memory", classes="section"):
            yield Label("💾 Memory", classes="section-title")
            with Horizontal(id="row4"):
                yield self._spark_cards["sc-ram"]
                yield self._spark_cards["sc-vram"]
                yield self._spark_cards["sc-bat"]

        # ── Load ──
        with Container(id="section-load", classes="section"):
            yield Label("📈 Load", classes="section-title")
            with Horizontal(id="row5"):
                yield self._spark_cards["sc-cu"]
                yield self._spark_cards["sc-gu"]
                yield self._spark_cards["sc-freq"]

        # ── Network ──
        with Container(id="section-net", classes="section"):
            yield Label("🌐 Network", classes="section-title")
            with Horizontal(id="row6"):
                yield self._spark_cards["sc-netu"]
                yield self._spark_cards["sc-netd"]

        # ── Storage ──
        with Container(id="section-storage", classes="section"):
            yield Label("💿 Storage", classes="section-title")
            with Horizontal(id="row7"):
                yield self._spark_cards["sc-diskr"]
                yield self._spark_cards["sc-diskw"]

        # ── Sensors ──
        with Container(id="section-sensors", classes="section"):
            yield Label("🔧 Sensors", classes="section-title")
            with Horizontal(id="row8"):
                yield self._spark_cards["sc-volt"]
                yield self._spark_cards["sc-gvolt"]
                yield self._spark_cards["sc-cclk"]
                yield self._spark_cards["sc-gclk"]


    def _compose_controls_and_processes(self) -> ComposeResult:
        # ── 🎮 Controls ──────────────────────────────────────────────
        with TabPane("🎮 Controls", id="ctrl"):
            with ScrollableContainer(id="ctrl-scroll"):
                with Container(id="presets"):
                    with Horizontal(id="preset-row"):
                        yield Button("🎮 Gaming", id="p-gaming")
                        yield Button("🤖 AI Mode", id="p-ai")
                        yield Button("⚖  Balanced", id="p-balanced")
                        yield Button("🌙 Silent", id="p-silent")

                with Container(id="hwbox"):
                    yield CtrlRow(
                        "Performance",
                        [("🌿 Eco", "eco"), ("⚖ Comfort", "comfort"), ("🚀 Turbo", "turbo")],
                        cid="shift", id="shift-row",
                    )
                    yield CtrlRow(
                        "Fan Mode",
                        [("🔄 Auto", "auto"), ("🤫 Silent", "silent"), ("⚙ Advanced", "advanced")],
                        cid="fan", id="fan-row",
                    )
                    with Horizontal(id="toggle-row", classes="ex-row"):
                        yield Label("Toggles", classes="ex-lbl")
                        yield Button("Cooler Boost [c]", id="boost-btn", classes="tbtn")
                        yield Button("Super Battery", id="supbat-btn", classes="tbtn")
                        yield Button("Webcam", id="webcam-btn", classes="tbtn")
                        yield Button("Fn/Win Swap", id="fnswap-btn", classes="tbtn")

                with Container(id="extrabox"):
                    with Horizontal(classes="ex-row"):
                        yield Label("Battery Limit", classes="ex-lbl")
                        for p in (60, 70, 80, 90, 100):
                            yield Button(f"{p}%", id=f"bl-{p}", classes="bl-btn")

                    with Horizontal(classes="ex-row"):
                        yield Label("Charge Start", classes="ex-lbl")
                        for p in (20, 30, 40, 50, 60, 70, 80, 90):
                            yield Button(f"{p}%", id=f"bcs-{p}", classes="bcs-btn")

                    with Horizontal(classes="ex-row"):
                        yield Label("Charge End", classes="ex-lbl")
                        for p in (60, 70, 80, 90, 100):
                            yield Button(f"{p}%", id=f"bce-{p}", classes="bce-btn")

                    with Horizontal(classes="ex-row"):
                        yield Label("Keyboard Light", classes="ex-lbl")
                        yield Button("Off", id="kbd-0", classes="kbd-btn")
                        for lv in range(1, kbd_max() + 1):
                            yield Button(str(lv), id=f"kbd-{lv}", classes="kbd-btn")

                with Container(id="cooling-box"):
                    yield Static("Connecting to fan-control service…", id="backend-status", markup=False)
                    with Grid(id="curve-actions"):
                        yield Button("Read Curve", id="curve-read", classes="curve-btn")
                        yield Button("Write Perf", id="curve-perf", classes="curve-btn")
                        yield Button("Write Silent", id="curve-silent", classes="curve-btn")
                        yield Button("Restore Auto", id="curve-reset", classes="curve-btn")
                        yield Button("Reconnect", id="backend-reconnect")
                        yield Button("Setup", id="curve-setup")
                    yield Static(
                        "Custom curves need the ec_sys driver and the updated control service.\n"
                        "From the project directory:\n"
                        "  cmake --build msi-ec-daemon/build -j 4\n"
                        "  sudo bash msi-ec-daemon/install.sh --enable-curves --start\n"
                        "Then select Reconnect. This keeps firmware temperature steps fixed.",
                        id="curve-setup-help", markup=False,
                    )
                    yield Static("", id="curve-points", markup=False)

        # ── ⚙ Processes ──────────────────────────────────────────────
        with TabPane("⚙ Processes", id="procs"):
            with Horizontal(id="proc-bar"):
                yield Button("Sort: CPU ▼", id="s-cpu", classes="sort-btn")
                yield Button("Sort: RAM", id="s-mem", classes="sort-btn")
                yield Button("Sort: Name", id="s-name", classes="sort-btn")
                yield Button("🗡  Kill", id="kill-btn")
                yield Button("🧹 Drop Cache", id="drop-btn")
                yield Label("", id="proc-status")

            yield DataTable(id="ptable", cursor_type="row")


    # ── mount ─────────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self._layout_dashboard()
        self.query_one("#presets").border_title = " Presets (one-click) "
        self.query_one("#hwbox").border_title = " Hardware Controls "
        self.query_one("#extrabox").border_title = " Battery, Keyboard & Fans "
        self.query_one("#core-box").border_title = " Per-Core CPU Usage "
        self.query_one("#cooling-box").border_title = " Fan curves & service "

        dt = self.query_one("#ptable", DataTable)
        dt.add_columns("PID", "Name", "CPU %", "MEM %", "MEM MB")

        self.query_one("#s-cpu", Button).add_class("-on")

        # Apply persisted settings
        self._sync_ctrl()

        self.set_interval(2, self._tick)
        self.set_interval(3, self._tick_procs)
        self.call_after_refresh(self._tick)
        self._probe_backend(restore_settings=True)

    def _layout_dashboard(self, width: int | None = None) -> None:
        width = self.size.width if width is None else width
        dashboard = self.query_one("#dash-scroll")
        dashboard.set_class(width >= 120, "wide")
        dashboard.set_class(width < 64, "narrow")

    def on_resize(self, event) -> None:
        if self.query("#dash-scroll"):
            self._layout_dashboard(event.size.width)

    def _update_dashboard_context(self) -> None:
        mode = (ec_read("shift_mode") or "unknown").title()
        fan = ec_read("fan_mode") or "unknown"
        boost = " · Boost on" if ec_read("cooler_boost") == "on" else ""
        backend = "Controls connected" if self._fan_backend.status.connected else "Control service offline"
        gpu = self._gpu_name if self._nvml_ok else "GPU telemetry EC-only"
        self.query_one("#dash-context", Static).update(f"{mode} · Fans {fan}{boost} · {gpu} · {backend}")

    def _apply_config(self) -> None:
        cfg = self._config
        changes = {
            MSI_EC / "shift_mode": cfg.performance_mode,
            MSI_EC / "fan_mode": cfg.fan_mode,
        }
        boost = cfg.cooler_boost
        if boost is None and cfg.last_preset in self._PRESETS:
            boost = self._PRESETS[cfg.last_preset][2] == "on"
        if boost is not None:
            changes[MSI_EC / "cooler_boost"] = "on" if boost else "off"
        results = []
        if self._fan_backend.status.connected:
            self._apply_backend_controls(
                {path.name: value for path, value in changes.items()},
                "Saved EC settings restored and verified", preset_id=cfg.last_preset,
            )
        else:
            results.append(apply_verified(changes))
        battery_changes = {}
        for kind, value in (("start", cfg.battery_start_limit), ("end", cfg.battery_limit)):
            attribute = _bat_thresh_path(kind)
            if attribute is not None and value is not None:
                battery_changes[attribute] = str(value)
        if battery_changes:
            results.append(apply_verified(battery_changes))
        if _kbd_path() is not None and cfg.kbd_brightness is not None:
            results.append(write_kbd(cfg.kbd_brightness))
        failures = [result.message for result in results if not result]
        if failures:
            self._status("Settings restore: " + "; ".join(failures))
        self._sync_ctrl()

    def _sync_ctrl(self) -> None:
        shift, fan = ec_read("shift_mode"), ec_read("fan_mode")
        for row_id, current, available_name in (
            ("shift-row", shift, "available_shift_modes"),
            ("fan-row", fan, "available_fan_modes"),
        ):
            row = self.query_one(f"#{row_id}", CtrlRow)
            row.activate(current or "")
            available = ec_read(available_name)
            for _, value in row.options:
                button = row.query_one(f"#{row.cid}-{value}", Button)
                button.disabled = current is None or (available is not None and value not in available.split())
                button.tooltip = "Unavailable for this hardware or driver" if button.disabled else None

        boost, supbat = ec_read("cooler_boost"), ec_read("super_battery")
        webcam, fn_key, win_key = ec_read("webcam"), ec_read("fn_key"), ec_read("win_key")
        self._tog("boost-btn", None if boost is None else boost == "on", "🌀 Cooler Boost ON [c]", "Cooler Boost [c]")
        self._tog("supbat-btn", None if supbat is None else supbat == "on", "🔋 Super Battery ON", "Super Battery")
        self._tog("webcam-btn", None if webcam is None else webcam == "on", "📷 Webcam ON", "📷 Webcam")
        self._tog("fnswap-btn", None if fn_key is None or win_key is None else fn_key == "left", "⌨ Fn↔Win: Left", "⌨ Fn↔Win: Right")

        for selector, current, prefix in (
            (".bl-btn", read_bat_limit(), "bl-"),
            (".bce-btn", read_bat_limit(), "bce-"),
            (".bcs-btn", read_bat_limit("start"), "bcs-"),
            (".kbd-btn", read_kbd(), "kbd-"),
        ):
            for button in self.query(selector):
                value = int(button.id.removeprefix(prefix))
                button.set_class(current is not None and current == value, "-on")
                button.disabled = current is None
                button.tooltip = "Control unavailable or unreadable" if current is None else None

        for preset_id, (mode, fan_mode, cooler, _) in self._PRESETS.items():
            button = self.query_one(f"#{preset_id}", Button)
            button.disabled = any(value is None for value in (shift, fan, boost))
            for name, value in (("available_shift_modes", mode), ("available_fan_modes", fan_mode)):
                available = ec_read(name)
                if available is not None and value not in available.split():
                    button.disabled = True
            button.tooltip = "One or more required controls are unavailable" if button.disabled else None
            button.set_class(
                self._config.last_preset == preset_id and (shift, fan, boost) == (mode, fan_mode, cooler),
                "-on",
            )
        self._sync_backend()

    def _sync_backend(self) -> None:
        self._update_dashboard_context()
        state = self._fan_backend.status
        status = f"Service connected · firmware {state.firmware}" if state.connected else state.reason
        if state.connected and state.reason:
            status += f" · Curves unavailable: {state.reason}"
        if self._backend_busy:
            status = "Applying and verifying hardware settings…"
        elif self._backend_probing:
            status = "Connecting to fan-control service…"
        self.query_one("#backend-status", Static).update(status)
        for button in self.query(".curve-btn"):
            supported = state.curve_read if button.id == "curve-read" else state.curve_write
            if button.id == "curve-reset":
                supported = (state.connected and "auto" in state.fan_modes) or (
                    ec_read("fan_mode") is not None and "auto" in (ec_read("available_fan_modes") or "").split()
                )
            button.disabled = self._backend_busy or not supported
            button.tooltip = state.reason if not supported else None
        self.query_one("#backend-reconnect", Button).disabled = self._backend_busy or self._backend_probing
        if self._backend_busy:
            for button in self.query(".cbtn, .tbtn, #preset-row Button"):
                button.disabled = True

    @work(group="backend-probe")
    async def _probe_backend(self, restore_settings: bool = False) -> None:
        if self._backend_busy or self._backend_probing:
            return
        self._backend_probing = True
        self._sync_backend()
        try:
            await self._fan_backend.probe()
            if restore_settings:
                self._apply_config()
        finally:
            self._backend_probing = False
            self._sync_ctrl()

    @on(Button.Pressed, "#backend-reconnect")
    def on_backend_reconnect(self) -> None:
        self._probe_backend()

    @on(Button.Pressed, "#curve-setup")
    def on_curve_setup(self) -> None:
        help_text = self.query_one("#curve-setup-help", Static)
        help_text.display = not help_text.display
        if help_text.display:
            self.call_after_refresh(help_text.scroll_visible)

    def _tog(self, btn_id: str, active: bool | None, on_lbl: str, off_lbl: str) -> None:
        btn = self.query_one(f"#{btn_id}", Button)
        btn.label = on_lbl if active else off_lbl
        btn.set_class(active is True, "-on")
        btn.disabled = active is None
        btn.tooltip = "Control unavailable or unreadable" if active is None else None

    def _status(self, msg: str, *, hold: bool = True) -> None:
        if hold:
            self._status_until = time.monotonic() + 6
        self.query_one("#status", Static).update(f" {msg}")

    def _save_settings(self, message: str) -> None:
        if not save_config(self._config):
            message += " (applied, but settings could not be saved)"
        self._status(message)

    # ─── presets ───────────────────────────────────────────────────────────────
    _PRESETS: dict[str, tuple[str, str, str, str]] = {
        "p-gaming": ("turbo", "advanced", "on", "🎮 Gaming"),
        "p-ai": ("turbo", "advanced", "on", "🤖 AI Mode"),
        "p-balanced": ("comfort", "auto", "off", "⚖  Balanced"),
        "p-silent": ("eco", "silent", "off", "🌙 Silent"),
    }

    @on(Button.Pressed, "#preset-row Button")
    def on_preset(self, ev: Button.Pressed) -> None:
        preset_id = ev.button.id
        if preset_id not in self._PRESETS:
            return
        shift, fan, boost, label = self._PRESETS[preset_id]
        if self._fan_backend.status.connected:
            self._apply_backend_controls(
                {"shift_mode": shift, "fan_mode": fan, "cooler_boost": boost},
                f"Preset applied and verified: {label}", preset_id=preset_id,
            )
            return
        result = apply_verified({
            MSI_EC / "shift_mode": shift,
            MSI_EC / "fan_mode": fan,
            MSI_EC / "cooler_boost": boost,
        })
        if result:
            self._config.last_preset = preset_id
            self._config.performance_mode = shift
            self._config.fan_mode = fan
            self._config.cooler_boost = boost == "on"
            self._save_settings(f"Preset applied and verified: {label}")
        else:
            self._status(f"Preset failed: {result.message}")
        self._sync_ctrl()

    # ─── battery / keyboard ─────────────────────────────────────────────────
    def _set_battery_threshold(self, pct: int, kind: str) -> None:
        result = write_bat_limit(pct, kind)
        if result:
            # Some firmware couples the start/end thresholds. Save actual values.
            end = read_bat_limit()
            if end is not None:
                self._config.battery_limit = end
            self._config.battery_start_limit = read_bat_limit("start")
            self._save_settings(f"Charge {kind} threshold verified: {pct}%")
        else:
            self._status(result.message)
        self._sync_ctrl()

    @on(Button.Pressed, ".bl-btn")
    def on_bat_limit(self, ev: Button.Pressed) -> None:
        self._set_battery_threshold(int(ev.button.id.removeprefix("bl-")), "end")

    @on(Button.Pressed, ".bcs-btn")
    def on_bat_charge_start(self, ev: Button.Pressed) -> None:
        self._set_battery_threshold(int(ev.button.id.removeprefix("bcs-")), "start")

    @on(Button.Pressed, ".bce-btn")
    def on_bat_charge_end(self, ev: Button.Pressed) -> None:
        self._set_battery_threshold(int(ev.button.id.removeprefix("bce-")), "end")

    @on(Button.Pressed, ".kbd-btn")
    def on_kbd(self, ev: Button.Pressed) -> None:
        level = int(ev.button.id.removeprefix("kbd-"))
        result = write_kbd(level)
        if result:
            self._config.kbd_brightness = level
            self._save_settings(f"Keyboard brightness verified: {level}")
        else:
            self._status(result.message)
        self._sync_ctrl()

    # ─── toggles ──────────────────────────────────────────────────────────────
    def _toggle_ec(self, attribute: str) -> None:
        current = ec_read(attribute)
        if current not in ("on", "off"):
            self._status(f"{attribute}: control unavailable or unreadable")
            return
        self._write_ec(attribute, "off" if current == "on" else "on")

    @on(Button.Pressed, ".tbtn")
    def on_tbtn(self, ev: Button.Pressed) -> None:
        attribute = {
            "boost-btn": "cooler_boost",
            "supbat-btn": "super_battery",
            "webcam-btn": "webcam",
        }.get(ev.button.id)
        if attribute:
            self._toggle_ec(attribute)
        elif ev.button.id == "fnswap-btn":
            current = ec_read("fn_key")
            if current not in ("left", "right"):
                self._status("Fn/Win swap: control unavailable or unreadable")
                return
            new = "left" if current == "right" else "right"
            if self._fan_backend.status.connected:
                self._apply_backend_controls(
                    {"fn_key": new, "win_key": "right" if new == "left" else "left"},
                    f"Fn/Win swap verified: {new}",
                )
                return
            result = apply_verified({
                MSI_EC / "fn_key": new,
                MSI_EC / "win_key": "right" if new == "left" else "left",
            })
            self._status(f"Fn/Win swap verified: {new}" if result else result.message)
            self._sync_ctrl()

    @on(Button.Pressed, ".curve-btn")
    def on_curve(self, ev: Button.Pressed) -> None:
        if ev.button.id == "curve-reset":
            if self._fan_backend.status.connected:
                self._apply_backend_controls({"fan_mode": "auto"}, "Firmware automatic fan control restored")
            else:
                self._write_ec("fan_mode", "auto")
        else:
            self._run_curve_action(ev.button.id)

    @work(group="backend-controls")
    async def _run_curve_action(self, action: str) -> None:
        if self._backend_busy:
            return
        self._backend_busy = True
        self._sync_ctrl()
        try:
            if action == "curve-read":
                points = await self._fan_backend.read_curve()
                self._status("Fan curve read from hardware")
            else:
                preset = {"curve-perf": "performance", "curve-silent": "silent"}[action]
                points = await self._fan_backend.set_preset(preset)
                self._config.fan_curves["system"] = FanCurve(points=points)
                self._config.fan_mode = "advanced"
                self._config.last_preset = ""
                self._save_settings(f"{preset.title()} curve applied and verified")
            self.query_one("#curve-points", Static).update(
                "Hardware curve: " + "  ·  ".join(f"{temp}°C → {fan}%" for temp, fan in points)
            )
        except BackendError as exc:
            self.query_one("#curve-points", Static).update("Curve unavailable; refresh to read the current hardware state")
            self._status(f"Fan curve: {exc}")
            await self._fan_backend.probe()
        finally:
            self._backend_busy = False
            self._sync_ctrl()

    @work(group="backend-controls")
    async def _apply_backend_controls(self, changes: dict[str, str], message: str, preset_id: str = "") -> None:
        if self._backend_busy:
            return
        self._backend_busy = True
        self._sync_ctrl()
        try:
            await self._fan_backend.apply_controls(changes)
            for attribute, value in changes.items():
                setting = {"shift_mode": "performance_mode", "fan_mode": "fan_mode", "cooler_boost": "cooler_boost"}.get(attribute)
                if setting:
                    setattr(self._config, setting, value == "on" if setting == "cooler_boost" else value)
            self._config.last_preset = preset_id
            self._save_settings(message)
        except BackendError as exc:
            self._status(f"Control failed: {exc}")
            await self._fan_backend.probe()
        finally:
            self._backend_busy = False
            self._sync_ctrl()

    # ─── processes ────────────────────────────────────────────────────────────
    @on(Button.Pressed, ".sort-btn")
    def on_sort(self, ev: Button.Pressed) -> None:
        sid = ev.button.id
        if sid == "s-cpu":
            self._sort = "cpu"
        elif sid == "s-mem":
            self._sort = "mem"
        elif sid == "s-name":
            self._sort = "name"
        for b in self.query(".sort-btn"):
            b.set_class(b.id == sid, "-on")
        self._tick_procs()

    @on(Button.Pressed, "#kill-btn")
    def on_kill(self) -> None:
        dt = self.query_one("#ptable", DataTable)
        if dt.cursor_row is not None and self._pids:
            pid = self._pids[dt.cursor_row]
            try:
                os.kill(pid, signal.SIGTERM)
                self._status(f"SIGTERM → PID {pid}")
            except Exception as e:
                self._status(f"Kill failed: {e}")
        else:
            self._status("No process selected")

    @on(Button.Pressed, "#drop-btn")
    def on_drop(self) -> None:
        try:
            subprocess.run(["sync"], check=False)
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3")
            self._status("🧹 Page cache cleared")
        except Exception as e:
            self._status(f"Failed: {e}")

    # ─── ticks ────────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        if not self._nvml_ok and time.monotonic() >= self._nvml_retry_at:
            self._connect_nvml()
            self._telemetry.nvml_available = self._nvml_ok
            self._telemetry.nvml_reason = self._nvml_reason
        sample = self._telemetry.sample()
        values = sample.values
        for device in ("cpu", "gpu"):
            clock = values.get("cpu_frequency" if device == "cpu" else "gpu_clock")
            detail = (
                f"{reading(values.get(device + '_temp'), '°C')} · "
                f"fan {reading(values.get(device + '_fan'), '%')} · "
                f"{reading(None if clock is None else clock / 1000, 'GHz', decimals=1)}"
            )
            card = self.query_one(f"#overview-{device}", OverviewCard)
            card.update_reading(
                values.get(device + "_load"), "N/A" if values.get(device + "_load") is None else f"{reading(values[device + '_load'], '%')} busy", detail,
            )
            if device == "gpu":
                card.tooltip = self._gpu_name if self._nvml_ok else self._nvml_reason
        self.query_one("#overview-memory", OverviewCard).update_reading(
            values.get("ram"), f"{reading(values.get('ram'), '%')} RAM used",
            f"GPU memory {reading(values.get('vram'), '%')}",
        )
        battery_source = "AC connected" if sample.battery_charging else "On battery"
        if values.get("battery") is None:
            battery_source = "Battery unavailable"
        self.query_one("#overview-battery", OverviewCard).update_reading(
            values.get("battery"), reading(values.get("battery"), "%"),
            f"{battery_source} · limit {reading(read_bat_limit(), '%')}",
        )
        self.query_one("#dash-cooling", Static).update(
            f"POWER  CPU {reading(values.get('cpu_power'), ' W', decimals=1)} · "
            f"GPU {reading(values.get('gpu_power'), ' W', decimals=1)}"
        )
        self.query_one("#dash-activity", Static).update(
            f"NET  ↑ {reading(values.get('net_up'), '', decimals=2)}  ↓ {reading(values.get('net_down'), ' MB/s', decimals=2)}"
            f"    DISK  R {reading(values.get('disk_read'), '', decimals=2)}  W {reading(values.get('disk_write'), ' MB/s', decimals=2)}"
        )
        self._update_dashboard_context()
        cards = {
            "sc-ct": "cpu_temp", "sc-gt": "gpu_temp",
            "sc-cp": "cpu_power", "sc-gp": "gpu_power",
            "sc-cf": "cpu_fan", "sc-gf": "gpu_fan",
            "sc-ram": "ram", "sc-vram": "vram", "sc-bat": "battery",
            "sc-cu": "cpu_load", "sc-gu": "gpu_load", "sc-freq": "cpu_frequency",
            "sc-netu": "net_up", "sc-netd": "net_down",
            "sc-diskr": "disk_read", "sc-diskw": "disk_write",
            "sc-volt": "cpu_voltage", "sc-gvolt": "gpu_voltage",
            "sc-cclk": "cpu_clock", "sc-gclk": "gpu_clock",
        }
        for card_id, metric in cards.items():
            self._spark_cards[card_id].update(
                values[metric], sample.unavailable.get(metric, "No current reading from this sensor")
            )

        for core in self.query(CoreBar):
            value = sample.per_core[core.core] if core.core < len(sample.per_core) else None
            core.update(value)

        parts = []
        for metric, label, unit in (
            ("cpu_temp", "CPU", "°C"), ("gpu_temp", "GPU", "°C"),
            ("cpu_fan", "CPU Fan", "%"), ("gpu_fan", "GPU Fan", "%"),
            ("net_up", "Net ↑", "MB/s"), ("net_down", "↓", "MB/s"),
            ("battery", "Bat", "%"), ("ram", "RAM", "%"),
        ):
            value = values[metric]
            if value is not None:
                parts.append(f"{label} {value:.1f}{unit}")

        alerts = []
        cfg = self._config.alerts
        for metric, label, warning, critical in (
            ("cpu_temp", "CPU", cfg.cpu_warn, cfg.cpu_crit),
            ("gpu_temp", "GPU", cfg.gpu_warn, cfg.gpu_crit),
        ):
            value = values[metric]
            if value is not None and value >= critical:
                alerts.append(f"🔥 {label} {value:.0f}°C")
            elif value is not None and value >= warning:
                alerts.append(f"⚠ {label} {value:.0f}°C")
        if (
            cfg.fan_stall_enabled and values["cpu_fan"] == 0
            and values["cpu_temp"] is not None and values["cpu_temp"] > 60
        ):
            alerts.append("🛑 CPU fan stalled!")
        if alerts:
            self._status(" | ".join(alerts), hold=False)
        elif time.monotonic() >= self._status_until:
            self._status(" | ".join(parts) or "Waiting for sensor readings", hold=False)

    def _tick_procs(self) -> None:
        dt = self.query_one("#ptable", DataTable)
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]):
            try:
                info = p.info
                mem_mb = info["memory_info"].rss / (1024**2) if info["memory_info"] else 0
                procs.append((info["pid"], info["name"] or "?", info["cpu_percent"] or 0, info["memory_percent"] or 0, mem_mb))
            except Exception:
                pass

        if self._sort == "cpu":
            procs.sort(key=lambda x: x[2], reverse=True)
        elif self._sort == "mem":
            procs.sort(key=lambda x: x[3], reverse=True)
        else:
            procs.sort(key=lambda x: (x[1] or "").lower())

        self._pids = [p[0] for p in procs]
        dt.clear()
        for pid, name, cpu, mem, mem_mb in procs[:100]:
            dt.add_row(str(pid), name[:30], f"{cpu:.1f}", f"{mem:.1f}", f"{mem_mb:.0f}")

    # ─── key actions ───────────────────────────────────────────────────────────
    def action_toggle_details(self) -> None:
        self.action_show_tab("dash")
        details = self.query_one("#dash-details", Collapsible)
        details.collapsed = not details.collapsed
        if not details.collapsed:
            self.call_after_refresh(details.scroll_visible)

    def action_navigate(self, action: str) -> None:
        tab = self.query_one("#tabs", TabbedContent).active
        selector = {"dash": "#dash-scroll", "ctrl": "#ctrl-scroll", "procs": "#ptable"}[tab]
        target = self.query_one(selector)
        if isinstance(target, DataTable):
            action = {"scroll_up": "cursor_up", "scroll_down": "cursor_down"}.get(action, action)
        getattr(target, f"action_{action}")()

    def action_refresh_now(self) -> None:
        self._tick()
        self._sync_ctrl()
        self._status("Refreshed")
        self._probe_backend()

    def action_boost(self) -> None:
        self._toggle_cooler_boost()

    def _toggle_cooler_boost(self) -> None:
        self._toggle_ec("cooler_boost")

    def action_show_tab(self, tab: str) -> None:
        # Release focus before hiding a pane so its buttons cannot reactivate it.
        self.set_focus(None)
        self.query_one("#tabs", TabbedContent).active = tab
        target = {"dash": "#dash-scroll", "ctrl": "#ctrl-scroll", "procs": "#ptable"}[tab]
        self.call_after_refresh(self.query_one(target).focus)

    def _write_ec(self, rel: str, val: str) -> bool:
        if self._backend_busy:
            self._status("Wait for the current hardware operation to finish")
            return False
        if self._fan_backend.status.connected:
            self._apply_backend_controls({rel: val}, f"{rel} verified: {val}")
            return False  # Completion is reported by the worker after verification.
        result = ec_write(rel, val)
        self._sync_ctrl()
        if not result:
            self._status(result.message)
            return False
        setting = {"shift_mode": "performance_mode", "fan_mode": "fan_mode", "cooler_boost": "cooler_boost"}.get(rel)
        if setting:
            setattr(self._config, setting, val == "on" if setting == "cooler_boost" else val)
            self._config.last_preset = ""
            self._save_settings(f"{rel} verified: {val}")
            self._sync_ctrl()
        else:
            self._status(f"{rel} verified: {val}")
        return True

    def on_unmount(self) -> None:
        if self._nvml_ok:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError:
                pass


if __name__ == "__main__":
    import sys
    if "--reset-config" in sys.argv:
        from config import reset_config
        if reset_config():
            print("Config reset to defaults")
        else:
            print("Failed to reset config")
            sys.exit(1)
        sys.exit(0)
    GiveLaptopAC().run()
