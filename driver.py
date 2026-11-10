#!/usr/bin/env python3
"""Super Over on-device auto-play driver v2 (no changes to the game needed).

Drives one seeded session on a booted emulator through plain adb:
  - reads the screen with `uiautomator dump` (built into every Android device)
  - acts with `input tap` / `input swipe` (two quick taps = activate, matching
    the game's gestures-mode TalkBack-OFF semantics)
  - feature coverage: deterministic mini-tours reach the big features
    (quick T20, ODI setup, gesture guide drills, What's New, settings toggle),
    and COVER events fire the first time each known feature screen appears
  - visual capture: a labelled screenshot on the first sighting of every
    feature screen, plus periodic shots and shots on every event
  - detects: CRASH (process gone), STALL (screen unchanged for many polls),
    SILENT_SPEECH (the game's "Offline Hindi speech unavailable" fallback text)
  - emits one JSON object per line on stdout (the CI collects these)

Usage: python3 driver.py --seed 7 --steps 150 --out artifacts/s7
"""
import argparse, hashlib, json, os, random, re, subprocess, sys, time

PKG = "com.superover.cricket"
MAIN = PKG + "/.MainActivity"
SILENT_MARK = "Offline Hindi speech unavailable"
INTERESTING = ["quick", "match", "play", "attack", "defend", "big hit", "leave",
               "drinks", "score", "again", "guide", "over", "t20", "odi",
               "bowl", "yorker", "bouncer", "toss", "heads", "tails", "continue",
               "what's new", "whatsnew", "settings", "keeper", "eleven", "xi"]

# Feature screens: name -> regex over the visible text. First sighting per
# session emits COVER and saves a labelled screenshot.
FEATURES = {
    "menu":        r"quick match",
    "setup":       r"choose.*(team|format)|team 11|playing 11|select.*overs",
    "xi_speech":   r"wicketkeeper|of 11",
    "toss":        r"toss",
    "live_match":  r"attack|big hit|defend|yorker|bouncer",
    "live_panel":  r"scorecard|live",
    "drinks":      r"drinks break",
    "guide":       r"gesture guide|practice area|drill",
    "whatsnew":    r"what's new|version 10\.",
    "results":     r"match ended|won by|play again",
    "settings":    r"controls|voice|music|speed",
}

# Mini-tours: best-effort deterministic flows to guarantee coverage.
# Each step: (regex of the control to activate, max polls to wait for it).
TOURS = {
    "tour_whatsnew": [
        (r"what'?s new", 6), (r"version 10\.", 6),
    ],
    "tour_guide": [
        (r"gesture guide", 6), (r"practice|drill|start", 6),
    ],
    "tour_quick_t20": [
        (r"quick match", 6), (r"t20|20 overs", 6), (r"continue|next|start", 8),
    ],
    "tour_odi_setup": [
        (r"quick match", 6), (r"odi|50 overs", 6), (r"back|main menu|home", 6),
    ],
    "tour_settings_toggle": [
        (r"settings", 6), (r"controls|gestures|buttons", 6), (r"back|main menu|home", 6),
    ],
}

def adb(*args, timeout=30, binary=False):
    r = subprocess.run(["adb"] + list(args), capture_output=True, timeout=timeout)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")

def pid():
    return adb("shell", "pidof", PKG).strip()

def dump_ui():
    try:
        adb("shell", "uiautomator", "dump", "/sdcard/__autotest.xml", timeout=40)
        return adb("exec-out", "cat", "/sdcard/__autotest.xml", timeout=40)
    except Exception:
        return ""

BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

def nodes(xml):
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return out
    for n in root.iter("node"):
        b = BOUNDS.match(n.get("bounds") or "")
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        out.append({
            "cls": (n.get("class") or "").rsplit(".", 1)[-1],
            "desc": n.get("content-desc") or "",
            "text": n.get("text") or "",
            "clickable": n.get("clickable") == "true",
            "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            "w": x2 - x1, "h": y2 - y1,
        })
    return out

def emit(obj):
    obj["ts"] = round(time.time(), 1)
    print(json.dumps(obj, ensure_ascii=False), flush=True)

def tap(x, y, double):
    adb("shell", "input", "tap", str(x), str(y))
    if double:
        time.sleep(0.28)
        adb("shell", "input", "tap", str(x), str(y))

def shot(out, name):
    try:
        data = adb("exec-out", "screencap", "-p", binary=True, timeout=30)
        if data[:4] == b"\x89PNG":
            open(os.path.join(out, name + ".png"), "wb").write(data)
    except Exception:
        pass

def screen_text(ns):
    return " | ".join((n["desc"] or n["text"]) for n in ns if (n["desc"] or n["text"]))

