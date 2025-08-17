#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, select, time, argparse, requests, pandas as pd, sqlite3
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box

DATA_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/hackerone_data.json"
REQUEST_TIMEOUT = 30

COLUMNS = ["Timestamp", "Program", "Program URL", "Asset Type", "Asset"]
console = Console()

# Return current timestamp formatted as "dd.mm.yyyy hh:mm"
def now_str():
    return datetime.now().strftime("%d.%m.%Y %H:%M")

# Fetch HackerOne JSON data
def fetch():
    resp = requests.get(DATA_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

# Build maps of assets and program meta
def build_maps(data):
    inscope, meta = {}, {}
    for p in data:
        h = (p.get("handle") or "").strip()
        meta[h] = ((p.get("name") or h).strip(), (p.get("url") or "").strip())
        aset = set()
        for t in (p.get("targets", {}) or {}).get("in_scope", []) or []:
            ident = (t.get("asset_identifier") or "").strip()
            atype = (t.get("asset_type") or "").strip()
            if ident:
                aset.add((ident, atype))
        inscope[h] = aset
    return inscope, meta

# Initialize SQLite schema
def init_db(conn: sqlite3.Connection):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS programs (
        handle TEXT PRIMARY KEY,
        name   TEXT NOT NULL,
        url    TEXT NOT NULL
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS assets (
        handle           TEXT NOT NULL,
        asset_identifier TEXT NOT NULL,
        asset_type       TEXT NOT NULL,
        PRIMARY KEY (handle, asset_identifier, asset_type),
        FOREIGN KEY (handle) REFERENCES programs(handle) ON DELETE CASCADE
      )
    """)
    conn.commit()

# Snapshot from DB
def db_snapshot(conn: sqlite3.Connection):
    snap = {}
    for handle, ident, atype in conn.execute("SELECT handle, asset_identifier, asset_type FROM assets"):
        snap.setdefault(handle, set()).add((ident, atype))
    return snap

# Program meta from DB
def db_meta(conn: sqlite3.Connection):
    meta = {}
    for handle, name, url in conn.execute("SELECT handle, name, url FROM programs"):
        meta[handle] = (name, url)
    return meta

# Insert/update program
def upsert_program(conn: sqlite3.Connection, handle: str, name: str, url: str):
    conn.execute("""
      INSERT INTO programs(handle, name, url)
      VALUES (?, ?, ?)
      ON CONFLICT(handle) DO UPDATE SET name=excluded.name, url=excluded.url
    """, (handle, name, url))

# Apply asset changes to DB
def apply_asset_changes(conn: sqlite3.Connection, changes: dict, meta_live: dict):
    for handle, diff in changes.items():
        name, url = meta_live.get(handle, (handle, ""))
        upsert_program(conn, handle, name, url)
        for ident, atype in diff.get("added", set()):
            conn.execute("""
              INSERT OR IGNORE INTO assets(handle, asset_identifier, asset_type)
              VALUES (?, ?, ?)
            """, (handle, ident, atype))
        for ident, atype in diff.get("removed", set()):
            conn.execute("""
              DELETE FROM assets
              WHERE handle=? AND asset_identifier=? AND asset_type=?
            """, (handle, ident, atype))
    conn.commit()

# Detect differences
def detect_changes(prev: dict, curr: dict):
    changes = {}
    for h in set(prev.keys()) | set(curr.keys()):
        a, b = prev.get(h, set()), curr.get(h, set())
        add, rem = b - a, a - b
        if add or rem:
            changes[h] = {"added": add, "removed": rem}
    return changes

# Console output
def render_console(changes: dict, meta: dict):
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Change", style="bold")
    table.add_column("Program", style="cyan", no_wrap=True)
    table.add_column("Program URL", style="cyan")
    table.add_column("Asset Type", style="magenta", no_wrap=True)
    table.add_column("Asset", style="white")
    for h, diff in sorted(changes.items()):
        prog, url = meta.get(h, (h, ""))
        for ident, atype in sorted(diff["added"]):
            table.add_row("[green]Added[/green]", prog, url, atype or "-", ident)
        for ident, atype in sorted(diff["removed"]):
            table.add_row("[red]Removed[/red]", prog, url, atype or "-", ident)
    console.print(f"[bold magenta][{now_str()}] Changes detected[/bold magenta]")
    console.print(table)

# Ensure Excel exists
def ensure_excel(path: Path):
    if not path.exists():
        pd.DataFrame(columns=COLUMNS).to_excel(path, index=False)

# Update Excel
def update_excel(path: Path, added_rows, removed_rows):
    ensure_excel(path)
    df = pd.read_excel(path, dtype=str).fillna("")
    if not df.empty:
        df = df[COLUMNS]
    else:
        df = pd.DataFrame(columns=COLUMNS)

    if removed_rows:
        rem = pd.DataFrame(removed_rows, columns=COLUMNS)
        for _, r in rem.iterrows():
            mask = (
                (df["Program"] == r["Program"]) &
                (df["Program URL"] == r["Program URL"]) &
                (df["Asset Type"] == r["Asset Type"]) &
                (df["Asset"] == r["Asset"])
            )
            df = df.loc[~mask]

    if added_rows:
        add = pd.DataFrame(added_rows, columns=COLUMNS)
        for _, r in add.iterrows():
            mask = (
                (df["Program"] == r["Program"]) &
                (df["Program URL"] == r["Program URL"]) &
                (df["Asset Type"] == r["Asset Type"]) &
                (df["Asset"] == r["Asset"])
            )
            if not df.loc[mask].any().any():
                df = pd.concat([df, pd.DataFrame([r])], ignore_index=True)

    df.to_excel(path, index=False)

# One cycle
def tick(conn: sqlite3.Connection, xlsx_path: Path):
    live_data = fetch()
    curr_map, live_meta = build_maps(live_data)

    prev_map = db_snapshot(conn)
    prev_meta = db_meta(conn)
    meta_for_print = {**prev_meta, **live_meta}

    changes = detect_changes(prev_map, curr_map)

    if changes:
        render_console(changes, meta_for_print)
        rows_added, rows_removed = [], []
        for h, diff in sorted(changes.items()):
            prog, url = meta_for_print.get(h, (h, ""))
            for ident, atype in sorted(diff["added"]):
                rows_added.append([now_str(), prog, url, atype, ident])
            for ident, atype in sorted(diff["removed"]):
                rows_removed.append([now_str(), prog, url, atype, ident])
        update_excel(xlsx_path, rows_added, rows_removed)
        apply_asset_changes(conn, changes, live_meta)
    else:
        console.print(f"[yellow][{now_str()}] No changes[/yellow]")

# CLI entry
def main():
    parser = argparse.ArgumentParser(description="Watch HackerOne program assets and keep a live Excel of active assets. State is stored in SQLite.")
    parser.add_argument("-o", "--output", default="new_assets.xlsx", help="Output Excel file path (default: new_assets.xlsx)")
    parser.add_argument("--db", default="assets.db", help="SQLite database file (default: assets.db)")
    parser.add_argument("-i", "--interval", type=int, default=60, help="Polling interval in seconds (default: 60)")
    args = parser.parse_args()

    xlsx_path = Path(args.output)
    db_path = Path(args.db)
    interval = max(1, args.interval)

    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        console.print("[cyan]Started. Press Enter to fetch immediately.[/cyan]")

        cur = conn.execute("SELECT COUNT(1) FROM assets").fetchone()
        if cur and cur[0] == 0:
            live = fetch()
            curr_map, meta = build_maps(live)
            for h, (name, url) in meta.items():
                upsert_program(conn, h, name, url)
            for h, aset in curr_map.items():
                for ident, atype in aset:
                    conn.execute("INSERT OR IGNORE INTO assets(handle, asset_identifier, asset_type) VALUES (?, ?, ?)", (h, ident, atype))
            conn.commit()
            console.print("[cyan]Database initialized from live data.[/cyan]")

        while True:
            tick(conn, xlsx_path)
            for _ in range(interval):
                r, _, _ = select.select([sys.stdin], [], [], 1)
                if r:
                    sys.stdin.readline()
                    break
            else:
                continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("[cyan]Exiting...[/cyan]")
