"""Demo mode — shows sample output without any API calls."""

import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.console import Group

console = Console()

SAMPLE_POSITIONS = [
    {"tradingsymbol": "RELIANCE",   "product": "CNC",  "quantity":  10, "average_price": 2850.50, "last_price": 2934.75, "day_m2m":  420.00,  "pnl":  842.50},
    {"tradingsymbol": "INFY",       "product": "CNC",  "quantity":  25, "average_price": 1710.00, "last_price": 1683.40, "day_m2m": -320.00,  "pnl": -665.00},
    {"tradingsymbol": "NIFTY24DEC24000CE", "product": "NRML", "quantity": 50, "average_price": 185.00, "last_price": 223.60, "day_m2m": 1180.00, "pnl": 1930.00},
    {"tradingsymbol": "HDFCBANK",   "product": "MIS",  "quantity": -15, "average_price": 1645.25, "last_price": 1629.80, "day_m2m":  231.75,  "pnl":  231.75},
    {"tradingsymbol": "TATAMOTORS", "product": "CNC",  "quantity":  30, "average_price":  965.00, "last_price":  951.20, "day_m2m": -195.00,  "pnl": -414.00},
]


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


def render(tick: int):
    # Slightly wiggle LTP each tick to simulate live prices
    import math
    positions = []
    for i, p in enumerate(SAMPLE_POSITIONS):
        wobble = math.sin(tick * 0.4 + i) * p["last_price"] * 0.001
        ltp = round(p["last_price"] + wobble, 2)
        qty = p["quantity"]
        day_m2m = round(p["day_m2m"] + wobble * abs(qty), 2)
        pnl = round(p["pnl"] + wobble * abs(qty), 2)
        positions.append({**p, "last_price": ltp, "day_m2m": day_m2m, "pnl": pnl})

    table = Table(
        title="[bold cyan]Open Positions[/]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold white on dark_blue",
        show_footer=True,
        expand=True,
    )
    table.add_column("Symbol",      style="bold white", min_width=20)
    table.add_column("Product",     justify="center",   min_width=7)
    table.add_column("Qty",         justify="right",    min_width=6)
    table.add_column("Avg Price",   justify="right",    min_width=10)
    table.add_column("LTP",         justify="right",    min_width=10)
    table.add_column("Day P&L",     justify="right",    min_width=14)
    table.add_column("Overall P&L", justify="right",    min_width=14, footer_style="bold")

    total_day = 0.0
    total_overall = 0.0

    for pos in positions:
        qty = pos["quantity"]
        qty_color = "green" if qty > 0 else "red"
        table.add_row(
            pos["tradingsymbol"],
            pos["product"],
            Text(f"{qty:+d}", style=qty_color),
            f"₹{pos['average_price']:,.2f}",
            f"₹{pos['last_price']:,.2f}",
            color_pnl(pos["day_m2m"]),
            color_pnl(pos["pnl"]),
        )
        total_day += pos["day_m2m"]
        total_overall += pos["pnl"]

    table.columns[5].footer = color_pnl(total_day)
    table.columns[6].footer = color_pnl(total_overall)

    now = datetime.now().strftime("%H:%M:%S")
    day_color = "green" if total_day >= 0 else "red"
    overall_color = "green" if total_overall >= 0 else "red"

    summary = Panel(
        f"[bold]Open Positions:[/] {len(positions)}    "
        f"[bold]Day P&L:[/] [{day_color}]{pnl_arrow(total_day)} ₹{total_day:,.2f}[/]    "
        f"[bold]Overall P&L:[/] [{overall_color}]{pnl_arrow(total_overall)} ₹{total_overall:,.2f}[/]    "
        f"[dim]Updated: {now}   [DEMO MODE][/]",
        title="[bold yellow]Summary[/]",
        border_style="yellow",
    )

    return Group(table, summary)


def main():
    console.rule("[bold cyan]Zerodha Terminal P&L Tracker — DEMO[/]")
    console.print("[dim]Simulating live price movement. Press Ctrl+C to quit.[/]\n")

    with Live(render(0), refresh_per_second=4, screen=False) as live:
        tick = 0
        while True:
            time.sleep(0.5)
            tick += 1
            live.update(render(tick))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Demo stopped.[/]")
