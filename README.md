<div align="center">

# 🎮 Steam Market Bot

### TUI Edition

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/raharaw/steam-market-bot?style=social)](https://github.com/raharaw/steam-market-bot)

**Sell your Steam items smarter. Not harder.**

Scans your inventory → finds best prices → lists items on Steam Market.

</div>

---

## ✨ Features

```
📦  Scan entire Steam inventory (Dota 2, Steam Cards, etc.)
🔍  Find highest buy orders via Playwright
🏷   List items at buy order price (instant sale!)
📉  Or list at lowest sell price (competitive)
✏️   Manual listing — set your own price per item
💰  Estimate total inventory worth
🛡   VAC ban detection
📊  Dashboard with game stats & item types
🏃  Headless mode (no Playwright, API only)
```

---

## 🚀 Quick Start

```bash
git clone https://github.com/raharaw/steam-market-bot.git
cd steam-market-bot
pip install -r requirements.txt
playwright install chromium
python bot.py
```

Setup wizard guides you on first run. That's it.

---

## 📖 How to Use

### Step 1: Get Your Credentials

**Steam ID:**
```
1. Go to https://steamid.io
2. Paste your Steam profile URL
3. Copy "steamID64" (starts with 76561198...)
```

**Session Cookie:**
```
1. Open steamcommunity.com in your browser
2. Log in to your Steam account
3. Press F12 → Application tab → Cookies → steamcommunity.com
4. Find "steamLoginSecure" → copy its VALUE
```

**API Key (optional, for VAC check):**
```
1. Go to https://steamcommunity.com/dev/apikey
2. Register with any domain (e.g., "localhost")
3. Copy the key
```

### Step 2: Run the Bot

```bash
python bot.py
```

The setup wizard asks for your credentials on first run. Saved to `config.json`.

### Step 3: Use the Menu

```
╔═══════════════════════════════════════╗
║         📋 Main Menu                 ║
║                                       ║
║   1  📊  Dashboard                    ║
║   2  🔍  Scan for buy orders          ║
║   3  📦  List → highest buy order     ║
║   4  📦  List → lowest sell price     ║
║   5  💰  Estimate inventory worth     ║
║   6  🔄  Refresh inventory            ║
║   7  ⚙   Settings                     ║
║   8  ✏️   Manual listing               ║
║   0  🚪  Exit                         ║
║                                       ║
╚═══════════════════════════════════════╝
```

### Recommended Workflow

```
1 → See your inventory overview
2 → Scan items for buy orders (~15s per item)
3 → List at buy order (instant sale!)
   → Always do dry-run first!
```

---

## ✏️ Manual Listing

Pick any item from your inventory, see its market data, and set your own price.

```
┌─────────────────────────────────────────────┐
│  📦 Inventory (page 1/11)                   │
│                                             │
│   #  Item                    Game    Type   │
│   1  Spear of Teardrop Ice   Dota 2  Common │
│   2  Taunt: Chicken!         Dota 2  Mythic │
│  ...                                        │
│                                             │
│  Enter item number, n=next, p=prev, 0=back  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  🏷 Taunt: Chicken!                         │
│                                             │
│  Item:      Taunt: Chicken!                 │
│  Game:      Dota 2                          │
│  Type:      Mythical Taunt                  │
│                                             │
│  Buy Order:    Rp 6,843                     │
│  Lowest Sell:  Rp 7,307                     │
│  Market Price: $0.04                        │
│                                             │
│  Fee: IDR — Rp 360 flat                     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  📋 Listing Preview                         │
│                                             │
│  You entered (buyer pays):  Rp 6,843        │
│  Seller receives:           Rp 6,483        │
│  Fee:                       Rp 360          │
│  Price to send:             648,300 sen      │
│  Verify → actual buyer pays: Rp 6,843 ✓    │
│                                             │
│  ➤ List this item? [Y/n]                    │
└─────────────────────────────────────────────┘
```

---

## 💱 Pricing

### IDR (Indonesian Rupiah) — Flat Fee

```
buyer_pays = seller_receives + Rp 360
```

| Target | Seller | Send Price | Result |
|:------:|:------:|:----------:|:------:|
| Rp 32,852 | Rp 32,492 | 3,249,200 sen | ✅ |
| Rp 6,843 | Rp 6,483 | 648,300 sen | ✅ |
| Rp 1,582 | Rp 1,222 | 122,200 sen | ✅ |
| Rp 540 | Rp 180 | 18,000 sen | ✅ |

### Other Currencies — ~15% Fee

```
seller_receives = buyer_pays × 0.85
```

### Supported Currencies

| Code | Currency | Fee |
|:----:|:--------:|:---:|
| 1 | USD ($) | 15% |
| 3 | EUR (€) | 15% |
| **23** | **IDR (Rp)** | **Rp 360 flat** |
| 5 | RUB (₽) | 15% |
| 25 | MYR (RM) | 15% |
| 27 | SGD (S$) | 15% |
| 28 | THB (฿) | 15% |
| 29 | VND (₫) | 15% |

Change anytime: **Menu → Settings → Change currency**

---

## 🏃 Headless Mode

Skip Playwright for faster startup (no buy order scanning):

```bash
python bot.py --headless
```

- ✅ Inventory loading works
- ✅ Price overview works
- ✅ Manual listing works
- ❌ Buy order scanning disabled
- ❌ Auto-listing modes need scan first

Use this when you only need manual listing or price checking.

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Session expired" | Get fresh `steamLoginSecure` cookie, re-run setup |
| "Inventory is private" | Steam → Profile → Privacy → Inventory → Public |
| "Login failed" during scan | Don't run multiple scans at once |
| Items not selling | Re-scan for updated prices, try lowest sell mode |
| Playwright not found | Run `playwright install chromium` |

---

## 📁 Project Structure

```
steam-market-bot/
├── bot.py                 ← Run this
├── requirements.txt       ← Dependencies
├── config.example.json    ← Example config
├── config.json            ← Your config (gitignored)
├── cookies.json           ← Your session (gitignored)
├── README.md
└── .gitignore
```

---

## ⚠️ Disclaimer

For **educational purposes only**. Use at your own risk. Steam's ToS may restrict automated operations. Always do a **dry run** before listing.

---

## 📜 License

MIT

---

<div align="center">

**Built with ❤️ and laziness**

*The best code is the code never written.*

</div>
