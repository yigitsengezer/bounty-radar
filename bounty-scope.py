#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, select, argparse, requests, pandas as pd, sqlite3
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box

HACKERONE_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/hackerone_data.json"
BUGCROWD_URL  = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/bugcrowd_data.json"
INTIGRITI_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/intigriti_data.json"
YESWEHACK_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/yeswehack_data.json"
FEDERACY_URL  = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/refs/heads/main/data/federacy_data.json"
REQUEST_TIMEOUT = 30

COLUMNS = ["Timestamp", "Program", "Program URL", "Asset Type", "Asset"]
console = Console()

def now_str():
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def fetch_json(url: str):
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def build_maps_hackerone(data):
    inscope, meta = {}, {}
    for p in data:
        handle = (p.get("handle") or p.get("name") or "").strip()
        if not handle: continue
        key = f"h1:{handle}"
        name = (p.get("name") or handle).strip()
        url  = (p.get("url") or "").strip()
        meta[key] = (name, url)
        aset=set()
        for t in (p.get("targets",{}) or {}).get("in_scope",[]) or []:
            ident=(t.get("asset_identifier") or "").strip()
            atype=(t.get("asset_type") or "").strip()
            if ident: aset.add((ident, atype))
        inscope[key]=aset
    return inscope, meta

def build_maps_bugcrowd(data):
    inscope, meta = {}, {}
    for p in data:
        name = (p.get("name") or "").strip()
        if not name: continue
        key=f"bc:{name}"
        url=(p.get("url") or "").strip()
        meta[key]=(name,url)
        aset=set()
        for t in (p.get("targets",{}) or {}).get("in_scope",[]) or []:
            ident=(t.get("target") or "").strip()
            atype=(t.get("type") or "").strip()
            if ident: aset.add((ident, atype))
        inscope[key]=aset
    return inscope, meta

def build_maps_intigriti(data):
    inscope, meta = {}, {}
    for p in data:
        pid=(p.get("id") or "").strip()
        name=(p.get("name") or "").strip()
        if not pid or not name: continue
        key=f"ig:{pid}"
        url=(p.get("url") or "").strip()
        meta[key]=(name,url)
        aset=set()
        for t in (p.get("targets",{}) or {}).get("in_scope",[]) or []:
            ident=(t.get("endpoint") or "").strip()
            atype=(t.get("type") or "").strip()
            if ident: aset.add((ident, atype))
        inscope[key]=aset
    return inscope, meta

def build_maps_yeswehack(data):
    inscope, meta = {}, {}
    for p in data:
        pid=(p.get("id") or "").strip()
        name=(p.get("name") or "").strip()
        if not pid or not name: continue
        key=f"ywh:{pid}"
        url=(p.get("url") or "").strip()
        meta[key]=(name,url)
        aset=set()
        for t in (p.get("targets",{}) or {}).get("in_scope",[]) or []:
            ident=(t.get("target") or "").strip()
            atype=(t.get("type") or "").strip()
            if ident: aset.add((ident, atype))
        inscope[key]=aset
    return inscope, meta

def build_maps_federacy(data):
    inscope, meta = {}, {}
    for p in data:
        pid=(p.get("id") or "").strip()
        name=(p.get("name") or "").strip()
        if not pid or not name: continue
        key=f"fd:{pid}"
        url=(p.get("url") or "").strip()
        meta[key]=(name,url)
        aset=set()
        for t in (p.get("targets",{}) or {}).get("in_scope",[]) or []:
            ident=(t.get("target") or "").strip()
            atype=(t.get("type") or "").strip()
            if ident: aset.add((ident, atype))
        inscope[key]=aset
    return inscope, meta

def build_maps_combined(h1, bc, ig, ywh, fd):
    h1_map,h1_meta=build_maps_hackerone(h1)
    bc_map,bc_meta=build_maps_bugcrowd(bc)
    ig_map,ig_meta=build_maps_intigriti(ig)
    ywh_map,ywh_meta=build_maps_yeswehack(ywh)
    fd_map,fd_meta=build_maps_federacy(fd)
    inscope={**h1_map,**bc_map,**ig_map,**ywh_map,**fd_map}
    meta={**h1_meta,**bc_meta,**ig_meta,**ywh_meta,**fd_meta}
    return inscope,meta

