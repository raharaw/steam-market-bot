#!/usr/bin/env python3
"""
Steam Market Bot — TUI Edition
List Dota 2 (and other) items on Steam Community Market with smart pricing.

Usage:
  python bot.py              # Interactive TUI
  python bot.py --headless   # Skip Playwright (no buy order scraping)
"""

import json, os, sys, time, re, argparse
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich import box

console = Console()

# ─── Constants ───────────────────────────────────────────────────────────────

STEAM_COMMUNITY = "https://steamcommunity.com"
STEAM_API = "https://api.steampowered.com"
CONFIG_FILE = Path(__file__).parent / "config.json"
COOKIES_FILE = Path(__file__).parent / "cookies.json"
DELAY_BETWEEN_ITEMS = 10
HEADLESS_MODE = False  # Set by --headless flag

# Currency codes → (name, symbol, fee_type, fee_value)
CURRENCIES = {
    1:  ("USD",     "$",   "percent", 0.15),
    2:  ("GBP",     "£",   "percent", 0.15),
    3:  ("EUR",     "€",   "percent", 0.15),
    5:  ("RUB",     "₽",   "percent", 0.15),
    23: ("IDR",     "Rp",  "flat",    360),
    25: ("MYR",     "RM",  "percent", 0.15),
    26: ("PHP",     "₱",   "percent", 0.15),
    27: ("SGD",     "S$",  "percent", 0.15),
    28: ("THB",     "฿",   "percent", 0.15),
    29: ("VND",     "₫",   "percent", 0.15),
    37: ("TRY",     "₺",   "percent", 0.15),
    38: ("UAH",     "₴",   "percent", 0.15),
}

DEFAULT_CONFIG = {
    "steam_id": "",
    "steam_login_secure": "",
    "api_key": "",
    "currency": 23,
    "apps": [
        {"app_id": 570, "name": "Dota 2", "context_id": 2},
        {"app_id": 753, "name": "Steam", "context_id": 6},
    ],
}


# ─── Config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        cfg.update(saved)
    # Backward compat: load from cookies.json
    if not cfg.get("steam_login_secure") and COOKIES_FILE.exists():
        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        if "steamLoginSecure" in cookies:
            cfg["steam_login_secure"] = cookies["steamLoginSecure"]
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    console.print(f"[dim]Config saved → {CONFIG_FILE}[/dim]")


# ─── Price Helpers ───────────────────────────────────────────────────────────

def get_fee_info(currency_code: int) -> tuple[str, str, str, float]:
    """Returns (name, symbol, fee_type, fee_value)."""
    return CURRENCIES.get(currency_code, ("Unknown", "?", "percent", 0.15))


def calc_listing_price(buyer_pays: int, currency_code: int) -> int:
    """Calculate price to send to sellitem endpoint (in sen/cents).

    Given the desired buyer_pays amount:
      IDR (flat):  seller = buyer_pays - 360,  send = seller × 100
      Others (%):  seller = buyer_pays × 0.85, send = seller × 100
    """
    _, _, fee_type, fee_value = get_fee_info(currency_code)
    if fee_type == "flat":
        seller = max(1, buyer_pays - int(fee_value))
    else:
        seller = max(1, int(buyer_pays * (1 - fee_value)))
    return seller * 100


def calc_buyer_pays(seller_receives: int, currency_code: int) -> int:
    """Calculate what buyer pays given seller receives amount."""
    _, _, fee_type, fee_value = get_fee_info(currency_code)
    if fee_type == "flat":
        return seller_receives + int(fee_value)
    return int(seller_receives / (1 - fee_value))


def fmt_idr(amount: int) -> str:
    """Format IDR amount."""
    return f"Rp {amount:,}"


def fmt_price(amount: int, currency_code: int) -> str:
    """Format price with currency symbol."""
    name, symbol, _, _ = get_fee_info(currency_code)
    if currency_code == 1:  # USD cents
        return f"${amount/100:.2f}"
    return f"{symbol} {amount:,}"


def fee_display(currency_code: int) -> str:
    """Human-readable fee string."""
    _, symbol, fee_type, fee_val = get_fee_info(currency_code)
    if fee_type == "flat":
        return f"{symbol} {int(fee_val)} flat"
    return f"{int(fee_val * 100)}%"


# ─── Steam Client ───────────────────────────────────────────────────────────

class SteamClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Referer": f"{STEAM_COMMUNITY}/profiles/{cfg['steam_id']}/inventory",
        })
        # Load cookies
        if COOKIES_FILE.exists():
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            for name, value in cookies.items():
                self.session.cookies.set(name, value, domain="steamcommunity.com")
        elif cfg.get("steam_login_secure"):
            self.session.cookies.set("steamLoginSecure", cfg["steam_login_secure"], domain="steamcommunity.com")

    # ── Validation ──

    def validate_session(self) -> tuple[bool, str]:
        """Check if session is valid. Returns (ok, username_or_error)."""
        try:
            r = self.session.get(f"{STEAM_COMMUNITY}/my/", allow_redirects=False, timeout=10)
            if r.status_code == 302 and "login" in r.headers.get("Location", "").lower():
                return False, "Session expired — update steamLoginSecure"
            match = re.search(r'<title>Steam Community :: (.+?)</title>', r.text)
            return True, match.group(1) if match else "Unknown"
        except Exception as e:
            return False, str(e)

    # ── VAC Bans ──

    def get_vac_bans(self) -> dict | None:
        """Check VAC ban status. Returns None if no API key."""
        if not self.cfg.get("api_key"):
            return None
        try:
            r = self.session.get(
                f"{STEAM_API}/ISteamUser/GetPlayerBans/v1/",
                params={"steamids": self.cfg["steam_id"]},
                timeout=10,
            )
            players = r.json().get("players", [])
            return players[0] if players else None
        except Exception:
            return None

    # ── Inventory ──

    def get_inventory(self, app_id: int, context_id: int) -> list[dict]:
        """Fetch inventory items for an app."""
        self.session.get(f"{STEAM_COMMUNITY}/my/", timeout=10)
        time.sleep(2)

        url = f"{STEAM_COMMUNITY}/inventory/{self.cfg['steam_id']}/{app_id}/{context_id}"
        items_out = []
        seen = set()
        start_assetid = None

        while True:
            params = {"l": "english"}
            if start_assetid:
                params["start_assetid"] = start_assetid

            r = self.session.get(url, params=params, timeout=30)
            if r.status_code != 200:
                break

            data = r.json()
            if not data or not data.get("success"):
                break

            # Build description lookup
            descs = {}
            for d in data.get("descriptions", []):
                key = f"{d['classid']}_{d.get('instanceid', '0')}"
                descs[key] = d

            for asset in data.get("assets", []):
                aid = asset["assetid"]
                if aid in seen:
                    continue

                key = f"{asset['classid']}_{asset.get('instanceid', '0')}"
                desc = descs.get(key, {})

                if not desc.get("marketable") or not desc.get("tradable"):
                    continue

                seen.add(aid)
                items_out.append({
                    "assetid": aid,
                    "classid": asset["classid"],
                    "instanceid": asset.get("instanceid", "0"),
                    "app_id": int(asset.get("appid", app_id)),
                    "context_id": int(asset.get("contextid", context_id)),
                    "name": desc.get("name", "Unknown"),
                    "mhn": desc.get("market_hash_name", desc.get("name", "Unknown")),
                    "type": desc.get("type", ""),
                    "icon": desc.get("icon_url", ""),
                })

            if not data.get("more_items"):
                break
            start_assetid = data.get("last_assetid")
            time.sleep(1)

        return items_out

    def get_all_inventory(self) -> list[dict]:
        """Fetch inventory for all configured apps."""
        all_items = []
        for i, app in enumerate(self.cfg.get("apps", [])):
            if i > 0:
                time.sleep(5)
            items = self.get_inventory(app["app_id"], app["context_id"])
            all_items.extend(items)
            console.print(f"  [cyan]{app['name']}[/cyan]: {len(items)} marketable")
        return all_items

    # ── Pricing ──

    def get_price_overview(self, market_hash_name: str, app_id: int = 570) -> dict | None:
        """Get price overview from Steam API."""
        try:
            r = self.session.get(
                f"{STEAM_COMMUNITY}/market/priceoverview/",
                params={
                    "appid": app_id,
                    "market_hash_name": market_hash_name,
                    "currency": self.cfg.get("currency", 1),
                },
                timeout=10,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data.get("success"):
                return None
            return {
                "lowest": data.get("lowest_price", ""),
                "median": data.get("median_price", ""),
                "volume": data.get("volume", "0"),
            }
        except Exception:
            return None

    def scrape_buy_order(self, market_hash_name: str, app_id: int = 570) -> tuple[int | None, int | None]:
        """Scrape buy order from market page via Playwright.
        Returns (highest_buy_order_idr, lowest_sell_idr) or (None, None).
        Returns (None, None) immediately if --headless mode.
        """
        if HEADLESS_MODE:
            return None, None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None, None

        encoded = requests.utils.quote(market_hash_name)
        url = f"{STEAM_COMMUNITY}/market/listings/{app_id}/{encoded}"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
                )
                if COOKIES_FILE.exists():
                    with open(COOKIES_FILE) as f:
                        cookies_data = json.load(f)
                    ctx.add_cookies([{
                        "name": "steamLoginSecure",
                        "value": cookies_data.get("steamLoginSecure", ""),
                        "domain": "steamcommunity.com",
                        "path": "/",
                    }])
                page = ctx.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)
                content = page.content()
                browser.close()

            buy_idr = None
            sell_idr = None

            # "X requests to buy at Rp Y or lower"
            buy_match = re.search(
                r'(\d[\d.,]*)\s+requests?\s+to\s+buy\s+at\s+Rp\s*([\d.,]+)',
                content, re.IGNORECASE
            )
            if buy_match:
                buy_idr = int(buy_match.group(2).replace(".", "").replace(",", ""))

            # "Starting at: Rp X"
            sell_match = re.search(
                r'Starting\s+at:\s+Rp\s*([\d.,]+)',
                content, re.IGNORECASE
            )
            if sell_match:
                sell_idr = int(sell_match.group(1).replace(".", "").replace(",", ""))

            return buy_idr, sell_idr
        except Exception:
            return None, None

    # ── Listing ──

    def sell_item(self, item: dict, price_sen: int) -> tuple[bool, str]:
        """List an item on the market. price_sen = price in sen/cents."""
        url = f"{STEAM_COMMUNITY}/market/sellitem/"
        data = {
            "appid": str(item["app_id"]),
            "contextid": str(item["context_id"]),
            "assetid": str(item["assetid"]),
            "amount": "1",
            "price": str(price_sen),
        }
        r = self.session.post(url, data=data, timeout=15)
        try:
            res = r.json()
        except Exception:
            return False, f"HTTP {r.status_code}"
        if res.get("success") == 1:
            return True, "OK"
        return False, res.get("message", str(res))

    # ── Helpers ──

    def get_app_name(self, app_id: int) -> str:
        """Get app name from config."""
        return next(
            (a["name"] for a in self.cfg.get("apps", []) if a["app_id"] == app_id),
            f"App {app_id}"
        )


