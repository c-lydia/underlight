"""Compact overview cards; detailed sensor charts live below the overview."""

from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Container
from textual.widgets import Label, Sparkline, Static

from telemetry import number


def reading(value, unit: str = "", *, decimals: int = 0) -> str:
    value = number(value)
    return "N/A" if value is None else f"{value:.{decimals}f}{unit}"


class OverviewCard(Container):
    def __init__(self, title: str, color: str, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.color = Color.parse(color)
        self.history: list[float] = []

    def compose(self) -> ComposeResult:
        title = Label(self.title, classes="overview-title")
        title.styles.color = self.color
        yield title
        value = Static("N/A", classes="overview-value", markup=False)
        value.styles.color = self.color
        yield value
        yield Static("Waiting for readings", classes="overview-detail", markup=False)
        yield Sparkline([], min_color=self.color.with_alpha(0.3), max_color=self.color)

    def update_reading(self, value, headline: str, detail: str) -> None:
        self.query_one(".overview-value", Static).update(headline)
        self.query_one(".overview-detail", Static).update(detail)
        value = number(value)
        self.history = [] if value is None else (self.history + [value])[-60:]
        chart = self.query_one(Sparkline)
        chart.data = self.history.copy()
        chart.display = value is not None
