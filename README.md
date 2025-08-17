# 🕵️‍♂️ bounty-scope

Track **Bug Bounty program scopes** in real time.  
This tool fetches program data from [HackerOne public dataset](https://github.com/arkadiyt/bounty-targets-data), detects **added/removed in-scope assets**, and maintains a **live Excel file** of currently active assets.  
All state is stored in a local **SQLite database**.

---

## ✨ Features
- ⏱️ Polls HackerOne data periodically (default every 60s)  
- 🟢 Detects **new in-scope assets**  
- 🔴 Detects **removed assets**  
- 📊 Maintains an up-to-date **Excel file** (`.xlsx`)  
- 🗂️ Uses **SQLite** (`assets.db`) for storing the latest snapshot  
- 🎨 Clean, colorful console output (via [rich](https://github.com/Textualize/rich))  
- ⌨️ Press **Enter** to force an immediate fetch (no waiting)  

---

## 📦 Installation

Clone the repo and install dependencies:

```bash
git clone https://github.com/username/bounty-scope.git
cd bounty-scope
pip install -r requirements.txt
```

### Requirements
- Python 3.9+
- [requests](https://pypi.org/project/requests/)  
- [pandas](https://pypi.org/project/pandas/)  
- [openpyxl](https://pypi.org/project/openpyxl/)  
- [rich](https://pypi.org/project/rich/)  

Install all with:
```bash
pip install requests pandas openpyxl rich
```

---

## 🚀 Usage

```bash
python bounty-scope.py [options]
```

### Options
```
  -h, --help            Show help message and exit
  -o, --output FILE     Output Excel file (default: new_assets.xlsx)
  --db FILE             SQLite DB file (default: assets.db)
  -i, --interval SEC    Polling interval in seconds (default: 60)
```

### Examples

Run with defaults (Excel = `new_assets.xlsx`, DB = `assets.db`, interval = 60s):
```bash
python bounty-scope.py
```

Use a custom Excel file and DB:
```bash
python bounty-scope.py -o bugbounty_assets.xlsx --db bounty.db -i 30
```

---

## 📊 Output Example

### Console
```
[17.08.2025 14:30] Changes detected
Change   Program              Program URL                        Asset Type   Asset
------------------------------------------------------------------------------------------
Added    Example Program      https://hackerone.com/example      URL          docs.example.com
Removed  Another Program      https://hackerone.com/another      API          https://old-api.example.com/
```

### Excel (`new_assets.xlsx`)
| Timestamp        | Program         | Program URL                           | Asset Type | Asset                        |
|------------------|----------------|----------------------------------------|------------|------------------------------|
| 17.08.2025 14:30 | Example Program | https://hackerone.com/example          | URL        | docs.example.com             |
| 17.08.2025 14:30 | Example Program | https://hackerone.com/example          | URL        | www.portal.example.com       |

---

## 🛠️ How It Works
1. Fetch JSON data from [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data).  
2. Parse in-scope targets for each program.  
3. Compare against last snapshot stored in SQLite.  
4. Log **added/removed** assets in console and update Excel.  
5. Update the database with the new snapshot.  

---

## 📌 Roadmap
- [ ] Add optional Slack/Discord/Telegram notifications  
- [ ] Add export to CSV/JSON  
- [ ] Add support for more bug bounty platforms  

---

## 📜 License
MIT License © 2025 Anonymous