# ─── TUI Screens ─────────────────────────────────────────────────────────────

def show_banner():
    console.print()
    console.print(Panel(
        "[bold cyan]╔═══════════════════════════════════════════╗[/bold cyan]\n"
        "[bold cyan]║       🎮  Steam Market Bot  🎮            ║[/bold cyan]\n"
        "[bold cyan]║       TUI Edition — v2.0                  ║[/bold cyan]\n"
        "[bold cyan]╚═══════════════════════════════════════════╝[/bold cyan]",
        border_style="cyan",
    ))
    console.print()


def setup_wizard(cfg: dict) -> dict:
    """Interactive first-run setup wizard."""
    console.print(Panel.fit(
        "[bold yellow]⚙  Setup Wizard[/bold yellow]\n\n"
        "I need your Steam credentials to access your inventory.\n"
        "All data is saved locally in [cyan]config.json[/cyan].",
        border_style="yellow",
    ))
    console.print()

    # ── Steam ID ──
    console.print("[bold]1/4 · Steam ID[/bold]")
    console.print("   Find yours at [link]https://steamid.io[/link] → [cyan]steamID64[/cyan]")
    cfg["steam_id"] = Prompt.ask("   ➤ Steam ID64", default=cfg.get("steam_id", ""))
    console.print()

    # ── Session Cookie ──
    console.print("[bold]2/4 · Session Cookie[/bold]")
    console.print("   Browser → [link]steamcommunity.com[/link] → F12 → Application → Cookies")
    console.print("   Copy the value of [cyan]steamLoginSecure[/cyan]")
    cfg["steam_login_secure"] = Prompt.ask("   ➤ steamLoginSecure", default=cfg.get("steam_login_secure", ""))
    console.print()

    # ── API Key ──
    console.print("[bold]3/4 · Steam API Key [dim](optional)[/dim][/bold]")
    console.print("   Enables VAC ban checking. Get one at [link]https://steamcommunity.com/dev/apikey[/link]")
    cfg["api_key"] = Prompt.ask("   ➤ API Key [dim](Enter to skip)[/dim]", default=cfg.get("api_key", ""))
    console.print()

    # ── Currency ──
    console.print("[bold]4/4 · Wallet Currency[/bold]")
    console.print()

    ctable = Table(box=box.SIMPLE, border_style="dim")
    ctable.add_column("Code", style="cyan")
    ctable.add_column("Currency")
    ctable.add_column("Symbol")
    ctable.add_column("Fee")
    for code, (name, symbol, fee_type, fee_val) in sorted(CURRENCIES.items()):
        fee_str = f"Rp {fee_val:.0f} flat" if fee_type == "flat" else f"{fee_val*100:.0f}%"
        ctable.add_row(str(code), name, symbol, fee_str)
    console.print(ctable)
    console.print()

    console.print("   [dim]Common:[/dim] [cyan]23[/cyan]=IDR  [cyan]1[/cyan]=USD  [cyan]3[/cyan]=EUR")
    console.print()
    cfg["currency"] = IntPrompt.ask("   ➤ Currency code", default=cfg.get("currency", 23))
    console.print()

    save_config(cfg)
    console.print("[green bold]✅ Setup complete![/green bold]")
    return cfg


