#!/usr/bin/env python3
"""CG slow-change test (owner OK 2026-10-29 01:02 JST, Muse plan): an EXTRA fixed Instagram slot, IG only.
5 pre-rendered CG slow changes on consecutive days + 1 answer-only short the day after, all at SLOT_TIME JST.
Uses auto_post.py's own upload() / post() / puzzle_caption() / append_log() (auto_post.py is not modified,
puzzle_state.json is not touched, so the existing slots and their answer chains are unaffected).

  nohup python3 post_cg_slot.py >> post_cg_slot.out 2>&1 &     (safe to start again: one instance only, posted
                                                                 items are remembered in posted.json)
Off: touch ~/Looply/output/auto/CG_OFF (or PAUSE). An item more than 90 min late is skipped, not posted late.
Log: post_cg_slot.log in this folder."""
import datetime, fcntl, importlib.util, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LOOPLY = os.path.expanduser("~/Looply")
spec = importlib.util.spec_from_file_location("auto_post", os.path.join(LOOPLY, "scripts", "auto_post.py"))
ap = importlib.util.module_from_spec(spec); spec.loader.exec_module(ap)

JST = datetime.timezone(datetime.timedelta(hours=9))
QUEUE = json.load(open(os.path.join(HERE, "queue.json")))
POSTED = os.path.join(HERE, "posted.json")
CG_OFF = os.path.join(ap.AUTO, "CG_OFF")
LATE = datetime.timedelta(minutes=90)


def log(msg):
    with open(os.path.join(HERE, "post_cg_slot.log"), "a") as f:
        f.write(f"{datetime.datetime.now(JST):%Y-%m-%d %H:%M:%S} {msg}\n")


def posted():
    return json.load(open(POSTED)) if os.path.exists(POSTED) else {}


def caption(item):
    hook, cap, tags = ap.puzzle_caption("change", {})
    if item["type"] == "answer":
        hook = "yesterday's answer 👀 did you spot it in time?"
        cap = (f"{hook}\ncomment how many seconds it took you 👇\nfollow for a new puzzle every day 🧩\n.\n.\n{tags}")
    return hook, cap, tags


def post_item(item):
    video = os.path.join(HERE, item["file"])
    hook, cap, tags = caption(item)
    url = ap.upload(video)
    mid = ap.post(url, cap, cover_ms=item.get("cover_ms"))
    ap.append_log(datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M"), video, item["tag"], hook,
                  f"{item['notes']}; media id {mid}", tags=tags)
    return mid


def main():
    lock = open(os.path.join(HERE, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return  # already running
    log(f"runner started (pid {os.getpid()})")
    for item in QUEUE:
        done = posted()
        if item["file"] in done:
            continue
        at = datetime.datetime.fromisoformat(item["at"]).replace(tzinfo=JST)
        now = datetime.datetime.now(JST)
        if now > at + LATE:
            log(f"{item['file']}: missed ({at:%m/%d %H:%M}, now {now:%m/%d %H:%M}), skipped")
            done[item["file"]] = "missed"; json.dump(done, open(POSTED, "w"), indent=1)
            continue
        if now < at:
            log(f"{item['file']}: waiting until {at:%m/%d %H:%M}")
            while datetime.datetime.now(JST) < at:
                time.sleep(min(300, max(1, (at - datetime.datetime.now(JST)).total_seconds())))
        if os.path.exists(CG_OFF) or os.path.exists(os.path.join(ap.AUTO, "PAUSE")):
            log(f"{item['file']}: CG_OFF / PAUSE present, not posted")
            done[item["file"]] = "off"; json.dump(done, open(POSTED, "w"), indent=1)
            continue
        try:
            mid = post_item(item)
            log(f"{item['file']}: posted, media id {mid}")
            done[item["file"]] = mid
        except Exception as e:
            log(f"{item['file']}: FAILED {e!r}")
            done[item["file"]] = f"failed: {e!r}"[:300]
        json.dump(done, open(POSTED, "w"), indent=1)
    log("queue finished")


if __name__ == "__main__":
    main()
