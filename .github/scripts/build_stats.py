"""Build github-dashboard.svg from live GitHub data.

Usage: python build_stats.py <out_dir>
Env:   GH_USER  (default: repository owner / Mihiran-Thilakarathna)
       GH_TOKEN (optional; with a personal token private repos & contributions count too)
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER") or "Mihiran-Thilakarathna"
TOKEN = os.environ.get("GH_TOKEN", "").strip()
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist"
TODAY = dt.date.today()

BG, BG2, PANEL, BORDER = "#0b0f18", "#111a33", "#0f1524", "#1f2a44"
OR, BL, TX, MU = "#F7941D", "#7cc0ff", "#e6e9f0", "#8b95a7"
SANS = "'Segoe UI','Inter',-apple-system,Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono','Cascadia Code',Consolas,'Courier New',monospace"
LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572A5", "Java": "#b07219",
    "Kotlin": "#A97BFF", "C++": "#f34b7d", "C": "#555555", "HTML": "#e34c26", "CSS": "#663399",
    "Dart": "#00B4AB", "Jupyter Notebook": "#DA5B0B", "PHP": "#4F5D95", "Go": "#00ADD8",
    "Shell": "#89e051", "C#": "#178600", "SCSS": "#c6538c", "Vue": "#41b883", "Swift": "#F05138",
}


def request(url, data=None):
    headers = {"User-Agent": "profile-stats", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gql(query, **variables):
    res = request("https://api.github.com/graphql", {"query": query, "variables": variables})
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


# ------------------------------------------------------------------ data
def fetch_graphql():
    base = gql("""query($login:String!){user(login:$login){
        createdAt followers{totalCount}
        pullRequests{totalCount} issues{totalCount}
        repositories(first:100, ownerAffiliations:OWNER, isFork:false){totalCount nodes{
          stargazerCount languages(first:10, orderBy:{field:SIZE, direction:DESC}){edges{size node{name color}}}}}}}""",
               login=USER)["user"]
    days, commits_year = {}, 0
    for year in range(int(base["createdAt"][:4]), TODAY.year + 1):
        c = gql("""query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
            contributionsCollection(from:$from,to:$to){totalCommitContributions restrictedContributionsCount
              contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
                login=USER, **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})
        coll = c["user"]["contributionsCollection"]
        if year == TODAY.year:
            commits_year = coll["totalCommitContributions"] + coll["restrictedContributionsCount"]
        for w in coll["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    langs = {}
    for repo in base["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs[n] = langs.get(n, 0) + e["size"]
            if e["node"]["color"]:
                LANG_COLORS.setdefault(n, e["node"]["color"])
    return {
        "repos": base["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in base["repositories"]["nodes"]),
        "followers": base["followers"]["totalCount"],
        "prs": base["pullRequests"]["totalCount"],
        "commits_year": commits_year,
        "days": days,
        "langs": langs,
    }


def fetch_public():
    """Token-less fallback using the public REST API and a public contributions mirror."""
    user = request(f"https://api.github.com/users/{USER}")
    repos = [r for r in request(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
    langs = {}
    for r in repos:
        for n, size in request(r["languages_url"]).items():
            langs[n] = langs.get(n, 0) + size
    prs = request(f"https://api.github.com/search/issues?q=author:{USER}+type:pr")["total_count"]
    cal = request(f"https://github-contributions-api.jogruber.de/v4/{USER}?y=all")
    days = {d["date"]: d["count"] for d in cal["contributions"]}
    return {
        "repos": len(repos),
        "stars": sum(r["stargazers_count"] for r in repos),
        "followers": user["followers"],
        "prs": prs,
        "commits_year": None,
        "days": days,
        "langs": langs,
    }


def load():
    if TOKEN:
        try:
            return fetch_graphql()
        except Exception as e:  # keep the dashboard alive even if GraphQL hiccups
            print("GraphQL failed, using public fallback:", e)
    return fetch_public()


# ------------------------------------------------------------------ maths
def streaks(days):
    dates = sorted(d for d in days if dt.date.fromisoformat(d) <= TODAY)
    longest, run, start, best = 0, 0, None, (None, None)
    for d in dates:
        if days[d] > 0:
            run += 1
            start = start if run > 1 else d
            if run > longest:
                longest, best = run, (start, d)
        else:
            run, start = 0, None
    cur, day = 0, TODAY
    if days.get(day.isoformat(), 0) == 0:
        day -= dt.timedelta(days=1)
    cur_end = day
    while days.get(day.isoformat(), 0) > 0:
        cur += 1
        day -= dt.timedelta(days=1)
    cur_range = (day + dt.timedelta(days=1), cur_end) if cur else (None, None)
    return cur, cur_range, longest, best


def fmt_range(a, b):
    if not a:
        return "start one today"
    a = a if isinstance(a, dt.date) else dt.date.fromisoformat(a)
    b = b if isinstance(b, dt.date) else dt.date.fromisoformat(b)
    f = lambda d: d.strftime("%b ") + str(d.day)
    return f"{f(a)} – {f(b)}" + (f", {b.year}" if b.year != TODAY.year else "")


def weekly(days, n=26):
    out = []
    end = TODAY
    for _ in range(n):
        out.append(sum(days.get((end - dt.timedelta(days=i)).isoformat(), 0) for i in range(7)))
        end -= dt.timedelta(days=7)
    return out[::-1]


# ------------------------------------------------------------------ render
def render(s):
    days = s["days"]
    total = sum(v for d, v in days.items() if dt.date.fromisoformat(d) <= TODAY)
    this_year = sum(v for d, v in days.items() if d.startswith(str(TODAY.year)) and dt.date.fromisoformat(d) <= TODAY)
    cur, cur_rng, longest, best = streaks(days)
    active = sum(1 for d, v in days.items() if v > 0)
    weeks = weekly(days)
    W, H = 1200, 470
    p = []

    tiles = [
        ("TOTAL CONTRIBUTIONS", total, OR),
        (f"CONTRIBUTIONS {TODAY.year}", this_year, BL),
        ("MY REPOSITORIES", s["repos"], OR),
        ("STARS EARNED", s["stars"], BL),
        ("PULL REQUESTS", s["prs"], OR),
        ("FOLLOWERS", s["followers"], BL),
    ]
    for i, (label, val, col) in enumerate(tiles):
        x, y = 30 + (i % 3) * 188, 30 + (i // 3) * 104
        p.append(f'''<g class="tile" style="animation-delay:{i*.1:.1f}s">
<rect x="{x}" y="{y}" width="176" height="92" rx="14" fill="{PANEL}" stroke="{BORDER}"/>
<circle cx="{x+20}" cy="{y+24}" r="4" fill="{col}"/>
<text x="{x+32}" y="{y+28}" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">{label}</text>
<text x="{x+18}" y="{y+72}" font-size="34" font-weight="800" fill="{TX}">{val:,}</text></g>''')

    # weekly bars
    bx, by, bw, bh = 30, 262, 552, 150
    p.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh+48}" rx="14" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(f'<text x="{bx+18}" y="{by+28}" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">CONTRIBUTIONS · LAST 26 WEEKS</text>')
    p.append(f'<text x="{bx+bw-18}" y="{by+28}" font-size="12" fill="{OR}" text-anchor="end" class="m">{sum(weeks):,} total</text>')
    mx = max(weeks) or 1
    step = (bw - 36) / len(weeks)
    for i, v in enumerate(weeks):
        h = max(3, v / mx * (bh - 40))
        x = bx + 18 + i * step
        col = OR if i == len(weeks) - 1 else (BL if v == mx else "#2a3756")
        p.append(f'<rect x="{x:.1f}" y="{by+bh+20-h:.1f}" width="{step-6:.1f}" height="{h:.1f}" rx="3" fill="{col}" class="bar" style="animation-delay:{.3+i*.03:.2f}s"><title>{v} contributions</title></rect>')

    # streak ring
    cx, cy, r = 735, 175, 82
    circ = 2 * 3.14159 * r
    ratio = (cur / longest) if longest else 0
    p.append(f'<rect x="602" y="30" width="266" height="430" rx="14" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(f'<text x="{cx}" y="62" font-size="10.5" fill="{MU}" letter-spacing="1" text-anchor="middle" class="m">CURRENT STREAK</text>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1b2540" stroke-width="12"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#rg)" stroke-width="12" stroke-linecap="round" '
             f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ:.1f}" transform="rotate(-90 {cx} {cy})">'
             f'<animate attributeName="stroke-dashoffset" from="{circ:.1f}" to="{circ*(1-max(ratio, .02)):.1f}" dur="1.6s" begin=".3s" fill="freeze"/></circle>')
    p.append(f'<path d="M{cx} {cy-42} q14 16 8 30 q10 -4 10 -14 q12 16 2 32 q-8 10 -20 10 q-16 0 -22 -14 q-6 -14 6 -26 q0 10 6 12 q-4 -18 10 -30z" fill="{OR}" opacity=".18" class="fire"/>')
    p.append(f'<text x="{cx}" y="{cy+14}" font-size="50" font-weight="800" fill="{TX}" text-anchor="middle">{cur}</text>')
    p.append(f'<text x="{cx}" y="{cy+40}" font-size="13" fill="{OR}" text-anchor="middle" class="m">day{"s" if cur != 1 else ""}</text>')
    p.append(f'<text x="{cx}" y="{cy+r+34}" font-size="12.5" fill="{MU}" text-anchor="middle" class="m">{fmt_range(*cur_rng)}</text>')
    p.append(f'<line x1="626" y1="330" x2="844" y2="330" stroke="{BORDER}"/>')
    for j, (lab, val, sub) in enumerate([("LONGEST STREAK", f"{longest} days", fmt_range(*best)),
                                         ("ACTIVE DAYS", f"{active:,}", "days with contributions")]):
        y = 362 + j * 52
        p.append(f'<text x="626" y="{y}" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">{lab}</text>'
                 f'<text x="844" y="{y}" font-size="17" font-weight="700" fill="{BL if j == 0 else TX}" text-anchor="end">{val}</text>'
                 f'<text x="626" y="{y+20}" font-size="12" fill="#56607a" class="m">{esc(sub)}</text>')

    # languages
    langs = sorted(s["langs"].items(), key=lambda kv: -kv[1])
    tot = sum(v for _, v in langs) or 1
    top = langs[:7]
    if len(langs) > 7:
        top.append(("Other", sum(v for _, v in langs[7:])))
    lx, lw = 888, 282
    p.append(f'<rect x="{lx}" y="30" width="{lw}" height="430" rx="14" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(f'<text x="{lx+18}" y="62" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">MOST USED LANGUAGES</text>')
    sx = lx + 18
    p.append(f'<clipPath id="lb"><rect x="{sx}" y="80" width="{lw-36}" height="12" rx="6"/></clipPath><g clip-path="url(#lb)">')
    for i, (n, v) in enumerate(top):
        w = v / tot * (lw - 36)
        p.append(f'<rect x="{sx:.1f}" y="80" width="{w+.5:.1f}" height="12" fill="{LANG_COLORS.get(n, MU)}" class="seg" style="animation-delay:{.3+i*.08:.2f}s"/>')
        sx += w
    p.append('</g>')
    for i, (n, v) in enumerate(top):
        y = 128 + i * 41
        pct = v / tot * 100
        col = LANG_COLORS.get(n, MU)
        p.append(f'''<g class="tile" style="animation-delay:{.4+i*.08:.2f}s">
<circle cx="{lx+24}" cy="{y-4}" r="5" fill="{col}"/>
<text x="{lx+38}" y="{y}" font-size="14.5" fill="{TX}">{esc(n)}</text>
<text x="{lx+lw-18}" y="{y}" font-size="13" fill="{MU}" text-anchor="end" class="m">{pct:.1f}%</text>
<rect x="{lx+38}" y="{y+9}" width="{lw-56}" height="4" rx="2" fill="#1b2540"/>
<rect x="{lx+38}" y="{y+9}" width="{max(2, (lw-56)*pct/100):.1f}" height="4" rx="2" fill="{col}" class="seg" style="animation-delay:{.5+i*.08:.2f}s"/></g>''')

    stamp = f"updated {TODAY.isoformat()} · github.com/{USER}"
    body = f'''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>
<linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{OR}"/><stop offset="1" stop-color="{BL}"/></linearGradient>
</defs>
<rect x="1" y="1" width="{W-2}" height="{H+28}" rx="22" fill="url(#bg)" stroke="{BORDER}" stroke-width="1.5"/>
{"".join(p)}
<text x="{W-30}" y="{H+16}" font-size="11" fill="#56607a" text-anchor="end" class="m">{esc(stamp)}</text>'''
    style = f'''.m{{font-family:{MONO}}}
.tile{{animation:in .7s ease-out both}}
@keyframes in{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
.bar{{transform-box:fill-box;transform-origin:bottom;animation:grow .8s cubic-bezier(.2,.8,.2,1) both}}
@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
.seg{{transform-box:fill-box;transform-origin:left;animation:sx .9s ease-out both}}
@keyframes sx{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
.fire{{transform-box:fill-box;transform-origin:bottom;animation:fire 1.6s ease-in-out infinite alternate}}
@keyframes fire{{to{{transform:scale(1.15);opacity:.32}}}}'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H+30}" viewBox="0 0 {W} {H+30}" font-family="{SANS}">
<style>{style}</style>
{body}
</svg>
'''


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    stats = load()
    with open(os.path.join(OUT, "github-dashboard.svg"), "w", encoding="utf-8") as f:
        f.write(render(stats))
    print("dashboard written:", {k: v for k, v in stats.items() if k not in ("days", "langs")})
