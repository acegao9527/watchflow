#!/usr/bin/env python3
"""Douban wish-list -> Quark download folders.

Standalone, sanitized version of the Hermes skill script.

What it does:
1. Fetch or load Douban wish-list items.
2. Classify items as movie/show with conservative heuristics.
3. Search a configurable media-resource API for Quark links.
4. Validate Quark share links using the share token API.
5. Save links into Quark `电影下载` / `电视剧下载` folders.
6. Normalize movie folders and single main video/subtitle names.

Secrets are supplied via config file or environment variables. Do not commit config.json.
"""
from __future__ import annotations

import argparse
import dataclasses
import html
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import httpx

try:
    from quark_client import create_client
except Exception:  # pragma: no cover - optional until save mode is used
    create_client = None  # type: ignore[assignment]

VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".webm", ".rmvb"}
SUB_EXT = {".srt", ".ass", ".ssa", ".sub"}
EXCLUDE_WORDS = ["预告", "花絮", "解说", "枪版", "TC", "TS", "CAM", "抢先"]
BAD_MOVIE_NOTE_HINTS = ["短剧", "全集", "美剧", "电视剧", "动画", "动漫", "综艺"]
DEFAULT_CONFIG_PATH = Path.home() / ".config/douban-wish-quark-downloader/config.json"
DEFAULT_CACHE_PATH = Path("/tmp/douban_wish.json")


@dataclasses.dataclass
class Config:
    douban_user_id: str = ""
    quark_cookie: str = ""
    search_endpoint: str = "http://127.0.0.1:8888/api/search"
    movie_folder: str = "电影下载"
    show_folder: str = "电视剧下载"


@dataclasses.dataclass
class WishItem:
    subject_id: str
    title: str
    main_title: str
    url: str
    year: str
    pub: str
    media_type: str

    def folder_name(self) -> str:
        return f"{self.main_title} ({self.year})" if self.year else self.main_title


def load_config(path: Path) -> Config:
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    cfg = Config(
        douban_user_id=os.getenv("DOUBAN_USER_ID", data.get("douban_user_id", "")),
        quark_cookie=os.getenv("QUARK_COOKIE", data.get("quark_cookie", "")),
        search_endpoint=os.getenv("MEDIA_SEARCH_ENDPOINT", data.get("search_endpoint", Config.search_endpoint)),
        movie_folder=data.get("movie_folder", Config.movie_folder),
        show_folder=data.get("show_folder", Config.show_folder),
    )
    return cfg


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\-—_:：·・/\\\[\]【】（）()《》,.，。!！?？+]+", "", s)


def classify_item(title: str, pub: str, year: str) -> str:
    text = f"{title} {pub}"
    if re.search(r"\b\d+\s*集\b|\d+集|全\d+集|每集|单集|电视剧|剧集|连续剧|迷你剧|第[一二三四五六七八九十0-9]+季", text):
        return "show"
    if re.search(r"program\.|/tv/|tvn|netflix|disneyplus|iqiyi|youku|v\.qq|mgtv", pub, re.I):
        return "show"
    m = re.search(r"\b(\d{1,3})(?:-\d{1,3})?\s*分钟", pub)
    if m and int(m.group(1)) <= 80:
        return "show"
    if not year and re.search(r"\b[2345]\d\s*分钟", pub):
        return "show"
    return "movie"


def parse_wish_items_from_html(text: str) -> list[WishItem]:
    """Parse Douban wish page HTML.

    This parser intentionally uses regex to avoid requiring bs4. Douban public pages
    are simple enough for this bounded extraction, but authenticated/private pages may
    need cookies or a custom fetcher.
    """
    items: list[WishItem] = []
    blocks = re.findall(r"<div class=\"item\".*?</li>\s*</ul>", text, flags=re.S)
    if not blocks:
        blocks = re.findall(r"<li.*?</li>", text, flags=re.S)
    for block in blocks:
        href_match = re.search(r"https://movie\.douban\.com/subject/(\d+)/", block)
        title_match = re.search(r"<li class=\"title\">\s*<a[^>]*>\s*<em>(.*?)</em>", block, flags=re.S)
        if not href_match or not title_match:
            continue
        subject_id = href_match.group(1)
        raw_title = html.unescape(re.sub(r"<.*?>", "", title_match.group(1))).strip()
        main_title = raw_title.split("/")[0].strip()
        year = ""
        year_match = re.search(r"\b((?:19|20)\d{2})\b", block)
        if year_match:
            year = year_match.group(1)
        pub = ""
        intro_match = re.search(r"<li class=\"intro\">(.*?)</li>", block, flags=re.S)
        if intro_match:
            pub = html.unescape(re.sub(r"<.*?>", "", intro_match.group(1))).strip()
        media_type = classify_item(raw_title, pub, year)
        items.append(WishItem(subject_id, raw_title, main_title, f"https://movie.douban.com/subject/{subject_id}/", year, pub, media_type))
    return items


