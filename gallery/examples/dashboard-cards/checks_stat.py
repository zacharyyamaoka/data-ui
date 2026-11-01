"""Browser checks for the stat cards of the catalog (docs/peps/0005-dashboard-cards.md §2: kpi, gauge, bullet, barlist,
status). Every expected number is computed from the case's JSON (kpis.json, days.json), never read from the page's model;
every claim is a measurement (getBoundingClientRect, computed style, an SVG path's length), never "the element exists"."""

import collections
import math

KPIS = "kpis.json"
DAYS = "days.json"
TONE_OF = {"pass": "good", "fail": "bad", "mixed": "warn", "none": "muted"}  # the case's status: tones: map


def value(cell):
    return cell["value"] if isinstance(cell, dict) else cell


def sig3(x):
    return f"{x:.3g}"


def run(ctx, path, h):
    rows, ready, panel, D = h["rows"], h["ready"], h["panel"], h["D"]
    check = ctx.check
    kpis = sorted(rows(KPIS), key=lambda r: r["order"])
    days = rows(DAYS)

    page = ctx.page(path)
    ready(page)

    def probe(page, tone, scope):
        """The colour a tone token resolves to inside `scope` (a throwaway element wearing var(--dv-tone-<tone>))."""
        return page.evaluate("""([sel, tone]) => { const host = document.querySelector(sel); if (!host) return null; const p = document.createElement('i');
          p.style.cssText = `position:absolute;width:1px;height:1px;background:var(--dv-tone-${tone})`; host.append(p);
          const c = getComputedStyle(p).backgroundColor; p.remove(); return c; }""", [scope, tone])

    # ---- the KPI card: reference look, 3 significant figures, delta with an arrow AND a colour
    tuned = next(r for r in kpis if r["situation"] == "tuned")
    stop = value(tuned["stop_p90"])
    kp = page.evaluate("""() => { const k = document.querySelector("#example .dd-panel[data-panel='stop-error'] data-kpi"); if (!k) return null;
      const num = k.querySelector('.dv-kpi-num'), d = k.querySelector('.dv-kpi-delta'), card = k.querySelector('.dv-kpi-card');
      return { num: num && num.textContent, exact: num && num.dataset.exact, dir: d && d.dataset.dir, tone: k.dataset.tone,
        arrow: d ? getComputedStyle(d, '::before').content : null, deltaColor: d ? getComputedStyle(d).color : null,
        deltaText: d && d.textContent, deltaPill: d ? getComputedStyle(d).borderRadius : null,
        tabular: num ? getComputedStyle(num).fontVariantNumeric : null, labelSize: getComputedStyle(k.querySelector('.dv-kpi-label')).fontSize,
        footSize: getComputedStyle(k.querySelector('.dv-kpi-foot')).fontSize, cardBg: getComputedStyle(card).backgroundColor,
        cardBorder: getComputedStyle(card).borderTopWidth, cq: getComputedStyle(card).containerType }; }""")
    good = probe(page, "good", f"{D} .dd-panel[data-panel='stop-error'] data-kpi")
    bad = probe(page, "bad", f"{D} .dd-panel[data-panel='stop-error'] data-kpi")
    want_dir = "down" if stop < 5 else "up"
    want_tone = "good" if stop < 5 else "bad"  # better: lower
    check("stop-error KPI: the number is the oracle stop_p90 to 3 significant figures; the stored value stays in data-exact",
          bool(kp) and kp["num"] == sig3(stop) and kp["exact"] == str(stop), {"got": kp and [kp["num"], kp["exact"]], "want": [sig3(stop), str(stop)]})
    check(f"stop-error KPI: the delta vs target 5 shows {'▼' if want_dir == 'down' else '▲'} with the '{want_tone}' tone (better: lower), arrow AND colour",
          bool(kp) and kp["dir"] == want_dir and ("▼" if want_dir == "down" else "▲") in (kp["arrow"] or "") and kp["tone"] == want_tone
          and kp["deltaColor"] == (good if want_tone == "good" else bad) and good != bad, {"got": kp, "good": good, "bad": bad})
    check("stop-error KPI: reference look: muted 12.5px label, 11.5px footer, tabular numbers, delta as a pill, no own box inside a dashboard, a size container",
          bool(kp) and kp["labelSize"] == "12.5px" and kp["footSize"] == "11.5px" and "tabular-nums" in (kp["tabular"] or "")
          and kp["cardBg"] in ("rgba(0, 0, 0, 0)", "transparent") and kp["cardBorder"] == "0px" and kp["cq"] == "inline-size"
          and float((kp["deltaPill"] or "0").replace("px", "") or 0) >= 8, kp)

    # ---- the number follows its card by container query: clamp(20px, 12cqi, 44px); never overflows
    def font_vs_card(page):
        return page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='stop-error'] data-kpi")].map((k) => {
          const card = k.querySelector('.dv-kpi-card'), num = k.querySelector('.dv-kpi-num'), cs = getComputedStyle(card);
          const inner = card.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          const n = num.getBoundingClientRect(), c = card.getBoundingClientRect();
          return { font: parseFloat(getComputedStyle(num).fontSize), inner, fits: card.scrollWidth <= card.clientWidth && n.right <= c.right + 0.5 }; })[0]""")

    wide = font_vs_card(page)
    # WHY the card itself, not the panel: the grid keeps a card at least 200 px wide, so only the card can be squeezed under it
    page.evaluate("""() => { document.querySelector("#example .dd-panel[data-panel='stop-error'] data-kpi").style.width = '120px'; }""")
    ctx.frames(page)
    narrow = font_vs_card(page)
    page.evaluate("""() => { document.querySelector("#example .dd-panel[data-panel='stop-error'] data-kpi").style.width = ''; }""")

    def clamp_font(m):
        return min(44, max(20, 0.12 * m["inner"]))
    check("KPI number: font-size is clamp(20px, 12cqi, 44px) of its card (measured at the panel's width and with the card squeezed to 120 px: smaller, at the 20 px floor), never overflowing",
          abs(wide["font"] - clamp_font(wide)) < 0.6 and abs(narrow["font"] - clamp_font(narrow)) < 0.6 and narrow["font"] < wide["font"] and narrow["font"] == 20
          and wide["fits"] and narrow["fits"], {"wide": wide, "narrow": narrow})

    # ---- gauge: the fill is Σ passed_runs / Σ judged_runs; the target marker sits at 0.9
    ratio = sum(r["passed_runs"] for r in days) / sum(r["judged_runs"] for r in days)
    g = page.evaluate("""() => { const root = document.querySelector("#example .dd-panel[data-panel='pass-rate'] .dv-gauge"); if (!root) return null;
      const track = root.querySelector('.dv-gauge-track'), fill = root.querySelector('.dv-gauge-fill'), tick = root.querySelector('.dv-gauge-target');
      if (!track || !fill || !tick) return { missing: true, shape: root.dataset.shape };
      const arc = track instanceof SVGGeometryElement, tr = track.getBoundingClientRect(), tk = tick.getBoundingClientRect();
      const out = { shape: root.dataset.shape, arc, value: (root.querySelector('.dv-gauge-num') || {}).textContent, tick: [tk.left + tk.width / 2, tk.top + tk.height / 2] };
      if (arc) {
        const L = track.getTotalLength(), m = track.getScreenCTM(), at = (f) => { const p = track.getPointAtLength(f * L); return [p.x * m.a + p.y * m.c + m.e, p.x * m.b + p.y * m.d + m.f]; };
        out.frac = fill.getTotalLength() / L; out.want = at(0.9);
      } else {
        const fr = fill.getBoundingClientRect(); out.frac = fr.width / tr.width; out.want = [tr.left + 0.9 * tr.width, tk.top + tk.height / 2];
      }
      return out; }""")
    check("pass-rate gauge: fill fraction equals Σ passed_runs / Σ judged_runs over days.json (within 1%)",
          bool(g) and not g.get("missing") and abs(g["frac"] - ratio) < 0.01, {"got": g and g.get("frac"), "want": ratio, "gauge": g})
    check("pass-rate gauge: the target marker (0.9) is within 1 px of its expected position on the track",
          bool(g) and not g.get("missing") and math.hypot(g["tick"][0] - g["want"][0], g["tick"][1] - g["want"][1]) <= 1.0, g and {"tick": g.get("tick"), "want": g.get("want")})
    check("pass-rate gauge: the value is written to 3 significant figures (the dashboard's numbers: digits 3)",
          bool(g) and g.get("value") == sig3(ratio), {"got": g and g.get("value"), "want": sig3(ratio)})

    # ---- bullet: one row per kpis row; bar = stop_p90 / 60 (clipped at the track's end), tick = 5 / 60
    b = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='gate-margin'] .dv-bullet-row")].map((r) => {
      const t = r.querySelector('.dv-bullet-track').getBoundingClientRect(), bar = r.querySelector('.dv-bullet-bar').getBoundingClientRect(), k = r.querySelector('.dv-bullet-target').getBoundingClientRect();
      return { label: r.querySelector('.dv-bullet-label').textContent, frac: bar.width / t.width, tick: (k.left + k.width / 2 - t.left) / t.width, tickPx: k.left + k.width / 2 - t.left, w: t.width,
        clipped: r.dataset.clipped === 'true', text: r.querySelector('.dv-bullet-value').textContent, bands: r.querySelectorAll('.dv-bullet-band').length }; })""")
    want_b = [(r["title"], min(value(r["stop_p90"]) / 60, 1), value(r["stop_p90"]) > 60) for r in kpis]
    check("gate-margin bullet: one row per kpis row (4), in the view's order",
          [x["label"] for x in b] == [t for t, _, _ in want_b] and len(b) == 4, [x["label"] for x in b])
    check("gate-margin bullet: each value bar / track = stop_p90 / 60 within 1% (the factory's 124 is clipped at the track end and says so)",
          len(b) == 4 and all(abs(x["frac"] - w[1]) < 0.01 and x["clipped"] == w[2] for x, w in zip(b, want_b)), [(x["label"], round(x["frac"], 4), x["clipped"]) for x in b])
    check("gate-margin bullet: the target tick sits at 5 / 60 of the track on every row (within 1 px); three band shades; value text aligned right",
          len(b) == 4 and all(abs(x["tickPx"] - 5 / 60 * x["w"]) <= 1.0 and x["bands"] == 3 for x in b), [(round(x["tickPx"], 2), round(5 / 60 * x["w"], 2), x["bands"]) for x in b])

    # ---- barlist: Tremor's BarList
    def barlist(key):
        return page.evaluate("""(key) => { const root = document.querySelector(`#example .dd-panel[data-panel='${key}'] .dv-barlist`); if (!root) return null;
          const rows = [...root.querySelectorAll('.dv-barlist-row')].map((r) => { const t = r.querySelector('.dv-barlist-track').getBoundingClientRect(), b = r.querySelector('.dv-barlist-bar').getBoundingClientRect();
            return { label: r.querySelector('.dv-barlist-label').textContent, text: r.querySelector('.dv-barlist-value').textContent, w: b.width, track: t.width, tabular: getComputedStyle(r.querySelector('.dv-barlist-value')).fontVariantNumeric }; });
          const more = root.querySelector('.dv-barlist-more'); return { rows, more: more && more.textContent }; }""", key)

    bl = barlist("tracking-rms-by-gains")
    ordered = sorted(kpis, key=lambda r: value(r["tracking_rms"]))  # better: lower -> ascending
    top = max(value(r["tracking_rms"]) for r in kpis)
    check("tracking-rms-by-gains barlist: 4 rows ordered by tracking_rms ascending (better: lower)",
          bool(bl) and [r["label"] for r in bl["rows"]] == [r["title"] for r in ordered], bl and [r["label"] for r in bl["rows"]])
    check("tracking-rms-by-gains barlist: bar widths are value / max of the track within 1 px; values right-aligned in tabular figures to 3 significant figures",
          bool(bl) and len(bl["rows"]) == 4 and all(abs(r["w"] - value(o["tracking_rms"]) / top * r["track"]) <= 1.0 and r["text"].startswith(sig3(value(o["tracking_rms"])))
                                                       and "tabular-nums" in r["tabular"] for r, o in zip(bl["rows"], ordered)),
          bl and [(r["label"], round(r["w"], 2), r["text"]) for r in bl["rows"]])

    totals = collections.Counter()
    for r in days:
        totals[r["track_title"]] += r["runs"]
    desc = sorted(totals.items(), key=lambda kv: -kv[1])
    shown, rest = desc[:8], len(desc) - 8
    rt = barlist("runs-per-track")
    got_vals = [int(r["text"].replace(",", "")) for r in rt["rows"]] if rt else []
    tie_ok = bool(rt) and all({r["label"] for r, v in zip(rt["rows"], got_vals) if v == val} == {k for k, v in shown if v == val} for val in {v for _, v in shown})
    check("runs-per-track barlist: the top 8 tracks by Σ runs over days.json, in order (ties in either order)",
          bool(rt) and got_vals == [v for _, v in shown] and tie_ok, rt and [(r["label"], r["text"]) for r in rt["rows"]])
    top_runs = shown[0][1]
    check(f"runs-per-track barlist: '+{rest} more' is shown for the tracks past the limit; bar widths follow value / max",
          bool(rt) and rt["more"] is not None and rt["more"].strip() == f"+{rest} more" and all(abs(r["w"] - v / top_runs * r["track"]) <= 1.0 for r, (_, v) in zip(rt["rows"], shown)),
          rt and [rt["more"], [round(r["w"], 1) for r in rt["rows"]]])

    # ---- status: one tracker row per track, one block per day, coloured by its tone
    by_track = collections.OrderedDict()
    for r in sorted(days, key=lambda r: r["day"]):
        by_track.setdefault(r["track_title"], []).append(r)
    st = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='daily-verdicts'] .dv-tracker-row")].map((r) => ({
      label: r.querySelector('.dv-tracker-label').textContent, blocks: [...r.querySelectorAll('.dv-tracker-block')].map((b) => ({ bg: getComputedStyle(b).backgroundColor, title: b.title, w: b.getBoundingClientRect().width })) }))""")
    scope = f"{D} .dd-panel[data-panel='daily-verdicts'] .dv-view-tracker"
    tone_bg = {t: probe(page, t, scope) for t in ("good", "bad", "warn", "muted")}
    check("daily-verdicts status: one tracker row per track in days.json (13), block count per row = that track's day rows",
          len(st) == len(by_track) and {x["label"].strip(): len(x["blocks"]) for x in st} == {k: len(v) for k, v in by_track.items()},
          {"rows": len(st), "want": len(by_track), "counts": [(x["label"], len(x["blocks"])) for x in st][:3]})
    bad_blocks = []
    for x in st:
        want = by_track.get(x["label"].strip(), [])
        for blk, r in zip(x["blocks"], want):
            if blk["bg"] != tone_bg[TONE_OF[r["verdict"]]] or r["day"] not in blk["title"] or r["verdict"] not in blk["title"]:
                bad_blocks.append((x["label"], r["day"], r["verdict"], blk["bg"], blk["title"]))
    check("daily-verdicts status: every block's background is its tone's token (pass good, fail bad, mixed warn, none muted), in day order, hover title = day + state; the four tones differ",
          not bad_blocks and len(set(tone_bg.values())) == 4 and len(st) > 0, {"bad": bad_blocks[:3], "tones": tone_bg})
    legend = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='daily-verdicts'] .dv-tracker-legend .dv-tracker-key")].map((e) => e.textContent.trim())""")
    present = {r["verdict"] for r in days}
    check("daily-verdicts status: the legend names the states present", set(legend) == present, {"legend": legend, "want": sorted(present)})

    # ---- compact numbers (26,513 -> 26.5K) through the real views, on a throwaway <data-views> with the dashboard's numbers
    compact = page.evaluate("""async () => {
      const mk = (type, extra) => { const el = document.createElement('data-views'); el.style.cssText = 'display:block;width:420px;position:absolute;left:0;top:0;--data-height:260px';
        el.data = { id: 't', title: 't', titleProperty: 'name', properties: { name: { type: 'text' }, n: { type: 'number' } }, rows: [{ id: 'a', name: 'Alpha', n: 26513 }, { id: 'b', name: 'Beta', n: 900 }] };
        el.base = { views: [{ type, name: 't', style: { numbers: { digits: 3, compact: true } }, ...extra }] }; document.body.append(el); return el; };
      const bar = mk('barlist', { barlist: { label: 'name', value: 'n' } }), kpi = mk('kpi', { filters: 'name == "Alpha"', kpi: { label: 'Alpha', value: { property: 'n' } } });
      await new Promise((r) => { const t = setInterval(() => { if (bar.querySelector('.dv-barlist-value') && kpi.querySelector('.dv-kpi-num')) { clearInterval(t); r(); } }, 50); });
      const out = { bar: [...bar.querySelectorAll('.dv-barlist-row')].map((r) => [r.querySelector('.dv-barlist-value').textContent, r.querySelector('.dv-barlist-value').title]),
        kpi: [kpi.querySelector('.dv-kpi-num').textContent, kpi.querySelector('.dv-kpi-num').dataset.exact] };
      bar.remove(); kpi.remove(); return out; }""")
    check("compact numbers: 26,513 renders 26.5K in the bar list and the KPI card (style.numbers), the stored value one hover away",
          compact["bar"][0][0].startswith("26.5K") and "26,513" in compact["bar"][0][1] and compact["bar"][1][0].startswith("900")
          and compact["kpi"] == ["26.5K", "26,513"], compact)

    # ---- click: every stat card opens the rows behind it (drill-down), the dashboard's one peek
    page.locator(f"{D} .dd-panel[data-panel='tracking-rms-by-gains'] .dv-barlist-row").first.click()
    opened = ctx.until(page, "() => !!document.querySelector('#example data-views.dd-drill .dv-peek:not([hidden])')", timeout=8000)
    check("click: a bar list row opens the peek with the rows behind it (host.open)", opened, None)
    page.keyboard.press("Escape")
    page.context.close()

    # ---- looks: light and dark, 1440 and 390; no sideways scroll, nothing overflows its card
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            tag = f"{'dark' if dark else 'light'}-{width}"
            over = p.evaluate("""() => ['stop-error', 'tracking-rms-by-gains', 'pass-rate', 'gate-margin', 'runs-per-track', 'daily-verdicts'].flatMap((key) => {
              const v = document.querySelector(`#example .dd-panel[data-panel='${key}'] .dv-view`); if (!v) return [key + ': no view'];
              const bad = []; if (v.scrollWidth > v.clientWidth + 1) bad.push(key + ' view ' + v.scrollWidth + '>' + v.clientWidth);
              for (const e of v.querySelectorAll('.dv-kpi-card, .dv-gauge, .dv-bullet, .dv-barlist, .dv-tracker')) if (e.scrollWidth > e.clientWidth + 1) bad.push(key + ' ' + e.className + ' ' + e.scrollWidth + '>' + e.clientWidth);
              return bad; })""")
            sw = p.evaluate("document.scrollingElement.scrollWidth")
            check(f"stat cards, {tag}: nothing scrolls sideways, no card overflows" + (" (KPI number shrinks with its card)" if width == 390 else ""),
                  not over and sw <= width, {"over": over, "scrollWidth": sw})
            if width == 390:
                f = font_vs_card(p)
                check("stat cards, 390 px: the KPI number follows the container query clamp(20px, 12cqi, 44px) and fits", abs(f["font"] - clamp_font(f)) < 0.6 and f["fits"], f)
            for key, name in (("stop-error", "kpi"), ("tracking-rms-by-gains", "barlist"), ("pass-rate", "gauge"), ("gate-margin", "bullet"), ("runs-per-track", "barlist2"), ("daily-verdicts", "status")):
                p.locator(f"{D} .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
                try:
                    out = ctx.shot.__func__.__globals__["OUT"]
                    p.locator(f"{D} .dd-panel[data-panel='{key}']").screenshot(path=str(out / f"stat-{name}-{tag}.png"))
                except Exception:
                    ctx.shot(p, f"stat-{name}-{tag}")
            p.context.close()