def find_node(ns, rx):
    r = re.compile(rx, re.I)
    cands = [n for n in ns if n["clickable"] and r.search(n["desc"] + " " + n["text"])
             and n["w"] > 0 and n["h"] > 0]
    return cands[0] if cands else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tours", default=",".join(TOURS.keys()))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)
    shots = os.path.join(a.out, "shots")
    os.makedirs(shots, exist_ok=True)
    counts = {"tap": 0, "activate": 0, "swipe": 0, "back": 0,
              "crash": 0, "stall": 0, "silent_speech": 0}
    covered = set()
    emit({"type": "start", "seed": a.seed, "steps": a.steps, "tours": a.tours})

    if not pid():
        adb("shell", "am", "start", "-n", MAIN)
        time.sleep(8)

    tours = [t for t in a.tours.split(",") if t in TOURS]
    rng.shuffle(tours)
    tour = None          # (name, [remaining steps])
    tour_wait = 0

    last_sig, same_sig = None, 0
    for step in range(1, a.steps + 1):
        if not pid():
            counts["crash"] += 1
            emit({"type": "event", "event": "CRASH", "step": step})
            shot(shots, "crash_%d" % step)
            time.sleep(2)
            adb("shell", "am", "start", "-n", MAIN)
            time.sleep(8)
            if counts["crash"] >= 3:
                break
            continue

        ns = nodes(dump_ui())
        texts = screen_text(ns)
        descs = set((n["cls"], n["desc"], n["text"]) for n in ns)

        # feature coverage + first-sighting screenshots
        low = texts.lower()
        for feat, rx in FEATURES.items():
            if feat not in covered and re.search(rx, low):
                covered.add(feat)
                emit({"type": "cover", "feature": feat, "step": step})
                shot(shots, "feat_%s.png" % feat)

        if SILENT_MARK in texts:
            counts["silent_speech"] += 1
            emit({"type": "event", "event": "SILENT_SPEECH", "step": step,
                  "screen": texts[:400]})
            shot(shots, "silent_%d" % step)

        sig = hashlib.md5(repr(sorted(descs)).encode()).hexdigest()
        same_sig = same_sig + 1 if sig == last_sig else 0
        last_sig = sig
        if same_sig == 12:
            counts["stall"] += 1
            emit({"type": "event", "event": "STALL", "step": step,
                  "screen": texts[:400]})
            shot(shots, "stall_%d" % step)
            # nudge out of the stall: back, then a centre swipe
            adb("shell", "input", "keyevent", "4")
            time.sleep(0.6)

        # deterministic tour step takes priority when one is armed
        if tour is None and tours and rng.random() < 0.10:
            name = tours.pop(0)
            tour = (name, list(TOURS[name]))
            emit({"type": "tour", "tour": name, "step": step})
            tour_wait = 0

        acted = False
        if tour is not None:
            tname, tsteps = tour
            if not tsteps:
                tour = None
            else:
                rx, maxwait = tsteps[0]
                n = find_node(ns, rx)
                if n:
                    tap(n["cx"], n["cy"], True)
                    counts["activate"] += 1
                    emit({"type": "action", "step": step, "action": "tour",
                          "tour": tname, "target": (n["desc"] or n["text"])[:120]})
                    tsteps.pop(0)
                    tour_wait = 0
                    acted = True
                    if not tsteps:
                        emit({"type": "tour_done", "tour": tname, "step": step})
                        tour = None
                else:
                    tour_wait += 1
                    if tour_wait > maxwait:
                        emit({"type": "tour_aborted", "tour": tname, "step": step,
                              "screen": texts[:200]})
                        tour = None

        if not acted and tour is None:
            actionable = [n for n in ns if n["clickable"] and (n["desc"] or n["text"])
                          and n["w"] > 0 and n["h"] > 0]
            roll = rng.random()
            if actionable and roll < 0.80:
                interesting = [n for n in actionable
                               if any(k in (n["desc"] + " " + n["text"]).lower()
                                      for k in INTERESTING)]
                pool = interesting if (interesting and rng.random() < 0.7) else actionable
                n = rng.choice(pool)
                double = rng.random() < 0.75
                tap(n["cx"], n["cy"], double)
                kind = "activate" if double else "tap"
                counts[kind] += 1
                emit({"type": "action", "step": step, "action": kind,
                      "target": (n["desc"] or n["text"])[:120]})
            elif roll < 0.93:
                x, y = 540, 1200
                dx, dy = rng.choice([(350, 0), (-350, 0), (0, 500), (0, -500)])
                adb("shell", "input", "swipe", str(x), str(y), str(x + dx), str(y + dy), "300")
                counts["swipe"] += 1
                emit({"type": "action", "step": step, "action": "swipe"})
            else:
                adb("shell", "input", "keyevent", "4")
                counts["back"] += 1
                emit({"type": "action", "step": step, "action": "back"})

        if step % 25 == 0:
            shot(shots, "step_%d" % step)
        time.sleep(1.2)

    emit({"type": "summary", "seed": a.seed, "counts": counts,
          "features_covered": sorted(covered)})
    return 0

if __name__ == "__main__":
    sys.exit(main())
