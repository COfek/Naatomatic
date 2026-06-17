"""Generate a self-contained HTML dashboard of the Naatomatic database.

Usage:
    python scripts/dashboard.py [--db PATH] [--out dashboard.html] [--print]

Reads the SQLite DB and writes a single HTML file (no external assets, no extra
dependencies) with domain visualizations: personnel, the Justice Table fairness
pools, equipment health, network port utilization, tickets, and shifts. Open the
file in any browser. `--print` also dumps the summary as JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from models.db import DEFAULT_DB_PATH, create_session, get_engine
from models.enums import (
    DEPOT_PERSONAL_NUMBER,
    AssignmentStatus,
    EquipmentKind,
)
from models import tables as t


# --------------------------------------------------------------------------- #
# Data collection
# --------------------------------------------------------------------------- #
def collect(session) -> dict:
    people = session.scalars(select(t.Personnel)).all()
    depot = next((p for p in people if p.personal_number == DEPOT_PERSONAL_NUMBER), None)
    soldiers = [p for p in people if p is not depot]

    jt_rows = session.scalars(select(t.JusticeTable)).all()
    name_by_id = {p.id: p.full_name for p in people}
    pop_by_id = {p.id: p.population.value for p in people}

    equip = session.scalars(select(t.EquipmentItem)).all()
    ports = session.scalars(select(t.Port)).all()
    switches = {sw.id: sw for sw in session.scalars(select(t.Switch)).all()}
    tickets = session.scalars(select(t.Ticket)).all()
    shifts = session.scalars(select(t.Shift)).all()
    adhoc = session.scalars(select(t.AdHocMission)).all()

    # Equipment status by kind
    comp_status = Counter(e.status for e in equip if e.kind == EquipmentKind.COMPUTER)
    mon_status = Counter(e.status for e in equip if e.kind == EquipmentKind.MONITOR)

    # Ports by switch classification: connected vs disconnected
    port_by_class: dict[str, Counter] = {}
    for p in ports:
        cls = switches[p.switch_id].classification.value
        port_by_class.setdefault(cls, Counter())[p.status.value] += 1

    # Justice table rows enriched
    jt = sorted(
        (
            {
                "name": name_by_id.get(r.personnel_id, f"#{r.personnel_id}"),
                "pop": pop_by_id.get(r.personnel_id, "?"),
                "shifts": round(r.shifts_burden_points, 1),
                "support": round(r.support_burden_points, 1),
                "week": r.week_long_count,
                "day": r.single_day_count,
            }
            for r in jt_rows
        ),
        key=lambda d: d["shifts"],
        reverse=True,
    )

    return {
        "counts": {
            "soldiers": len(soldiers),
            "keva": sum(1 for p in soldiers if p.population.value == "KEVA"),
            "sadir": sum(1 for p in soldiers if p.population.value == "SADIR"),
            "managers": sum(1 for p in soldiers if p.roles),
            "switches": len(switches),
            "ports": len(ports),
            "equipment": len(equip),
            "tickets": len(tickets),
            "shifts": len(shifts),
            "adhoc": len(adhoc),
        },
        "computer_status": dict(comp_status),
        "monitor_status": dict(mon_status),
        "ports_by_class": {k: dict(v) for k, v in port_by_class.items()},
        "free_ports": sum(1 for p in ports if p.status.value == "DISCONNECTED"),
        "tickets_by_type": dict(Counter(f"{tk.type.value}/{tk.status.value}" for tk in tickets)),
        "shifts_by_type": dict(Counter(f"{s.type.value}/{s.status.value}" for s in shifts)),
        "shifts_with_reserve": sum(1 for s in shifts if s.reserve_id is not None),
        "shifts_assigned": sum(1 for s in shifts if s.assigned_to is not None),
        "justice": jt,
    }


# --------------------------------------------------------------------------- #
# HTML rendering (no dependencies — inline CSS bars)
# --------------------------------------------------------------------------- #
STATUS_COLORS = {
    "READY_TO_USE": "#3b82f6", "IN_USE": "#22c55e", "FORMATTING": "#f59e0b",
    "READY_FOR_PICKUP": "#a855f7", "BROKEN": "#ef4444", "DECOMMISSIONED": "#6b7280",
    "FUNCTIONAL": "#22c55e", "CONNECTED": "#22c55e", "DISCONNECTED": "#94a3b8",
}


def _stacked(counts: dict) -> str:
    total = sum(counts.values()) or 1
    segs, legend = [], []
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        color = STATUS_COLORS.get(status, "#64748b")
        pct = n / total * 100
        segs.append(f'<div class="seg" style="width:{pct:.1f}%;background:{color}" title="{status}: {n}"></div>')
        legend.append(f'<span class="lg"><i style="background:{color}"></i>{status} ({n})</span>')
    return f'<div class="stack">{"".join(segs)}</div><div class="legend">{"".join(legend)}</div>'


def _bars(rows: list, value_key: str, color: str, max_rows: int = 12) -> str:
    if not rows:
        return "<p class='muted'>none</p>"
    mx = max((r[value_key] for r in rows), default=1) or 1
    out = []
    for r in rows[:max_rows]:
        pct = r[value_key] / mx * 100
        tag = "K" if r["pop"] == "KEVA" else "S"
        out.append(
            f'<div class="row"><span class="lbl">{r["name"]} '
            f'<b class="tag {r["pop"].lower()}">{tag}</b></span>'
            f'<span class="track"><span class="fill" style="width:{pct:.1f}%;background:{color}"></span></span>'
            f'<span class="val">{r[value_key]}</span></div>'
        )
    return "".join(out)


def render(summary: dict) -> str:
    c = summary["counts"]
    cards = "".join(
        f'<div class="card"><div class="num">{v}</div><div class="cap">{k}</div></div>'
        for k, v in c.items()
    )
    jt = summary["justice"]
    reserve_pct = (summary["shifts_with_reserve"] / summary["shifts_assigned"] * 100) if summary["shifts_assigned"] else 0

    def kv_bars(d: dict, color: str) -> str:
        if not d:
            return "<p class='muted'>none</p>"
        mx = max(d.values()) or 1
        return "".join(
            f'<div class="row"><span class="lbl">{k}</span>'
            f'<span class="track"><span class="fill" style="width:{v/mx*100:.1f}%;background:{color}"></span></span>'
            f'<span class="val">{v}</span></div>'
            for k, v in sorted(d.items(), key=lambda kv: -kv[1])
        )

    ports_html = ""
    for cls, counts in summary["ports_by_class"].items():
        ports_html += f'<div class="subhead">{cls}</div>{_stacked(counts)}'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Naatomatic — Data Dashboard</title><style>
*{{box-sizing:border-box}}body{{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0f172a;color:#e2e8f0;padding:28px}}
h1{{margin:0 0 4px;font-size:22px}}.sub{{color:#94a3b8;margin-bottom:24px}}
.cards{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:28px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 18px;min-width:96px}}
.card .num{{font-size:26px;font-weight:700}}.card .cap{{color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px}}
.panel{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:18px}}
.panel h2{{margin:0 0 14px;font-size:15px}}.subhead{{color:#cbd5e1;font-size:12px;margin:10px 0 4px}}
.row{{display:flex;align-items:center;gap:10px;margin:4px 0}}
.lbl{{width:170px;flex:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}}
.track{{flex:1;height:14px;background:#0f172a;border-radius:7px;overflow:hidden}}
.fill{{display:block;height:100%}}.val{{width:42px;text-align:right;font-variant-numeric:tabular-nums;font-size:12px}}
.tag{{font-size:9px;padding:1px 4px;border-radius:4px;vertical-align:middle}}.tag.keva{{background:#7c3aed}}.tag.sadir{{background:#0ea5e9}}
.stack{{display:flex;height:18px;border-radius:6px;overflow:hidden;margin:4px 0}}.seg{{height:100%}}
.legend{{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px}}.lg{{font-size:11px;color:#cbd5e1}}.lg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle}}
.muted{{color:#64748b}}.note{{color:#94a3b8;font-size:12px;margin-top:8px}}
</style></head><body>
<h1>Naatomatic — Data Dashboard</h1>
<div class="sub">Snapshot of <code>naatomatic.db</code> · {c['soldiers']} soldiers ({c['keva']} Keva / {c['sadir']} Sadir) · {c['managers']} managers</div>
<div class="cards">{cards}</div>
<div class="grid">
  <div class="panel"><h2>Computer health</h2>{_stacked(summary['computer_status'])}
    <div class="subhead">Monitors</div>{_stacked(summary['monitor_status'])}</div>
  <div class="panel"><h2>Network ports — {summary['free_ports']} free</h2>{ports_html}</div>
  <div class="panel"><h2>Justice Table — shifts burden (top)</h2>{_bars(jt, 'shifts', '#0ea5e9')}
    <div class="note">K = Keva, S = Sadir. Higher = more loaded.</div></div>
  <div class="panel"><h2>Justice Table — support burden (top)</h2>{_bars(sorted(jt, key=lambda d: -d['support']), 'support', '#a855f7')}</div>
  <div class="panel"><h2>Tickets</h2>{kv_bars(summary['tickets_by_type'], '#f59e0b')}</div>
  <div class="panel"><h2>Shifts — {reserve_pct:.0f}% have a reserve</h2>{kv_bars(summary['shifts_by_type'], '#22c55e')}</div>
</div>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate an HTML dashboard of the DB.")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--out", default=str(Path(DEFAULT_DB_PATH).parent / "dashboard.html"))
    ap.add_argument("--print", action="store_true", help="also dump the summary as JSON")
    args = ap.parse_args()

    session = create_session(get_engine(args.db))
    try:
        summary = collect(session)
    finally:
        session.close()

    Path(args.out).write_text(render(summary), encoding="utf-8")
    if args.print:
        print(json.dumps(summary, indent=2, default=str))
    print(f"Wrote dashboard to {args.out} — open it in a browser.")


if __name__ == "__main__":
    main()
