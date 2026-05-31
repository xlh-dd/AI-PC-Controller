#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File Manager MCP Server - intelligent file organization"""
import json, os, shutil, hashlib, time
from pathlib import Path
from collections import defaultdict
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("file-manager-server")

EXT_MAP = {
    "images": [".jpg",".jpeg",".png",".gif",".bmp",".ico",".webp",".svg",".tiff"],
    "documents": [".pdf",".doc",".docx",".txt",".md",".rtf",".csv",".xls",".xlsx",".ppt",".pptx"],
    "videos": [".mp4",".avi",".mkv",".mov",".wmv",".flv",".webm"],
    "audio": [".mp3",".wav",".flac",".aac",".ogg",".wma"],
    "archives": [".zip",".rar",".7z",".tar",".gz",".bz2"],
    "code": [".py",".js",".ts",".html",".css",".cpp",".c",".java",".go",".rs",".json",".xml",".yaml",".yml",".toml"],
    "executables": [".exe",".msi",".bat",".cmd",".ps1",".sh"],
}

def _fmt_size(b):
    for u in ["B","KB","MB","GB","TB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024

def _file_hash(fp, algo="md5"):
    h = hashlib.new(algo)
    with open(fp, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest()

def _classify(name):
    for cat, exts in EXT_MAP.items():
        if Path(name).suffix.lower() in exts:
            return cat
    return "others"

@mcp.tool()
def file_disk_usage(path: str = "C:\\") -> str:
    """Get disk usage statistics"""
    try:
        total, used, free = shutil.disk_usage(path)
        pct = used / total * 100
        return json.dumps({"total": _fmt_size(total), "used": _fmt_size(used),
                           "free": _fmt_size(free), "percent_used": f"{pct:.1f}%"})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def file_scan_large(path: str, min_size_mb: int = 100, limit: int = 20, recursive: bool = True) -> str:
    """Find large files in directory"""
    base = Path(path).expanduser().resolve()
    if not base.exists():
        return json.dumps({"error": f"Path not found: {base}"})
    min_size = min_size_mb * 1048576
    files = []
    pat = "**/*" if recursive else "*"
    for fp in base.glob(pat):
        if fp.is_file():
            try:
                sz = fp.stat().st_size
                if sz >= min_size:
                    files.append({"path": str(fp), "size": _fmt_size(sz), "size_bytes": sz})
            except Exception:
                pass
    files.sort(key=lambda x: x["size_bytes"], reverse=True)
    files = files[:limit]
    return json.dumps({"large_files": files, "count": len(files),
                       "total_size": _fmt_size(sum(f["size_bytes"] for f in files))})

@mcp.tool()
def file_scan_temp(path: str, recursive: bool = True) -> str:
    """Find temporary/junk files"""
    base = Path(path).expanduser().resolve()
    temp_exts = {".tmp",".temp",".bak",".~",".swp",".dmp",".cache",".log"}
    pat = "**/*" if recursive else "*"
    files = []
    for fp in base.glob(pat):
        if fp.is_file() and (fp.suffix.lower() in temp_exts or fp.name.lower() in {"thumbs.db","desktop.ini","~$"}):
            try:
                sz = fp.stat().st_size
                files.append({"path": str(fp), "size": _fmt_size(sz)})
            except Exception:
                pass
    return json.dumps({"temp_files": files[:100], "count": len(files),
                       "total_size": _fmt_size(sum(f["size_bytes"] if "size_bytes" in f else 0 for f in files))})

@mcp.tool()
def file_find_duplicates(path: str, min_size_mb: int = 1, recursive: bool = True) -> str:
    """Find duplicate files by content hash"""
    base = Path(path).expanduser().resolve()
    min_size = min_size_mb * 1048576
    hash_map = defaultdict(list)
    pat = "**/*" if recursive else "*"
    scanned = 0
    for fp in base.glob(pat):
        if fp.is_file():
            try:
                sz = fp.stat().st_size
                if sz >= min_size:
                    hash_map[sz].append(fp)
                    scanned += 1
            except Exception:
                pass
    dups = []
    wasted = 0
    for sz, paths in hash_map.items():
        if len(paths) > 1:
            ch = defaultdict(list)
            for p in paths:
                try:
                    ch[_file_hash(str(p))].append(str(p))
                except Exception:
                    pass
            for h, plist in ch.items():
                if len(plist) > 1:
                    dups.append({"size": _fmt_size(sz), "files": plist})
                    wasted += sz * (len(plist) - 1)
    return json.dumps({"duplicate_groups": len(dups), "wasted_size": _fmt_size(wasted),
                       "scanned": scanned, "duplicates": dups[:50]})

@mcp.tool()
def file_sort_by_type(path: str, dry_run: bool = True) -> str:
    """Sort files into type-category subdirectories (images, documents, videos, etc.)"""
    base = Path(path).expanduser().resolve()
    moves = []
    for fp in base.iterdir():
        if fp.is_file():
            cat = _classify(fp.name)
            if cat != "others":
                moves.append({"file": fp.name, "category": cat})
    if not dry_run and moves:
        for m in moves:
            dest = base / m["category"] / m["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(base / m["file"]), str(dest))
    return json.dumps({"dry_run": dry_run, "files_to_sort": len(moves)})

@mcp.tool()
def file_batch_rename(path: str, pattern: str, format_str: str = "", dry_run: bool = True) -> str:
    """Batch rename files matching glob pattern. format: {n}=number, {name}=original name"""
    base = Path(path).expanduser().resolve()
    renames = []
    for i, fp in enumerate(sorted(base.glob(pattern))):
        if fp.is_file():
            new = (format_str.replace("{n}", str(i+1)).replace("{name}", fp.stem)
                   if format_str else fp.name)
            base_name = new if "." in new else new + fp.suffix
            renames.append({"old": fp.name, "new": base_name})
            if not dry_run:
                fp.rename(fp.parent / base_name)
    return json.dumps({"dry_run": dry_run, "count": len(renames), "renames": renames[:100]})

@mcp.tool()
def file_search(path: str, pattern: str, recursive: bool = True, limit: int = 50) -> str:
    """Search files by name pattern"""
    base = Path(path).expanduser().resolve()
    results = []
    pat = f"**/*{pattern}*" if recursive else f"*{pattern}*"
    for fp in base.glob(pat):
        if fp.is_file() and len(results) < limit:
            results.append({"name": fp.name, "path": str(fp), "size": _fmt_size(fp.stat().st_size), "ext": fp.suffix})
    return json.dumps({"query": pattern, "results": results, "found": len(results)})

@mcp.tool()
def file_info(path: str) -> str:
    """Get detailed file/folder info"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return json.dumps({"error": "Not found"})
    if p.is_dir():
        files = sum(1 for x in p.iterdir() if x.is_file())
        dirs = sum(1 for x in p.iterdir() if x.is_dir())
        return json.dumps({"type": "directory", "path": str(p), "files": files, "subdirs": dirs})
    st = p.stat()
    return json.dumps({"type": "file", "name": p.name, "ext": p.suffix,
                       "size": _fmt_size(st.st_size), "size_bytes": st.st_size,
                       "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))})

@mcp.tool()
def file_organize(path: str, dry_run: bool = True) -> str:
    """Intelligent organization: classify + detect duplicates in one pass"""
    p = Path(path).expanduser().resolve()
    categorized = sum(1 for x in p.iterdir() if x.is_file() and _classify(x.name) != "others")
    # Quick dedup scan (>1MB files)
    hash_map = defaultdict(list)
    for fp in p.iterdir():
        if fp.is_file() and fp.stat().st_size > 1048576:
            hash_map[fp.stat().st_size].append(fp)
    dup_count = 0
    for paths in hash_map.values():
        if len(paths) > 1:
            ch = defaultdict(list)
            for fp in paths:
                try:
                    ch[_file_hash(str(fp))].append(str(fp))
                except Exception:
                    pass
            for plist in ch.values():
                if len(plist) > 1:
                    dup_count += len(plist) - 1
    return json.dumps({"path": str(p), "dry_run": dry_run,
                       "categorizable": categorized, "potential_duplicates": dup_count})

if __name__ == "__main__":
    mcp.run(transport="stdio")