"""CHANGELOG.md from the change log of music_player_plan.md (its rows "| doc | date | 0.x.y: what |"),
newest first. Run at each release: python3 scripts/changelog.py"""

import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
row = re.compile(r"^\| [0-9.]+ \| (\d{4}-\d{2}-\d{2}) \| (\d+\.\d+(?:\.\d+)?): (.*) \|$")
entries = []
for line in (root / "music_player_plan.md").read_text(encoding="utf-8").splitlines():
    m = row.match(line)
    if m:
        entries.append((tuple(int(x) for x in m.group(2).split(".")), m.group(2), m.group(1), m.group(3).strip()))
entries.sort(key=lambda e: e[0], reverse=True)
out = ["# Changelog", "", "muzplayer의 버전별 변경 사항입니다(개발 계획서 `music_player_plan.md`의 변경 이력에서 만듦).", ""]
for _, version, date, text in entries:
    out += [f"## {version} — {date}", "", text, ""]
(root / "CHANGELOG.md").write_text("\n".join(out), encoding="utf-8")
print(f"CHANGELOG.md: {len(entries)} versions")
