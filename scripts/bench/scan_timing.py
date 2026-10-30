"""Runs one scan in the foreground and prints the time spent in each step (instrumentation lives
only here, the app is not changed).

Usage (from backend/, with DATABASE_URL, MUSIC_DIR, DATA_DIR set as for the app):
  PYTHONPATH=. ../.venv/bin/python ../scripts/bench/scan_timing.py
"""
import time, functools, sys, logging
from app import scanner
from app.db import SessionLocal
from app.models import ScanJob

T = {}
def timed(mod, name):
    f = getattr(mod, name)
    @functools.wraps(f)
    def w(*a, **k):
        t = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            T[name] = T.get(name, 0) + time.perf_counter() - t
    setattr(mod, name, w)
for n in ("_collect", "_link_chart_duplicates", "prune_orphans", "_find_banners", "_read_tags", "_ensure_cover", "_save_cover", "_embedded_cover", "folder_kinds", "_store", "_refresh_covers"):
    timed(scanner, n)
orig_cache = scanner._Cache.__init__
def cache_init(self, db):
    t = time.perf_counter(); orig_cache(self, db); T["_Cache"] = T.get("_Cache", 0) + time.perf_counter() - t
scanner._Cache.__init__ = cache_init

with SessionLocal() as db:
    job = ScanJob(status="running"); db.add(job); db.commit(); jid = job.id
t0 = time.perf_counter()
scanner._lock.acquire()
scanner._run(jid)
total = time.perf_counter() - t0
with SessionLocal() as db:
    j = db.get(ScanJob, jid)
    print(f"status={j.status} scanned={j.scanned} added={j.added} updated={j.updated} missing={j.missing} errors={j.errors}")
print(f"TOTAL {total:.1f}s")
for k, v in sorted(T.items(), key=lambda x: -x[1]):
    print(f"  {k:24s} {v:7.1f}s")
