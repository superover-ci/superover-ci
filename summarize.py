#!/usr/bin/env python3
"""Aggregates per-session events.jsonl files into a short Markdown summary."""
import glob, json, os, sys

root = sys.argv[1]
crashes, stalls, silents, sessions, actions = [], [], [], 0, 0
screens_stall = {}
covered = set()
tours_done, tours_aborted = set(), set()
ALL_FEATURES = ["menu", "setup", "xi_speech", "toss", "live_match", "live_panel",
                "drinks", "guide", "whatsnew", "results", "settings"]
for f in sorted(glob.glob(os.path.join(root, "s*/events.jsonl"))):
    seed = os.path.basename(os.path.dirname(f))
    sessions += 1
    for line in open(f, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        t = e.get("type")
        if t == "action":
            actions += 1
        elif t == "cover":
            covered.add(e.get("feature"))
        elif t == "tour_done":
            tours_done.add(e.get("tour"))
        elif t == "tour_aborted":
            tours_aborted.add(e.get("tour"))
        elif t == "event":
            key = (seed, e.get("step"))
            if e.get("event") == "CRASH":
                crashes.append(key)
            elif e.get("event") == "STALL":
                stalls.append(key)
                s = (e.get("screen") or "")[:80]
                screens_stall[s] = screens_stall.get(s, 0) + 1
            elif e.get("event") == "SILENT_SPEECH":
                silents.append(key)
missing = [f for f in ALL_FEATURES if f not in covered]
print("# Autotest summary")
print()
print("- sessions: %d" % sessions)
print("- actions performed: %d" % actions)
print("- features covered: %s" % (", ".join(sorted(covered)) or "none"))
print("- features NOT seen: %s" % (", ".join(missing) or "none - full coverage"))
print("- tours completed: %s; aborted: %s" % (", ".join(sorted(tours_done)) or "none",
                                            ", ".join(sorted(tours_aborted)) or "none"))
print("- CRASH events: %d %s" % (len(crashes), crashes[:10]))
print("- STALL events: %d %s" % (len(stalls), stalls[:10]))
print("- SILENT_SPEECH events: %d %s" % (len(silents), silents[:10]))
if screens_stall:
    print()
    print("## Most common stall screens")
    for s, c in sorted(screens_stall.items(), key=lambda x: -x[1])[:5]:
        print("- (%dx) %s" % (c, s))
print()
print("Verdict: " + ("CLEAN - no crashes, stalls or silent speech."
      if not (crashes or stalls or silents) else "ISSUES FOUND - see events and logcats."))