def show_dashboard(client: SteamClient, items: list[dict], vac_info: dict | None):
    """Show inventory dashboard."""
    console.print()

    # ── Player Info ──
    ok, username = client.validate_session()
    if ok:
        console.print(Panel(
            f"[bold]{username}[/bold]\n"
            f"[dim]Steam ID: {client.cfg['steam_id']}[/dim]",
            title="👤 Account",
            border_style="cyan",
        ))

    # ── VAC Status ──
    if vac_info:
        vac_banned = vac_info.get("VACBanned", False)
        game_bans = vac_info.get("NumberOfGameBans", 0)
        if vac_banned:
            console.print(Panel("[red bold]🚫 VAC BANNED[/red bold]\nSome items may be untradeable.", border_style="red"))
        elif game_bans > 0:
            console.print(Panel(f"[yellow]⚠ {game_bans} Game Ban(s)[/yellow]", border_style="yellow"))
        else:
            console.print(Panel("[green]✅ No VAC or Game Bans[/green]", border_style="green"))
    else:
        console.print("[dim]💡 Add API key for VAC ban checking[/dim]")

    # ── Currency ──
    cur_code = client.cfg.get("currency", 23)
    cur_name, _, _, _ = get_fee_info(cur_code)
    console.print(Panel(
        f"[bold]{cur_name}[/bold] (code {cur_code}) · Fee: [yellow]{fee_display(cur_code)}[/yellow]",
        title="💱 Currency",
        border_style="yellow",
    ))

    # ── Inventory by Game ──
    stats = {}
    for item in items:
        app_id = item["app_id"]
        if app_id not in stats:
            stats[app_id] = {"name": client.get_app_name(app_id), "count": 0, "types": set()}
        stats[app_id]["count"] += 1
        if item.get("type"):
            stats[app_id]["types"].add(item["type"])

    table = Table(title="📦 Inventory", box=box.ROUNDED, border_style="cyan")
    table.add_column("Game", style="bold")
    table.add_column("Items", justify="right", style="green")
    table.add_column("Types", style="dim")
    total = 0
    for app_id, info in stats.items():
        total += info["count"]
        types_str = ", ".join(sorted(info["types"])[:4])
        if len(info["types"]) > 4:
            types_str += f" +{len(info['types'])-4}"
        table.add_row(info["name"], str(info["count"]), types_str or "—")
    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold green]{total}[/bold green]", "")
    console.print(table)


