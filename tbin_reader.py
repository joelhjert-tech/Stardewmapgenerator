#!/usr/bin/env python3
"""
tbin_reader.py - minimal, validated reader for tIDE 'tBIN10' binary maps.

Used to extract AUTHORITATIVE vanilla tile usage + tile properties from the
unpacked base-game maps. Read-only.

The parser self-validates: every layer must consume exactly width*height tiles and
the whole file must be consumed. Callers should assert .ok.
"""
import struct, io


class TbinError(Exception):
    pass


class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0
        self.n = len(data)

    def bytes(self, k):
        if self.i + k > self.n:
            raise TbinError(f"EOF reading {k} bytes at {self.i}")
        b = self.d[self.i:self.i + k]
        self.i += k
        return b

    def u8(self):
        return self.bytes(1)[0]

    def i32(self):
        return struct.unpack("<i", self.bytes(4))[0]

    def f32(self):
        return struct.unpack("<f", self.bytes(4))[0]

    def string(self):
        ln = self.i32()
        if ln < 0 or self.i + ln > self.n:
            raise TbinError(f"bad string len {ln} at {self.i}")
        return self.bytes(ln).decode("utf-8", "replace")


def read_properties(r):
    """PropertyList: int32 count, then key:String + typed value."""
    props = {}
    count = r.i32()
    if count < 0 or count > 100000:
        raise TbinError(f"insane property count {count}")
    for _ in range(count):
        key = r.string()
        t = r.u8()
        if t == 0:      # bool
            val = bool(r.u8())
        elif t == 1:    # int32
            val = r.i32()
        elif t == 2:    # float
            val = r.f32()
        elif t == 3:    # string
            val = r.string()
        else:
            raise TbinError(f"unknown property type {t} for key {key!r}")
        props[key] = val
    return props


def read_tilesheet(r):
    ts = {}
    ts["id"] = r.string()
    ts["description"] = r.string()
    ts["imageSource"] = r.string()
    ts["sheetSize"] = (r.i32(), r.i32())   # in tiles (w,h)
    ts["tileSize"] = (r.i32(), r.i32())     # in px
    ts["margin"] = (r.i32(), r.i32())
    ts["spacing"] = (r.i32(), r.i32())
    ts["properties"] = read_properties(r)
    return ts


def read_tile_in_layer(r, state):
    """Read one tile command; returns (kind, advance, payload).
    state holds 'sheet' (current tilesheet id)."""
    cmd = chr(r.u8())
    if cmd == "N":           # null run
        cnt = r.i32()
        return ("null", cnt, None)
    if cmd == "T":           # tilesheet change (no advance)
        state["sheet"] = r.string()
        return ("sheet", 0, None)
    if cmd == "S":           # static tile
        idx = r.i32()
        # static tiles carry a 1-byte blend-mode flag, then a per-tile property list
        r.u8()               # blend mode (unused)
        props = read_properties(r)   # per-tile properties (usually empty)
        return ("static", 1, (state["sheet"], idx, props))
    if cmd == "A":           # animated tile
        interval = r.i32()   # frame interval (ms)
        frame_count = r.i32()
        first = None
        for _ in range(frame_count):
            sub = chr(r.u8())
            if sub == "T":
                state["sheet"] = r.string()
                sub = chr(r.u8())
            if sub == "S":
                fidx = r.i32()
                r.u8()
                props = read_properties(r)
                if first is None:
                    first = (state["sheet"], fidx, props)
            else:
                raise TbinError(f"unexpected anim frame cmd {sub!r}")
        own_props = read_properties(r)   # animated tile's own properties
        if first is not None and own_props:
            first = (first[0], first[1], own_props)
        return ("animated", 1, first)
    raise TbinError(f"unknown tile cmd {cmd!r} ({ord(cmd)}) at {r.i}")


def read_layer(r):
    layer = {}
    layer["id"] = r.string()
    layer["visible"] = bool(r.u8())
    layer["description"] = r.string()
    layer["layerSize"] = (r.i32(), r.i32())   # tiles (w,h)
    layer["tileSize"] = (r.i32(), r.i32())     # px
    layer["properties"] = read_properties(r)
    w, h = layer["layerSize"]
    if not (0 < w <= 10000 and 0 < h <= 10000):
        raise TbinError(f"insane layer size {w}x{h}")
    tiles = {}   # (x,y) -> (sheetId, index)
    tile_properties = {}   # (x,y) -> per-placement properties
    state = {"sheet": None}
    for y in range(h):
        x = 0
        while x < w:
            kind, adv, payload = read_tile_in_layer(r, state)
            if kind == "null":
                x += adv
            elif kind == "sheet":
                pass
            else:  # static / animated
                if payload is not None:
                    sheet_id, idx = payload[0], payload[1]
                    props = payload[2] if len(payload) > 2 and payload[2] else {}
                    tiles[(x, y)] = (sheet_id, idx)
                    if props:
                        tile_properties[(x, y)] = props
                x += adv
            if x > w:
                raise TbinError(f"layer {layer['id']} row {y} overran width ({x}>{w})")
    layer["tiles"] = tiles
    layer["tileProperties"] = tile_properties
    return layer


def parse(data):
    r = Reader(data)
    if r.bytes(6) != b"tBIN10":
        raise TbinError("bad magic (not tBIN10)")
    m = {}
    m["id"] = r.string()
    m["description"] = r.string()
    m["properties"] = read_properties(r)
    nts = r.i32()
    if not (0 <= nts <= 1000):
        raise TbinError(f"insane tilesheet count {nts}")
    m["tilesheets"] = [read_tilesheet(r) for _ in range(nts)]
    nl = r.i32()
    if not (0 <= nl <= 1000):
        raise TbinError(f"insane layer count {nl}")
    m["layers"] = [read_layer(r) for _ in range(nl)]
    # consumption check (allow trailing padding of zero bytes)
    trailing = r.d[r.i:]
    m["bytesConsumed"] = r.i
    m["bytesTotal"] = r.n
    m["fullyConsumed"] = all(b == 0 for b in trailing)
    m["trailingBytes"] = len(trailing)
    m["ok"] = m["fullyConsumed"]
    return m


if __name__ == "__main__":
    import sys
    mp = parse(open(sys.argv[1], "rb").read())
    print("id:", mp["id"], "| ok:", mp["ok"], "| consumed", mp["bytesConsumed"], "/", mp["bytesTotal"],
          "| trailing", mp["trailingBytes"])
    print("tilesheets:")
    for ts in mp["tilesheets"]:
        print("  ", ts["id"], "->", ts["imageSource"], "sheet", ts["sheetSize"], "tile", ts["tileSize"],
              "props", list(ts["properties"].keys())[:5])
    print("layers:")
    for ly in mp["layers"]:
        print("  ", ly["id"], ly["layerSize"], "placed tiles:", len(ly["tiles"]),
              "props", list(ly["properties"].keys())[:5])