def fetch_douban_wish(user_id: str, max_pages: int, cache_path: Path, cookie: str = "") -> list[WishItem]:
    if not user_id:
        raise ValueError("douban_user_id is required; set config.json or DOUBAN_USER_ID")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Referer": "https://movie.douban.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    all_items: list[WishItem] = []
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30) as client:
        for page in range(max_pages):
            start = page * 15
            url = f"https://movie.douban.com/people/{user_id}/wish?start={start}&sort=time&rating=all&filter=all&mode=list"
            r = client.get(url)
            r.raise_for_status()
            items = parse_wish_items_from_html(r.text)
            print(f"[douban] page={page} start={start} items={len(items)}", file=sys.stderr, flush=True)
            if not items:
                break
            all_items.extend(items)
            if len(items) < 15:
                break
            time.sleep(1.0)
    save_cache(all_items, cache_path)
    return all_items


def save_cache(items: Iterable[WishItem], path: Path) -> None:
    data = {"items": [dataclasses.asdict(item) for item in items]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cache(path: Path) -> list[WishItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for raw in data.get("items", []):
        if "main_title" not in raw:
            title = raw.get("title", "")
            raw["main_title"] = title.split("/")[0].strip()
        raw.setdefault("media_type", classify_item(raw.get("title", ""), raw.get("pub", ""), raw.get("year", "")))
        out.append(WishItem(**{k: raw.get(k, "") for k in WishItem.__dataclass_fields__}))
    return out


def list_all(client: Any, fid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client.list_files(fid, page=page, size=200).get("data", {})
        arr = data.get("list", [])
        out.extend(arr)
        if len(arr) < 200:
            return out
        page += 1


def get_target_fid(client: Any, target_folder: str) -> str:
    root = list_all(client, "0")
    target = next((x for x in root if x.get("dir") and x.get("file_name") == target_folder), None)
    if not target:
        raise RuntimeError(f"Quark root folder not found: {target_folder}")
    return target["fid"]


def search_quark(endpoint: str, item: WishItem) -> list[dict[str, Any]]:
    payload = {"kw": item.main_title, "cloud_types": ["quark"], "filter": {"exclude": EXCLUDE_WORDS}}
    with httpx.Client(timeout=30) as client:
        r = client.post(endpoint, json=payload)
        r.raise_for_status()
        data = r.json()
    return data.get("data", {}).get("merged_by_type", {}).get("quark", []) or data.get("data", {}).get("data", {}).get("merged_by_type", {}).get("quark", []) or []


def validate_quark_url(url: str) -> tuple[bool, str]:
    m = re.search(r"pan\.quark\.cn/s/([A-Za-z0-9_-]+)", url or "")
    if not m:
        return False, "not_quark_share"
    pwd_id = m.group(1)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://pan.quark.cn/"}
    try:
        r = httpx.post("https://drive-m.quark.cn/1/clouddrive/share/sharepage/token", json={"pwd_id": pwd_id, "passcode": ""}, timeout=30, headers=headers)
        data = r.json()
    except Exception as exc:
        return False, f"validation_error:{type(exc).__name__}"
    ok = r.status_code == 200 and data.get("status") == 200 and data.get("code") == 0 and data.get("data", {}).get("stoken")
    return bool(ok), "ok" if ok else f"invalid_share:{data.get('message') or data.get('code')}"


def candidate_score(item: WishItem, cand: dict[str, Any]) -> int:
    note = cand.get("note") or cand.get("title") or ""
    nt, nn = normalize_text(item.main_title), normalize_text(note)
    if not nt or nt not in nn:
        return -100
    compact_extra = nn.replace(nt, "", 1)
    exactish = nn == nt or (item.main_title in note and len(compact_extra) <= 8)
    has_year = bool(item.year and item.year in note)
    if item.media_type == "movie" and not (has_year or exactish):
        return -80
    if item.media_type == "movie" and any(h in note for h in BAD_MOVIE_NOTE_HINTS) and not has_year:
        return -50
    score = 10
    if exactish:
        score += 15
    if item.main_title in note:
        score += 10
    if has_year:
        score += 10
    if item.media_type == "show" and any(h in note for h in ["全集", "全", "电视剧", "美剧", "Season", "season"]):
        score += 5
    return score


def choose_candidate(endpoint: str, item: WishItem) -> tuple[dict[str, Any] | None, str]:
    try:
        ranked = sorted(search_quark(endpoint, item), key=lambda c: candidate_score(item, c), reverse=True)
    except Exception as exc:
        return None, f"search_error:{type(exc).__name__}"
    for cand in ranked:
        if candidate_score(item, cand) < 0:
            continue
        ok, why = validate_quark_url(cand.get("url") or "")
        if ok:
            return cand, "ok"
    return None, "no_verified_candidate"


def extract_saved_fids(res: dict[str, Any]) -> list[str]:
    for path in (["task_result", "data", "save_as", "save_as_top_fids"], ["data", "task_resp", "data", "save_as", "save_as_top_fids"]):
        cur: Any = res
        for key in path:
            cur = cur.get(key, {}) if isinstance(cur, dict) else {}
        if isinstance(cur, list) and cur:
            return cur
    return []


def normalize_inside_movie_folder(client: Any, folder_fid: str, base: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    files = [x for x in list_all(client, folder_fid) if not x.get("dir")]
    videos = [f for f in files if os.path.splitext(f.get("file_name", ""))[1].lower() in VIDEO_EXT]
    subs = [f for f in files if os.path.splitext(f.get("file_name", ""))[1].lower() in SUB_EXT]
    for group, typ in ((videos, "video"), (subs, "subtitle")):
        if len(group) == 1:
            old = group[0]["file_name"]
            ext = os.path.splitext(old)[1]
            new = f"{base}{ext}"
            if old != new:
                try:
                    res = client.rename_file(group[0]["fid"], new)
                    changes.append({"type": typ, "old": old, "new": new, "code": res.get("code")})
                except Exception as exc:
                    changes.append({"type": typ, "old": old, "new": new, "error": type(exc).__name__})
        elif typ == "video" and len(group) > 1:
            changes.append({"type": "skip", "reason": "multiple_video_variants", "files": [v.get("file_name") for v in group]})
    return changes


def run(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_config(Path(args.config))
    if args.douban_user_id:
        cfg.douban_user_id = args.douban_user_id
    if args.search_endpoint:
        cfg.search_endpoint = args.search_endpoint
    cache_path = Path(args.cache)

    if args.use_existing:
        items = load_cache(cache_path)
    else:
        items = fetch_douban_wish(cfg.douban_user_id, args.max_pages, cache_path, args.douban_cookie or os.getenv("DOUBAN_COOKIE", ""))

    if args.dry_run:
        return {"mode": "dry_run", "total": len(items), "sample": [dataclasses.asdict(x) for x in items[: args.count]]}

    if create_client is None:
        raise RuntimeError("quark_client is required for saving; install requirements.txt")
    if not cfg.quark_cookie:
        raise ValueError("quark_cookie is required; set config.json or QUARK_COOKIE")
    client = create_client(cookies=cfg.quark_cookie, auto_login=False)
    target_fid_by_type = {"movie": get_target_fid(client, cfg.movie_folder), "show": get_target_fid(client, cfg.show_folder)}
    existing_by_type = {"movie": {x.get("file_name") for x in list_all(client, target_fid_by_type["movie"])}, "show": {x.get("file_name") for x in list_all(client, target_fid_by_type["show"])}}

    saved_count = 0
    results: list[dict[str, Any]] = []
    matching_index = 0
    for item in items:
        if args.media_type != "all" and item.media_type != args.media_type:
            continue
        if matching_index < args.start_index:
            matching_index += 1
            continue
        matching_index += 1
        if saved_count >= args.count:
            break
        base = item.folder_name()
        if base in existing_by_type[item.media_type]:
            results.append({"title": item.main_title, "media_type": item.media_type, "action": "skip_exists", "folder": base})
            continue
        print(f"[{matching_index}/{len(items)}] search {item.media_type}: {base}", file=sys.stderr, flush=True)
        cand, why = choose_candidate(cfg.search_endpoint, item)
        if not cand:
            results.append({"title": item.main_title, "media_type": item.media_type, "action": "no_resource", "reason": why})
            continue
        res = client.save_shared_files(cand["url"], target_folder_id=target_fid_by_type[item.media_type], wait_for_completion=True, timeout=args.timeout)
        fids = extract_saved_fids(res)
        per = []
        for i, fid in enumerate(fids, 1):
            name = base if len(fids) == 1 else f"{base} - {i}"
            try:
                rr = client.rename_file(fid, name)
                rename_code = rr.get("code")
            except Exception as exc:
                rename_code = f"rename_error:{type(exc).__name__}"
            changes = normalize_inside_movie_folder(client, fid, name) if item.media_type == "movie" else []
            per.append({"fid": fid, "folder": name, "rename_code": rename_code, "file_changes": changes})
        saved_count += 1
        existing_by_type[item.media_type].add(base)
        results.append({"title": item.main_title, "media_type": item.media_type, "action": "saved", "url": cand.get("url"), "note": cand.get("note"), "folders": per})
    return {"saved_count": saved_count, "processed_results": len(results), "results": results}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--douban-user-id", default="")
    ap.add_argument("--douban-cookie", default="")
    ap.add_argument("--search-endpoint", default="")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    ap.add_argument("--use-existing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=5)
    ap.add_argument("--media-type", choices=["all", "movie", "show"], default="all")
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