def scan_buy_orders(client: SteamClient, items: list[dict], top_n: int = 0) -> list[dict]:
    """Scan items for buy orders via Playwright."""
    if HEADLESS_MODE:
        console.print("[yellow]⚠ Playwright disabled in headless mode. Scan skipped.[/yellow]")
        return []

    if top_n > 0:
        items = items[:top_n]

    results = []
    console.print(f"\n[bold]🔍 Scanning {len(items)} items for buy orders...[/bold]")
    console.print("[dim]Uses Playwright (headless browser). ~15s per item.[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=len(items))
        for item in items:
            progress.update(task, description=f"[cyan]{item['name'][:35]}[/cyan]")
            buy_idr, sell_idr = client.scrape_buy_order(item["mhn"], item["app_id"])
            if buy_idr:
                results.append({
                    "name": item["name"],
                    "mhn": item["mhn"],
                    "app_id": item["app_id"],
                    "buy_order": buy_idr,
                    "sell": sell_idr or 0,
                })
                console.print(f"  [green]✓[/green] {item['name'][:40]:<40} Buy: {fmt_idr(buy_idr)}")
            progress.advance(task)
            time.sleep(DELAY_BETWEEN_ITEMS)

    results.sort(key=lambda x: x["buy_order"], reverse=True)
    return results


def list_items(client: SteamClient, items: list[dict], scan_results: list[dict],
               mode: str, dry_run: bool = False):
    """List items on the market.

    mode: 'buy_order' — sell at highest buy order (instant sale)
          'lowest'    — sell at lowest sell price (undercut by 1)
    """
    cur_code = client.cfg.get("currency", 23)
    cur_name, _, fee_type, fee_val = get_fee_info(cur_code)

    console.print()
    mode_label = "[green]Highest Buy Order[/green]" if mode == "buy_order" else "[yellow]Lowest Sell[/yellow]"
    console.print(f"[bold]📋 Listing {len(scan_results)} items — Mode: {mode_label}[/bold]")
    console.print(f"[dim]Currency: {cur_name} · Fee: {fee_display(cur_code)}[/dim]")
    if dry_run:
        console.print("[yellow bold]⚠ DRY RUN — nothing will be listed[/yellow bold]")
    console.print()

    # Build inventory lookup: mhn → list of items (handle duplicates)
    inv_map: dict[str, list[dict]] = {}
    for item in items:
        inv_map.setdefault(item["mhn"], []).append(item)

    table = Table(box=box.ROUNDED, border_style="cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Item", max_width=35)
    table.add_column("Buy Order", justify="right", style="cyan")
    table.add_column("Lowest Sell", justify="right", style="yellow")
    table.add_column("List At", justify="right", style="bold")
    table.add_column("→ Buyer Pays", justify="right", style="green")
    table.add_column("Result")

    total_ok = 0
    total_fail = 0
    total_revenue = 0

    for i, r in enumerate(scan_results):
        mhn = r["mhn"]
        buy_str = fmt_idr(r["buy_order"])
        sell_str = fmt_idr(r["sell"]) if r.get("sell") else "—"

        # Get next available item from inventory
        inv_list = inv_map.get(mhn, [])
        if not inv_list:
            table.add_row(str(i+1), r["name"][:35], buy_str, sell_str, "—", "—", "[dim]Not in inventory[/dim]")
            continue

        # Calculate target price
        if mode == "buy_order":
            target_buyer = r["buy_order"]
        else:
            if r.get("sell") and r["sell"] > 1:
                target_buyer = r["sell"] - 1
            else:
                table.add_row(str(i+1), r["name"][:35], buy_str, sell_str, "—", "—", "[yellow]No sell data[/yellow]")
                continue

        price_to_send = calc_listing_price(target_buyer, cur_code)
        seller = price_to_send // 100
        actual_buyer = calc_buyer_pays(seller, cur_code)
        list_str = fmt_idr(target_buyer)
        buyer_str = fmt_idr(actual_buyer)

        if dry_run:
            table.add_row(str(i+1), r["name"][:35], buy_str, sell_str, list_str, buyer_str, "[yellow]DRY-RUN[/yellow]")
            total_revenue += target_buyer
        else:
            inv_item = inv_list.pop(0)  # Take first available, remove from list
            ok, msg = client.sell_item(inv_item, price_to_send)
            if ok:
                table.add_row(str(i+1), r["name"][:35], buy_str, sell_str, list_str, buyer_str, "[green]✓[/green]")
                total_ok += 1
                total_revenue += target_buyer
            else:
                table.add_row(str(i+1), r["name"][:35], buy_str, sell_str, list_str, buyer_str, f"[red]✗ {msg}[/red]")
                total_fail += 1

        time.sleep(DELAY_BETWEEN_ITEMS)

    console.print(table)
    console.print()
    console.print(Panel(
        f"[green]Listed: {total_ok}[/green]  [red]Failed: {total_fail}[/red]\n"
        f"[bold]Est. Revenue: {fmt_idr(total_revenue)}[/bold]\n"
        f"[dim]Fee: {fee_display(cur_code)} per item ({cur_name})[/dim]",
        title="📊 Results",
        border_style="green" if total_ok > 0 else ("red" if total_fail > 0 else "yellow"),
    ))


def estimate_worth(client: SteamClient, items: list[dict]):
    """Estimate inventory worth using priceoverview API."""
    console.print()
    console.print("[bold]💰 Estimating inventory worth...[/bold]")
    console.print("[dim]Uses Steam's priceoverview API — ~1.5s per item.[/dim]")
    console.print()

    cur_code = client.cfg.get("currency", 1)
    total = 0.0
    priced = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Pricing...", total=len(items))
        for item in items:
            progress.update(task, description=f"[cyan]{item['name'][:35]}[/cyan]")
            data = client.get_price_overview(item["mhn"], item["app_id"])
            if data:
                price_str = data.get("lowest", "")
                # Parse price: remove currency symbols, handle thousand separators
                cleaned = re.sub(r'[^\d.,]', '', price_str)
                if cleaned:
                    # Handle "1,582" (thousands) vs "1.58" (decimal)
                    if "," in cleaned and "." in cleaned:
                        cleaned = cleaned.replace(",", "")
                    elif "," in cleaned:
                        parts = cleaned.split(",")
                        cleaned = cleaned.replace(",", "") if len(parts[-1]) == 3 else cleaned.replace(",", ".")
                    try:
                        total += float(cleaned)
                        priced += 1
                    except ValueError:
                        failed += 1
                else:
                    failed += 1
            else:
                failed += 1
            progress.advance(task)
            time.sleep(1.5)

    symbol = get_fee_info(cur_code)[1]
    if cur_code == 1:
        total_str = f"${total:,.2f}"
    else:
        total_str = f"{symbol} {total:,.0f}"

    console.print()
    console.print(Panel(
        f"[green]Estimated total:[/green]  [bold]{total_str}[/bold]\n"
        f"[dim]Priced: {priced} | Failed: {failed} | Total: {len(items)}[/dim]",
        title="💰 Inventory Worth",
        border_style="green",
    ))


# ─── Manual Listing ──────────────────────────────────────────────────────────

def manual_list(client: SteamClient, items: list[dict]):
    """Manual listing: user picks an item, sees market data, inputs price."""
    cur_code = client.cfg.get("currency", 23)
    cur_name, _, fee_type, fee_val = get_fee_info(cur_code)

    console.print()
    console.print("[bold cyan]✏️  Manual Listing[/bold cyan]")
    console.print()

    page_size = 20
    page = 0
    total_pages = max(1, (len(items) - 1) // page_size + 1)

    while True:
        start = page * page_size
        end = min(start + page_size, len(items))
        page_items = items[start:end]

        table = Table(title=f"📦 Inventory (page {page+1}/{total_pages})", box=box.ROUNDED, border_style="cyan")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Item")
        table.add_column("Game", style="yellow")
        table.add_column("Type", style="dim")

        for i, item in enumerate(page_items):
            idx = start + i + 1
            table.add_row(str(idx), item["name"][:40], client.get_app_name(item["app_id"]), item.get("type", "")[:25])

        console.print(table)
        console.print()
        console.print(f"[dim]Item number (1-{len(items)}), [cyan]n[/cyan]=next, [cyan]p[/cyan]=prev, [cyan]0[/cyan]=back[/dim]")
        choice = Prompt.ask("  ➤ Choose")

        if choice == "0":
            return
        elif choice == "n" and page < total_pages - 1:
            page += 1
            continue
        elif choice == "p" and page > 0:
            page -= 1
            continue

        try:
            idx = int(choice) - 1
        except ValueError:
            console.print("[red]Invalid — enter a number[/red]")
            continue

        if idx < 0 or idx >= len(items):
            console.print(f"[red]Enter 1-{len(items)}[/red]")
            continue

        item = items[idx]
        game = client.get_app_name(item["app_id"])

        # Fetch market data
        console.print()
        console.print(f"[bold]Fetching market data for: [cyan]{item['name']}[/cyan][/bold]")

        buy_idr, sell_idr = None, None
        if not HEADLESS_MODE:
            with console.status("[cyan]Scraping buy order...[/cyan]"):
                buy_idr, sell_idr = client.scrape_buy_order(item["mhn"], item["app_id"])

        with console.status("[cyan]Getting price overview...[/cyan]"):
            price_data = client.get_price_overview(item["mhn"], item["app_id"])

        # Show item info
        console.print()
        info_lines = [
            f"  [bold]Item:[/bold]      {item['name']}",
            f"  [bold]Game:[/bold]      {game}",
            f"  [bold]Type:[/bold]      {item.get('type') or '—'}",
            "",
            f"  [cyan]Buy Order:[/cyan]    {fmt_idr(buy_idr) if buy_idr else '[dim]None[/dim]'}",
            f"  [yellow]Lowest Sell:[/yellow] {fmt_idr(sell_idr) if sell_idr else '[dim]None[/dim]'}",
        ]
        if price_data:
            info_lines.append(f"  [dim]Market Price:[/dim]   {price_data.get('lowest', '—')}")
        info_lines.append("")
        info_lines.append(f"  [dim]Fee: {cur_name} — {fee_display(cur_code)}[/dim]")
        console.print(Panel("\n".join(info_lines), title=f"🏷 {item['name']}", border_style="cyan"))

        # Price input
        console.print()
        console.print(f"[bold]Enter [cyan]buyer pays[/cyan] amount ({cur_name})[/bold]")
        if buy_idr:
            console.print(f"  [cyan]{fmt_idr(buy_idr)}[/cyan] = buy order (instant sale)")
        if sell_idr:
            console.print(f"  [yellow]{fmt_idr(sell_idr)}[/yellow] = lowest sell (competitive)")
        console.print(f"  [dim]0 = skip[/dim]")
        console.print()

        # Default to buy_order if available, else sell
        default_price = buy_idr or sell_idr or 0
        price_input = IntPrompt.ask("  ➤ Amount", default=default_price)

        if price_input <= 0:
            console.print("[dim]Skipped[/dim]")
            continue

        # Calculate & verify
        price_to_send = calc_listing_price(price_input, cur_code)
        seller = price_to_send // 100
        actual_buyer = calc_buyer_pays(seller, cur_code)

        console.print()
        console.print(Panel(
            f"  [bold]You entered (buyer pays):[/bold]  {fmt_idr(price_input)}\n"
            f"  [green]Seller receives:[/green]         {fmt_idr(seller)}\n"
            f"  [yellow]Fee:[/yellow]                    {fee_display(cur_code)}\n"
            f"  [cyan]Price to send:[/cyan]            {price_to_send:,} sen\n"
            f"  [dim]Verify → actual buyer pays:[/dim] {fmt_idr(actual_buyer)}",
            title="📋 Listing Preview",
            border_style="yellow",
        ))

        # Verify match
        if actual_buyer != price_input:
            console.print(f"[yellow]⚠ Note: buyer will pay {fmt_idr(actual_buyer)}, not {fmt_idr(price_input)}[/yellow]")

        console.print()
        if not Confirm.ask("  ➤ List this item?", default=True):
            console.print("[dim]Cancelled[/dim]")
            continue

        # List
        ok, msg = client.sell_item(item, price_to_send)
        if ok:
            console.print(f"[green bold]✅ Listed! Buyer pays {fmt_idr(actual_buyer)}[/green bold]")
            items.remove(item)
        else:
            console.print(f"[red bold]✗ Failed: {msg}[/red bold]")

        console.print()
        if not Confirm.ask("  List another?", default=True):
            return


# ─── Main Menu ───────────────────────────────────────────────────────────────

def main_menu(client: SteamClient, items: list[dict], vac_info: dict | None):
    """Main interactive menu."""
    scan_cache = []

    while True:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]📋 Main Menu[/bold cyan]\n\n"
            "  [bold]1[/bold]  📊  Dashboard\n"
            "  [bold]2[/bold]  🔍  Scan for buy orders\n"
            "  [bold]3[/bold]  📦  List → [green]highest buy order[/green]\n"
            "  [bold]4[/bold]  📦  List → [yellow]lowest sell price[/yellow]\n"
            "  [bold]5[/bold]  💰  Estimate inventory worth\n"
            "  [bold]6[/bold]  🔄  Refresh inventory\n"
            "  [bold]7[/bold]  ⚙   Settings\n"
            "  [bold]8[/bold]  ✏️   Manual listing\n"
            "  [bold]0[/bold]  🚪  Exit",
            border_style="cyan",
        ))

        choice = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5","6","7","8"], default="1")

        if choice == "0":
            console.print("[dim]Bye![/dim]")
            break

        elif choice == "1":
            show_dashboard(client, items, vac_info)

        elif choice == "2":
            console.print()
            console.print("[bold]Scan options:[/bold]")
            console.print("  [cyan]0[/cyan] = all items (slow)")
            console.print("  [cyan]N[/cyan] = first N items")
            n = IntPrompt.ask("  ➤ How many?", default=0)
            scan_cache = scan_buy_orders(client, items, top_n=n)
            if scan_cache:
                console.print(f"\n[green bold]✅ Found {len(scan_cache)} items with buy orders[/green bold]")
                stable = Table(title="📋 Scan Results", box=box.ROUNDED, border_style="cyan")
                stable.add_column("#", justify="right", style="dim")
                stable.add_column("Item")
                stable.add_column("Buy Order", justify="right", style="cyan")
                stable.add_column("Lowest Sell", justify="right", style="yellow")
                for j, r in enumerate(scan_cache):
                    stable.add_row(str(j+1), r["name"][:40], fmt_idr(r["buy_order"]),
                                   fmt_idr(r["sell"]) if r.get("sell") else "—")
                console.print(stable)
                console.print("[dim]Use menu 3 or 4 to list them.[/dim]")
            else:
                console.print("[yellow]No items with buy orders found.[/yellow]")

        elif choice == "3":
            if not scan_cache:
                console.print("[yellow]⚠ No scan results. Run scan first (option 2).[/yellow]")
                continue
            console.print()
            console.print("[bold]🏷 Listing at [green]highest buy order[/green][/bold]")
            console.print("[dim]Items sell instantly at buy order price.[/dim]")
            console.print()
            dry = Confirm.ask("  Dry run first?", default=True)
            list_items(client, items, scan_cache, mode="buy_order", dry_run=dry)
            if dry:
                console.print()
                if Confirm.ask("  Looks good? List for real?", default=False):
                    list_items(client, items, scan_cache, mode="buy_order", dry_run=False)

        elif choice == "4":
            if not scan_cache:
                console.print("[yellow]⚠ No scan results. Run scan first (option 2).[/yellow]")
                continue
            console.print()
            console.print("[bold]📉 Listing at [yellow]lowest sell price[/yellow] (undercut by 1)[/bold]")
            console.print("[dim]Competitive pricing — may take longer to sell.[/dim]")
            console.print()
            dry = Confirm.ask("  Dry run first?", default=True)
            list_items(client, items, scan_cache, mode="lowest", dry_run=dry)
            if dry:
                console.print()
                if Confirm.ask("  Looks good? List for real?", default=False):
                    list_items(client, items, scan_cache, mode="lowest", dry_run=False)

        elif choice == "5":
            estimate_worth(client, items)

        elif choice == "6":
            console.print("[bold]🔄 Refreshing inventory...[/bold]")
            time.sleep(10)
            items = client.get_all_inventory()
            console.print(f"[green bold]✅ {len(items)} marketable items loaded[/green bold]")

        elif choice == "7":
            console.print()
            cfg = client.cfg
            cur_code = cfg.get("currency", 23)
            cur_name, _, _, _ = get_fee_info(cur_code)

            console.print(Panel(
                f"  Steam ID:     [cyan]{cfg.get('steam_id', '—')}[/cyan]\n"
                f"  API Key:      {'[green]Set[/green]' if cfg.get('api_key') else '[dim]Not set[/dim]'}\n"
                f"  Currency:     [cyan]{cur_name}[/cyan] (code {cur_code}) · Fee: {fee_display(cur_code)}\n"
                f"  Cookie:       {'[green]Set[/green]' if cfg.get('steam_login_secure') or COOKIES_FILE.exists() else '[red]Not set[/red]'}\n"
                f"  Headless:     {'[yellow]Yes[/yellow]' if HEADLESS_MODE else '[green]No[/green]'}",
                title="⚙ Settings",
                border_style="yellow",
            ))
            console.print()
            console.print("[bold]Options:[/bold]")
            console.print("  [cyan]1[/cyan]  Change currency")
            console.print("  [cyan]2[/cyan]  Re-run full setup wizard")
            console.print("  [cyan]3[/cyan]  Back")
            console.print()
            sub = Prompt.ask("  ➤ Choose", choices=["1","2","3"], default="3")
            if sub == "1":
                console.print()
                for code, (name, symbol, ft, fv) in sorted(CURRENCIES.items()):
                    fs = f"Rp {fv:.0f} flat" if ft == "flat" else f"{fv*100:.0f}%"
                    marker = " ◀ current" if code == cur_code else ""
                    console.print(f"  [cyan]{code:>2}[/cyan]  {name:<10} {symbol:<4} {fs}{marker}")
                console.print()
                new_cur = IntPrompt.ask("  ➤ New currency code", default=cur_code)
                cfg["currency"] = new_cur
                save_config(cfg)
                client.cfg = cfg
                new_name, _, _, _ = get_fee_info(new_cur)
                console.print(f"[green]✅ Currency → {new_name}[/green]")
            elif sub == "2":
                cfg = setup_wizard(cfg)
                client.cfg = cfg

        elif choice == "8":
            manual_list(client, items)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global HEADLESS_MODE

    parser = argparse.ArgumentParser(description="Steam Market Bot — TUI Edition")
    parser.add_argument("--headless", action="store_true", help="Skip Playwright (no buy order scraping)")
    args = parser.parse_args()
    HEADLESS_MODE = args.headless

    show_banner()

    cfg = load_config()

    if not cfg.get("steam_id"):
        cfg = setup_wizard(cfg)

    client = SteamClient(cfg)

    # Validate session
    with console.status("[bold cyan]Validating session..."):
        ok, info = client.validate_session()

    if not ok:
        console.print(f"[red]✗ Session invalid: {info}[/red]")
        console.print()
        if Confirm.ask("Run setup wizard?", default=True):
            cfg = setup_wizard(cfg)
            client = SteamClient(cfg)
            with console.status("[bold cyan]Validating session..."):
                ok, info = client.validate_session()
        if not ok:
            console.print("[red]Still invalid. Check your credentials.[/red]")
            sys.exit(1)

    console.print(f"[green]✓ Logged in as: [bold]{info}[/bold][/green]")

    # VAC check
    vac_info = client.get_vac_bans()
    if vac_info and vac_info.get("VACBanned"):
        console.print("[red bold]⚠ VAC BANNED — some items may be untradeable![/red bold]")

    # Load inventory
    console.print()
    console.print("[bold]📦 Loading inventory...[/bold]")
    time.sleep(10)
    items = client.get_all_inventory()
    if not items:
        console.print("[red]No marketable items found. Check inventory privacy.[/red]")
        sys.exit(1)

    console.print(f"\n[green bold]✅ {len(items)} marketable items loaded[/green bold]")

    show_dashboard(client, items, vac_info)
    main_menu(client, items, vac_info)


if __name__ == "__main__":
    main()
