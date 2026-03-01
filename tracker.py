"""
Zerodha Terminal P&L Tracker
Real-time positions and profit/loss display using WebSocket (KiteTicker).
"""

import os
import sys
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
from kiteconnect import KiteConnect, KiteTicker
from rich.console import Console, Group
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")

console = Console()

# ---------------------------------------------------------------------------
# Shared state (protected by _lock)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_positions: list[dict] = []      # position dicts; last_price updated by WS
_last_tick_time: str = "waiting..."
_ws_status: str = "Connecting..."


# ---------------------------------------------------------------------------
# Kite client
# ---------------------------------------------------------------------------
def get_kite_client() -> KiteConnect:
    if not API_KEY or not ACCESS_TOKEN:
        console.print(
            "[bold red]Error:[/] Missing KITE_API_KEY or KITE_ACCESS_TOKEN in .env file.\n"
            "See [bold].env.example[/] for setup instructions."
        )
        sys.exit(1)
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    return kite


# ---------------------------------------------------------------------------
# P&L helpers
# ---------------------------------------------------------------------------
def color_pnl(value: float) -> Text:
    formatted = f"₹{value:,.2f}"
    if value > 0:
        return Text(formatted, style="bold green")
    elif value < 0:
        return Text(formatted, style="bold red")
    return Text(formatted, style="dim")


def pnl_arrow(value: float) -> str:
    if value > 0:
        return "▲"
    elif value < 0:
        return "▼"
    return "─"


def calc_pnl(pos: dict) -> tuple[float, float]:
    """Return (day_pnl, overall_pnl) from current LTP."""
    qty = pos.get("quantity", 0)
    avg = pos.get("average_price", 0.0)
    ltp = pos.get("last_price", 0.0)
    # close_price is yesterday's close for CF/NRML; fall back to avg for MIS
    close = pos.get("close_price") or avg
    product = pos.get("product", "")

    overall_pnl = (ltp - avg) * qty
    day_pnl = overall_pnl if product == "MIS" else (ltp - close) * qty
    return day_pnl, overall_pnl


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------
def build_positions_table(positions: list[dict]):
    table = Table(
        title="[bold cyan]Open Positions[/]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold white on dark_blue",
        show_footer=True,
        expand=True,
    )
    table.add_column("Symbol", style="bold white", min_width=14)
    table.add_column("Product", justify="center", min_width=7)
    table.add_column("Qty", justify="right", min_width=6)
    table.add_column("Avg Price", justify="right", min_width=10)
    table.add_column("LTP", justify="right", min_width=10)
    table.add_column("Day P&L", justify="right", min_width=14)
    table.add_column("Overall P&L", justify="right", min_width=14)

    total_day = 0.0
    total_overall = 0.0

    for pos in positions:
        qty = pos.get("quantity", 0)
        if qty == 0:
            continue
        day_pnl, overall_pnl = calc_pnl(pos)
        total_day += day_pnl
        total_overall += overall_pnl

        qty_str = Text(f"{qty:+d}", style="green" if qty > 0 else "red")
        table.add_row(
            pos.get("tradingsymbol", ""),
            pos.get("product", ""),
            qty_str,
            f"₹{pos.get('average_price', 0.0):,.2f}",
            f"₹{pos.get('last_price', 0.0):,.2f}",
            color_pnl(day_pnl),
            color_pnl(overall_pnl),
        )

    table.columns[5].footer = color_pnl(total_day)
    table.columns[6].footer = color_pnl(total_overall)
    return table, total_day, total_overall


