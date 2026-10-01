"""Live mode: fetch every enabled series from its publisher into a live cache, with a manifest.

Live and synthetic data never share a cache: ``fetch`` refuses a directory that
holds demo data, and ``demo`` refuses one that holds a live manifest. The
manifest records, per series, when it was fetched, from where, and what came
back, so every output can say how fresh each input is.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .catalog import enabled_series
from .demo import MARKER
from .series import Series
from .sources import SourceError, fetch_series, write_cache

MANIFEST = "_manifest.json"


def read_manifest(cache_dir: Path) -> Dict[str, Any]:
    path = Path(cache_dir) / MANIFEST
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_all(cfg: Mapping[str, Any], cache_dir: Path, only: Optional[List[str]] = None,
              log=print) -> Dict[str, Any]:
    """Fetch enabled series into ``cache_dir``; returns the updated manifest.

    A failed fetch keeps the previously cached file (if any) and records the
    error, so one publisher being down does not blank the nowcast.
    """
    cache_dir = Path(cache_dir)
    if (cache_dir / MARKER).exists():
        raise SourceError(f"{cache_dir} holds synthetic demo data; use a separate cache for live data")
    base = Path(cfg.get("_base_dir", "."))
    manifest = read_manifest(cache_dir)
    series = manifest.setdefault("series", {})
    for spec in enabled_series(cfg):
        sid = spec["id"]
        if only and sid not in only:
            continue
        entry: Dict[str, Any] = {"source": spec.get("source"), "attempted_at": _now(),
                                 "optional": bool(spec.get("optional"))}
        try:
            s: Series = fetch_series(spec, base)
        except SourceError as exc:
            prev = series.get(sid, {})
            entry.update(status="failed", error=str(exc),
                         last_good_fetch=prev.get("fetched_at") or prev.get("last_good_fetch"),
                         last=prev.get("last"), observations=prev.get("observations"))
            series[sid] = entry
            log(f"  {'skip' if spec.get('optional') else 'FAIL'} {sid}: {exc}")
            continue
        write_cache(cache_dir, s)
        entry.update(status="ok", fetched_at=entry["attempted_at"], observations=len(s.observations),
                     first=s.observations[0][0].isoformat(), last=s.last_date.isoformat(),
                     origin=s.source, details={k: str(v) for k, v in s.meta.items()})
        series[sid] = entry
        log(f"  ok   {sid}: {len(s.observations)} obs {entry['first']} .. {entry['last']}  ({s.source})")
    enabled = {s["id"] for s in enabled_series(cfg)}
    for sid in [k for k in series if k not in enabled]:
        del series[sid]  # switched off in the catalog
    manifest["updated_at"] = _now()
    manifest["mode"] = "live"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def required_failures(cfg: Mapping[str, Any], manifest: Mapping[str, Any]) -> List[str]:
    entries = manifest.get("series", {})
    return [s["id"] for s in enabled_series(cfg)
            if not s.get("optional") and entries.get(s["id"], {}).get("status") != "ok"]


def probe(cfg: Mapping[str, Any], only: Optional[List[str]] = None, log=print) -> int:
    """Try every enabled source without touching the cache; print what came back.

    For GENESIS tables it also prints the table's variables and attribute codes,
    which is what you need to fix a filter that matched nothing.
    """
    from .sources import genesis

    base = Path(cfg.get("_base_dir", "."))
    bad = 0
    for spec in enabled_series(cfg):
        sid = spec["id"]
        if only and sid not in only:
            continue
        log(f"== {sid} [{spec.get('source')}]")
        try:
            s = fetch_series(spec, base)
            tail = ", ".join(f"{d.isoformat()}={v:g}" for d, v in s.observations[-3:])
            log(f"   ok: {len(s.observations)} obs {s.observations[0][0]} .. {s.last_date}; last: {tail}")
            for k, v in s.meta.items():
                log(f"   {k}: {v}")
        except SourceError as exc:
            bad += not spec.get("optional")
            log(f"   {'skip' if spec.get('optional') else 'FAIL'}: {exc}")
        if spec.get("source") == "genesis":
            try:
                client = genesis.GenesisClient.from_env()
                params = spec.get("params", {})
                text = client.tablefile(params["table"], startyear=params.get("startyear"))
                info = genesis.inspect_ffcsv(text)
                log(f"   table {params['table']}: {info['rows']} rows, time {info['time']}")
                log("   header: " + text.splitlines()[0][:400])
                for code, attrs in info["variables"].items():
                    shown = ", ".join(f"{a}={l}" for a, l in list(attrs.items())[:12])
                    log(f"   variable {code}: {shown}")
                for m in info["measures"][:12]:
                    log(f"   measure {m}")
            except (SourceError, KeyError, IndexError) as exc:
                log(f"   inspect failed: {exc}")
    return bad
