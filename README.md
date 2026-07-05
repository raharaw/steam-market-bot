<div align="center">

# 🎮 Steam Market Bot

### TUI Edition

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/YOUR_USERNAME/steam-market-bot?style=social)](https://github.com/YOUR_USERNAME/steam-market-bot)

**Sell your Steam items smarter. Not harder.**

A terminal-based tool that scans your inventory, finds the best prices,
and lists items on the Steam Community Market — all from your terminal.

![Demo](https://via.placeholder.com/800x400/1a1a2e/00d4ff?text=Steam+Market+Bot+TUI)

</div>

---

## ✨ What It Does

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   📦 Scans your entire Steam inventory                      │
│   🔍 Finds highest buy orders for each item                 │
│   📊 Shows real-time market data                            │
│   🏷  Lists items at buy order price (instant sale!)         │
│   💰 Estimates total inventory worth                        │
│   🛡  Detects VAC bans (warns if items untradeable)          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/steam-market-bot.git
cd steam-market-bot
pip install -r requirements.txt
playwright install chromium
```

### 2. Run

```bash
python bot.py
```

That's it. The setup wizard will guide you through everything on first run.

---

## 📖 How to Use

### First Run — Setup Wizard

When you run the bot for the first time, it will ask for:

```
╔═══════════════════════════════════════════╗
║           ⚙  Setup Wizard                ║
╚═══════════════════════════════════════════╝

1/4 · Steam ID
   ➤ Enter your steamID64

2/4 · Session Cookie
   ➤ Paste your steamLoginSecure value

3/4 · Steam API Key (optional)
   ➤ For VAC ban detection

4/4 · Wallet Currency
   ➤ Pick from the table (e.g., 23 for IDR)
```

### Getting Your Session Cookie

This is the trickiest part. Here's exactly how:

```
Step 1:  Open your browser → go to steamcommunity.com
Step 2:  Log in to your Steam account
Step 3:  Press F12 (opens DevTools)
Step 4:  Click "Application" tab (Chrome) or "Storage" (Firefox)
Step 5:  Left sidebar → Cookies → steamcommunity.com
Step 6:  Find "steamLoginSecure" → copy its VALUE
Step 7:  Paste into the bot when prompted
```

> ⚠️ **Session cookies expire.** If you see "Session expired",
> just repeat steps 1-7 to get a fresh one.

### Getting Your Steam ID

```
Step 1:  Go to https://steamid.io
Step 2:  Paste your Steam profile URL
Step 3:  Copy the "steamID64" number (starts with 76561198...)
```

### Getting a Steam API Key (Optional)

```
Step 1:  Go to https://steamcommunity.com/dev/apikey
Step 2:  Register with any domain name (e.g., "localhost")
Step 3:  Copy the key
```

> 💡 The API key enables VAC ban detection. The bot works fine without it.

---

## 🎯 Main Menu

Once set up, you'll see the interactive menu:

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
║   0  🚪  Exit                         ║
║                                       ║
╚═══════════════════════════════════════╝
```

### Recommended Workflow

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  Step 1:  Press 1 → see your inventory overview            │
│                                                            │
│  Step 2:  Press 2 → scan items for buy orders              │
│           (this takes ~15 seconds per item)                │
│                                                            │
│  Step 3:  Press 3 → list at buy order (instant sale!)      │
│           always do dry-run first!                         │
│                                                            │
│  Step 4:  Confirm → items listed on Steam Market           │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## 💱 Pricing Modes

### Mode 1: Highest Buy Order (Recommended)

```
  ┌──────────────────────────────────────────────┐
  │  🏷  List at highest buy order price          │
  │                                              │
  │  • Items sell INSTANTLY                      │
  │  • Matches the highest buy order             │
  │  • Best for: quick sales, clearing inventory │
  └──────────────────────────────────────────────┘
```

**How it works:**
```
Buy order = Rp 6,843

  Steam fee (IDR)  = Rp 360 flat
  Seller receives  = Rp 6,843 - 360 = Rp 6,483
  Price to send    = 648,300 sen (6,483 × 100)

  → Buyer pays Rp 6,843 (matches buy order!) ✅
```

### Mode 2: Lowest Sell Price

```
  ┌──────────────────────────────────────────────┐
  │  📉  List at lowest sell price (undercut)     │
  │                                              │
  │  • Competitive pricing                       │
  │  • Undercuts current lowest seller by 1      │
  │  • Best for: maximizing value, patient sales │
  └──────────────────────────────────────────────┘
```

---

## 💰 Fee Structure

### IDR (Indonesian Rupiah) — Flat Fee

```
  ┌─────────────────────────────────────────┐
  │  Steam charges Rp 360 per transaction   │
  │                                         │
  │  buyer_pays = seller_receives + Rp 360  │
  └─────────────────────────────────────────┘
```

**Verified test cases:**

| Target (Buyer Pays) | Seller Receives | Send Price | Result |
|:-------------------:|:---------------:|:----------:|:------:|
| Rp 32,852 | Rp 32,492 | 3,249,200 sen | ✅ |
| Rp 6,843 | Rp 6,483 | 648,300 sen | ✅ |
| Rp 1,582 | Rp 1,222 | 122,200 sen | ✅ |
| Rp 540 | Rp 180 | 18,000 sen | ✅ |

### Other Currencies — ~15% Fee

```
  ┌─────────────────────────────────────────┐
  │  Steam takes ~15% of the sale price     │
  │                                         │
  │  seller_receives = buyer_pays × 0.85   │
  └─────────────────────────────────────────┘
```

### Supported Currencies

| Code | Currency | Symbol | Fee Type |
|:----:|:--------:|:------:|:--------:|
| 1 | US Dollar | $ | 15% |
| 2 | British Pound | £ | 15% |
| 3 | Euro | € | 15% |
| 5 | Russian Ruble | ₽ | 15% |
| **23** | **Indonesian Rupiah** | **Rp** | **Rp 360 flat** |
| 25 | Malaysian Ringgit | RM | 15% |
| 27 | Singapore Dollar | S$ | 15% |
| 28 | Thai Baht | ฿ | 15% |
| 29 | Vietnamese Dong | ₫ | 15% |
| 37 | Turkish Lira | ₺ | 15% |

> 💡 Change currency anytime via **Menu → Settings → Change currency**

---

## 📊 Dashboard Preview

```
┌─ 👤 Account ─────────────────────────────────┐
│  Lord Cilung                                  │
│  Steam ID: 76561198000000000                  │
└───────────────────────────────────────────────┘

┌─ 🛡 VAC Status ──────────────────────────────┐
│  ✅ No VAC or Game Bans                       │
└───────────────────────────────────────────────┘

┌─ 💱 Currency ────────────────────────────────┐
│  IDR (code 23) · Fee: Rp 360 flat            │
└───────────────────────────────────────────────┘

┌─ 📦 Inventory ──────────────────────────────┐
│  Game          │ Items │ Types               │
│  ──────────────┼───────┼──────────────────── │
│  Dota 2        │   210 │ Rare shield, ...    │
│  Steam         │    28 │ Trading Card, ...   │
│  ──────────────┼───────┼──────────────────── │
│  Total         │   238 │                     │
└───────────────────────────────────────────────┘
```

---

## 🔧 Troubleshooting

### "Session expired"

Your `steamLoginSecure` cookie expired. Get a fresh one:

```
Browser → steamcommunity.com → F12 → Application → Cookies
→ Copy new "steamLoginSecure" value
→ Re-run: python bot.py → Settings → Re-run setup wizard
```

### "Inventory is private"

```
Steam → Profile → Edit Profile → Privacy Settings
→ Set "Inventory" to "Public"
```

### "Login failed" during scan

Multiple scans running at once cause session conflicts. Run one scan at a time.

### Items not selling

- Buy orders may have been filled by other sellers
- Re-scan to get updated prices
- Try "lowest sell" mode for competitive pricing

---

## 📁 Project Structure

```
steam-market-bot/
│
├── bot.py                 ← Main script (run this)
├── requirements.txt       ← Python dependencies
├── config.example.json    ← Example config
├── config.json            ← Your config (auto-generated, gitignored)
├── cookies.json           ← Your session cookies (gitignored)
├── README.md              ← This file
└── .gitignore             ← Git ignore rules
```

---

## ⚠️ Disclaimer

This tool is for **educational purposes only**.

- Use at your own risk
- Steam's ToS may restrict automated market operations
- The authors are not responsible for account restrictions or bans
- Always do a **dry run** before listing real items

---

## 📜 License

MIT — do whatever you want with it.

---

<div align="center">

**Built with ❤️ and laziness**

*The best code is the code never written.*

</div>