def build_summary_panel(
    total_day: float, total_overall: float, open_count: int, updated: str, ws_status: str
) -> Panel:
    day_color = "green" if total_day >= 0 else "red"
    overall_color = "green" if total_overall >= 0 else "red"
    summary = (
        f"[bold]Open Positions:[/] {open_count}    "
        f"[bold]Day P&L:[/] [{day_color}]{pnl_arrow(total_day)} ₹{total_day:,.2f}[/]    "
        f"[bold]Overall P&L:[/] [{overall_color}]{pnl_arrow(total_overall)} ₹{total_overall:,.2f}[/]    "
        f"[dim]Tick: {updated}   WS: {ws_status}[/]"
    )
    return Panel(summary, title="[bold yellow]Summary[/]", border_style="yellow")


def render():
    with _lock:
        positions = [dict(p) for p in _positions]   # snapshot (shallow-copy each dict)
        updated = _last_tick_time
        ws_status = _ws_status

    open_positions = [p for p in positions if p.get("quantity", 0) != 0]

    if not open_positions:
        no_pos = Panel(
            "[dim]No open positions found.[/]",
            title="[bold cyan]Open Positions[/]",
            border_style="cyan",
        )
        return Columns([no_pos, build_summary_panel(0, 0, 0, updated, ws_status)], expand=True)

    table, total_day, total_overall = build_positions_table(open_positions)
    summary = build_summary_panel(total_day, total_overall, len(open_positions), updated, ws_status)
    return Group(table, summary)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
def start_websocket(instrument_tokens: list[int]) -> KiteTicker:
    ticker = KiteTicker(API_KEY, ACCESS_TOKEN)

    def on_connect(ws, _response):
        global _ws_status
        ws.subscribe(instrument_tokens)
        ws.set_mode(ws.MODE_LTP, instrument_tokens)
        with _lock:
            _ws_status = "Live"

    def on_ticks(ws, ticks):
        global _last_tick_time
        token_map = {tick["instrument_token"]: tick.get("last_price") for tick in ticks}
        with _lock:
            for pos in _positions:
                ltp = token_map.get(pos.get("instrument_token"))
                if ltp is not None:
                    pos["last_price"] = ltp
            _last_tick_time = datetime.now().strftime("%H:%M:%S")

    def on_close(ws, code, reason):
        global _ws_status
        with _lock:
            _ws_status = f"Closed ({code})"

    def on_error(ws, code, reason):
        global _ws_status
        with _lock:
            _ws_status = f"Error ({reason})"

    ticker.on_connect = on_connect
    ticker.on_ticks = on_ticks
    ticker.on_close = on_close
    ticker.on_error = on_error

    ticker.connect(threaded=True)   # non-blocking; runs WS in its own thread
    return ticker


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    console.rule("[bold cyan]Zerodha Terminal P&L Tracker[/]")
    kite = get_kite_client()

    try:
        profile = kite.profile()
        console.print(
            f"[green]Connected[/] as [bold]{profile['user_name']}[/] "
            f"([dim]{profile['email']}[/])\n"
        )
    except Exception as e:
        console.print(f"[bold red]Authentication failed:[/] {e}")
        sys.exit(1)

    # Fetch positions, retrying until at least one open position appears.
    tokens = []
    while not tokens:
        try:
            all_positions = kite.positions()
            positions = all_positions.get("net", [])
        except Exception as e:
            console.print(f"[bold red]Failed to fetch positions:[/] {e}")
            sys.exit(1)

        open_positions = [p for p in positions if p.get("quantity", 0) != 0]
        tokens = [p["instrument_token"] for p in open_positions if "instrument_token" in p]

        if not tokens:
            console.print("[dim]No open positions yet — retrying in 5s...[/]", end="\r")
            time.sleep(5)

    console.print(" " * 50, end="\r")  # clear the retry line
    with _lock:
        _positions.extend(positions)

    console.print(
        f"[dim]Tracking {len(tokens)} instrument(s) via WebSocket. Press Ctrl+C to quit.[/]\n"
    )

    ticker = start_websocket(tokens)

    try:
        with Live(render(), refresh_per_second=4, screen=False) as live:
            while True:
                time.sleep(0.25)
                live.update(render())
    finally:
        ticker.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Tracker stopped.[/]")
