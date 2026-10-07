"""Optional thin live layer: vessel counts for a handful of ports from aisstream.io.

This is deliberately *not* an AIS pipeline. ``ais-listen`` opens the free
aisstream.io WebSocket for a few minutes, keeps the latest position of each
vessel (MMSI) inside each port's bounding box, and appends one row per port per
run to a CSV:

    date, port, vessels, stationary, messages, minutes

``stationary`` (moored / at anchor / SOG <= 0.5 kn) is the closest a snapshot
gets to "ships working the port". Run it at the same UTC time each day (cron)
so the counts are comparable; the CSV then plugs into the catalog as a daily
``csv`` series. It needs ``AISSTREAM_API_KEY`` and ``pip install websockets``.

Coverage of the free feed is terrestrial and uneven, so treat the counts as a
local cross-check on the OECD port-call series, not a replacement for it.
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from . import SourceError

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
POSITION_TYPES = ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport")
STATIONARY_NAV_STATUS = {1, 5}  # 1 = at anchor, 5 = moored
STATIONARY_SOG = 0.5

Box = Tuple[Tuple[float, float], Tuple[float, float]]  # ((lat, lon), (lat, lon)) corners


def _inside(box: Box, lat: float, lon: float) -> bool:
    (a_lat, a_lon), (b_lat, b_lon) = box
    return min(a_lat, b_lat) <= lat <= max(a_lat, b_lat) and min(a_lon, b_lon) <= lon <= max(a_lon, b_lon)


@dataclass
class PortCounter:
    ports: Mapping[str, Box]
    vessels: Dict[str, Dict[int, Tuple[float, int]]] = field(default_factory=dict)
    messages: int = 0

    def subscription(self, api_key: str) -> Dict:
        return {"APIKey": api_key,
                "BoundingBoxes": [[list(c) for c in box] for box in self.ports.values()],
                "FilterMessageTypes": list(POSITION_TYPES)}

    def ingest(self, msg: Mapping) -> Optional[str]:
        """Record one aisstream envelope; returns the port it fell in, if any."""
        mtype = msg.get("MessageType")
        if mtype not in POSITION_TYPES:
            return None
        body = (msg.get("Message") or {}).get(mtype) or {}
        meta = msg.get("MetaData") or {}
        lat = body.get("Latitude", meta.get("latitude"))
        lon = body.get("Longitude", meta.get("longitude"))
        mmsi = body.get("UserID", meta.get("MMSI"))
        if lat is None or lon is None or mmsi is None:
            return None
        self.messages += 1
        for name, box in self.ports.items():
            if _inside(box, float(lat), float(lon)):
                sog = float(body.get("Sog", 0.0) or 0.0)
                nav = int(body.get("NavigationalStatus", 15) if body.get("NavigationalStatus") is not None else 15)
                self.vessels.setdefault(name, {})[int(mmsi)] = (sog, nav)
                return name
        return None

    def summary(self, day: date, minutes: float) -> List[Dict[str, object]]:
        rows = []
        for name in self.ports:
            seen = self.vessels.get(name, {})
            stationary = sum(1 for sog, nav in seen.values() if nav in STATIONARY_NAV_STATUS or sog <= STATIONARY_SOG)
            rows.append({"date": day.isoformat(), "port": name, "vessels": len(seen),
                         "stationary": stationary, "messages": self.messages, "minutes": round(minutes, 1)})
        return rows


def ports_from_config(cfg: Mapping) -> Dict[str, Box]:
    ports = (cfg.get("ais") or {}).get("ports") or {}
    if not ports:
        raise SourceError("no ais.ports in the catalog; add {name: [[lat, lon], [lat, lon]]}")
    if len(ports) > 10:
        raise SourceError("keep the live layer tight: at most 10 ports")
    return {name: (tuple(box[0]), tuple(box[1])) for name, box in ports.items()}


def append_rows(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "port", "vessels", "stationary", "messages", "minutes"])
        if new:
            w.writeheader()
        w.writerows(rows)


async def _listen(counter: PortCounter, api_key: str, seconds: float) -> None:
    try:
        import websockets  # optional dependency
    except ImportError as exc:
        raise SourceError("ais-listen needs `pip install websockets` (or `pip install -e .[ais]`)") from exc
    deadline = time.monotonic() + seconds
    async with websockets.connect(STREAM_URL) as ws:
        await ws.send(json.dumps(counter.subscription(api_key)))
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if "error" in msg:
                raise SourceError(f"aisstream: {msg['error']}")
            counter.ingest(msg)


def listen(ports: Mapping[str, Box], minutes: float, out: Path, api_key: Optional[str] = None) -> List[Dict[str, object]]:
    api_key = api_key or os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        raise SourceError("set AISSTREAM_API_KEY (free key from aisstream.io)")
    counter = PortCounter(ports)
    asyncio.run(_listen(counter, api_key, minutes * 60))
    rows = counter.summary(datetime.now(timezone.utc).date(), minutes)
    append_rows(out, rows)
    return rows