def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS programs (
        key TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS assets (
        key TEXT NOT NULL, asset_identifier TEXT NOT NULL, asset_type TEXT NOT NULL,
        PRIMARY KEY (key,asset_identifier,asset_type),
        FOREIGN KEY (key) REFERENCES programs(key) ON DELETE CASCADE)""")
    conn.commit()

def db_snapshot(conn):
    snap={}
    for key,ident,atype in conn.execute("SELECT key,asset_identifier,asset_type FROM assets"):
        snap.setdefault(key,set()).add((ident,atype))
    return snap

def db_meta(conn):
    meta={}
    for key,name,url in conn.execute("SELECT key,name,url FROM programs"):
        meta[key]=(name,url)
    return meta

def upsert_program(conn,key,name,url):
    conn.execute("""INSERT INTO programs(key,name,url) VALUES (?,?,?)
        ON CONFLICT(key) DO UPDATE SET name=excluded.name,url=excluded.url""",(key,name,url))

def apply_asset_changes(conn,changes,meta_live):
    for key,diff in changes.items():
        name,url=meta_live.get(key,(key,""))
        upsert_program(conn,key,name,url)
        for ident,atype in diff.get("added",set()):
            conn.execute("INSERT OR IGNORE INTO assets(key,asset_identifier,asset_type) VALUES (?,?,?)",(key,ident,atype))
        for ident,atype in diff.get("removed",set()):
            conn.execute("DELETE FROM assets WHERE key=? AND asset_identifier=? AND asset_type=?",(key,ident,atype))
    conn.commit()

def detect_changes(prev,curr):
    changes={}
    for k in set(prev.keys())|set(curr.keys()):
        a,b=prev.get(k,set()),curr.get(k,set())
        add,rem=b-a,a-b
        if add or rem: changes[k]={"added":add,"removed":rem}
    return changes

def render_console(changes,meta):
    table=Table(box=box.SIMPLE_HEAVY)
    table.add_column("Change",style="bold")
    table.add_column("Program",style="cyan",no_wrap=True)
    table.add_column("Program URL",style="cyan")
    table.add_column("Asset Type",style="magenta",no_wrap=True)
    table.add_column("Asset",style="white")
    for key,diff in sorted(changes.items()):
        prog,url=meta.get(key,(key,""))
        for ident,atype in sorted(diff["added"]):
            table.add_row("[green]Added[/green]",prog,url,atype or "-",ident)
        for ident,atype in sorted(diff["removed"]):
            table.add_row("[red]Removed[/red]",prog,url,atype or "-",ident)
    console.print(f"[bold magenta][{now_str()}] Changes detected[/bold magenta]")
    console.print(table)

def ensure_excel(path: Path):
    if not path.exists():
        pd.DataFrame(columns=COLUMNS).to_excel(path,index=False)

def update_excel(path: Path,added,removed):
    ensure_excel(path)
    df=pd.read_excel(path,dtype=str).fillna("")
    if not df.empty: df=df[COLUMNS]
    else: df=pd.DataFrame(columns=COLUMNS)
    if removed:
        rem=pd.DataFrame(removed,columns=COLUMNS)
        for _,r in rem.iterrows():
            mask=(df["Program"]==r["Program"])&(df["Program URL"]==r["Program URL"])&(df["Asset Type"]==r["Asset Type"])&(df["Asset"]==r["Asset"])
            df=df.loc[~mask]
    if added:
        add=pd.DataFrame(added,columns=COLUMNS)
        for _,r in add.iterrows():
            mask=(df["Program"]==r["Program"])&(df["Program URL"]==r["Program URL"])&(df["Asset Type"]==r["Asset Type"])&(df["Asset"]==r["Asset"])
            if not df.loc[mask].any().any():
                df=pd.concat([df,pd.DataFrame([r])],ignore_index=True)
    df.to_excel(path,index=False)

def tick(conn,xlsx_path: Path):
    h1=fetch_json(HACKERONE_URL)
    bc=fetch_json(BUGCROWD_URL)
    ig=fetch_json(INTIGRITI_URL)
    ywh=fetch_json(YESWEHACK_URL)
    fd=fetch_json(FEDERACY_URL)
    curr,live_meta=build_maps_combined(h1,bc,ig,ywh,fd)
    prev=db_snapshot(conn); prev_meta=db_meta(conn)
    meta={**prev_meta,**live_meta}
    changes=detect_changes(prev,curr)
    if changes:
        render_console(changes,meta)
        rows_add,rows_rem=[],[]
        for key,diff in sorted(changes.items()):
            prog,url=meta.get(key,(key,""))
            for ident,atype in sorted(diff["added"]):
                rows_add.append([now_str(),prog,url,atype,ident])
            for ident,atype in sorted(diff["removed"]):
                rows_rem.append([now_str(),prog,url,atype,ident])
        update_excel(xlsx_path,rows_add,rows_rem)
        apply_asset_changes(conn,changes,live_meta)
    else:
        console.print(f"[yellow][{now_str()}] No changes[/yellow]")

def main():
    parser=argparse.ArgumentParser(description="Track Bug Bounty scopes (HackerOne + Bugcrowd + Intigriti + YesWeHack + Federacy). Keeps Excel of active assets; state in SQLite.")
    parser.add_argument("-o","--output",default="new_assets.xlsx",help="Excel output file (default new_assets.xlsx)")
    parser.add_argument("--db",default="assets.db",help="SQLite DB file (default assets.db)")
    parser.add_argument("-i","--interval",type=int,default=60,help="Interval seconds (default 60)")
    args=parser.parse_args()
    xlsx_path=Path(args.output); db_path=Path(args.db); interval=max(1,args.interval)
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        console.print("[cyan]Started. Press Enter to fetch immediately.[/cyan]")
        if conn.execute("SELECT COUNT(1) FROM assets").fetchone()[0]==0:
            h1=fetch_json(HACKERONE_URL); bc=fetch_json(BUGCROWD_URL); ig=fetch_json(INTIGRITI_URL); ywh=fetch_json(YESWEHACK_URL); fd=fetch_json(FEDERACY_URL)
            curr,meta=build_maps_combined(h1,bc,ig,ywh,fd)
            for key,(name,url) in meta.items():
                conn.execute("INSERT OR IGNORE INTO programs(key,name,url) VALUES (?,?,?)",(key,name,url))
            for key,aset in curr.items():
                for ident,atype in aset:
                    conn.execute("INSERT OR IGNORE INTO assets(key,asset_identifier,asset_type) VALUES (?,?,?)",(key,ident,atype))
            conn.commit()
            console.print("[cyan]Database initialized from live data.[/cyan]")
        while True:
            tick(conn,xlsx_path)
            for _ in range(interval):
                r,_,_=select.select([sys.stdin],[],[],1)
                if r:
                    sys.stdin.readline()
                    break
            else: continue

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: console.print("[cyan]Exiting...[/cyan]")
