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


CORE_LANGS = {"TypeScript", "JavaScript", "Python", "Java", "Kotlin", "Dart"}
FRAMEWORKS = [
    ("React", "#61DAFB"), ("Next.js", "#e6e9f0"), ("Node.js", "#339933"), ("Spring Boot", "#6DB33F"),
    ("Tailwind", "#38BDF8"), ("TensorFlow", "#FF6F00"), ("PyTorch", "#EE4C2C"), ("FastAPI", "#009688"),
]
SNAKE_COLORS = ["#161b2e", "#0e3a5c", "#0e75b6", "#4fa3e0", "#7cc0ff"]


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


def overview_graphql():
    since = (TODAY - dt.timedelta(days=365)).isoformat()
    c = gql("""query($login:String!,$from:DateTime!){user(login:$login){contributionsCollection(from:$from){
        totalCommitContributions restrictedContributionsCount totalIssueContributions
        totalPullRequestContributions totalPullRequestReviewContributions
        commitContributionsByRepository(maxRepositories:100){repository{nameWithOwner} contributions{totalCount}}
        pullRequestContributionsByRepository(maxRepositories:100){repository{nameWithOwner}}
        issueContributionsByRepository(maxRepositories:100){repository{nameWithOwner}}}}}""",
            login=USER, **{"from": f"{since}T00:00:00Z"})["user"]["contributionsCollection"]
    repos = {r["repository"]["nameWithOwner"]: r["contributions"]["totalCount"] for r in c["commitContributionsByRepository"]}
    for key in ("pullRequestContributionsByRepository", "issueContributionsByRepository"):
        for r in c[key]:
            repos.setdefault(r["repository"]["nameWithOwner"], 0)
    return {
        "commits": c["totalCommitContributions"] + c["restrictedContributionsCount"],
        "issues": c["totalIssueContributions"],
        "prs": c["totalPullRequestContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
        "repos": sorted(repos.items(), key=lambda kv: -kv[1]),
    }


def overview_public():
    since = (TODAY - dt.timedelta(days=365)).isoformat()
    s = "https://api.github.com/search"
    commits = request(f"{s}/commits?q=author:{USER}+author-date:>={since}&per_page=100")
    repos = {}
    for it in commits["items"]:
        n = it["repository"]["full_name"]
        repos[n] = repos.get(n, 0) + 1
    prs = request(f"{s}/issues?q=author:{USER}+type:pr+created:>={since}&per_page=100")
    for it in prs["items"]:
        repos.setdefault(it["repository_url"].split("/repos/")[1], 0)
    return {
        "commits": commits["total_count"],
        "issues": request(f"{s}/issues?q=author:{USER}+type:issue+created:>={since}")["total_count"],
        "prs": prs["total_count"],
        "reviews": request(f"{s}/issues?q=reviewed-by:{USER}+type:pr+-author:{USER}+created:>={since}")["total_count"],
        "repos": sorted(repos.items(), key=lambda kv: -kv[1]),
    }


def load():
    stats = None
    if TOKEN:
        try:
            stats = fetch_graphql()
            stats["overview"] = overview_graphql()
        except Exception as e:  # keep the dashboard alive even if GraphQL hiccups
            print("GraphQL failed, using public fallback:", e)
            stats = None
    if stats is None:
        stats = fetch_public()
        stats["overview"] = overview_public()
    return stats


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

    # languages: only the full-stack / AI-ML ones, share measured from real code bytes
    langs = sorted(((n, v) for n, v in s["langs"].items() if n in CORE_LANGS), key=lambda kv: -kv[1])
    tot = sum(v for _, v in langs) or 1
    top = langs[:5]
    lx, lw = 888, 282
    p.append(f'<rect x="{lx}" y="30" width="{lw}" height="430" rx="14" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(f'<text x="{lx+18}" y="62" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">MOST USED LANGUAGES</text>')
    p.append(f'<text x="{lx+18}" y="{128+len(top)*41+6}" font-size="10.5" fill="{MU}" letter-spacing="1" class="m">FRAMEWORKS I BUILD WITH</text>')
    fx, fy = lx + 18, 128 + len(top) * 41 + 22
    for i, (n, col) in enumerate(FRAMEWORKS):
        w = len(n) * 6.9 + 26
        if fx + w > lx + lw - 18:
            fx, fy = lx + 18, fy + 30
        p.append(f'<g class="tile" style="animation-delay:{.6+i*.05:.2f}s"><rect x="{fx:.0f}" y="{fy}" width="{w:.0f}" height="24" rx="12" fill="#121a2e" stroke="#2a3756"/>'
                 f'<circle cx="{fx+12:.0f}" cy="{fy+12}" r="3.5" fill="{col}"/>'
                 f'<text x="{fx+21:.0f}" y="{fy+16}" font-size="11.5" fill="{TX}">{esc(n)}</text></g>')
        fx += w + 6
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


def frame_svg(W, H, body, style=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{SANS}">
<style>.m{{font-family:{MONO}}}
.in{{animation:in .7s ease-out both}}@keyframes in{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
{style}</style>
<defs><linearGradient id="fbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG}"/><stop offset="1" stop-color="{BG2}"/></linearGradient></defs>
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="22" fill="url(#fbg)" stroke="{BORDER}" stroke-width="1.5"/>
{body}
</svg>
'''


def render_overview(ov):
    """GitHub-style 'Activity overview': contributed repos + commits/issues/PRs/reviews cross chart."""
    W = 1200
    repos = ov["repos"]
    p = [f'<text x="40" y="52" font-size="12" fill="{OR}" letter-spacing="3" class="m">ACTIVITY OVERVIEW · LAST 12 MONTHS</text>']
    # sentence with repo names, wrapped by hand
    names = [n for n, _ in repos[:3]]
    rest = max(0, len(repos) - 3)
    tokens = [("Contributed to ", TX, 400)]
    for i, n in enumerate(names):
        sep = "," if i < len(names) - 1 or rest else ""
        tokens.append((n + sep + " ", BL, 700))
    if rest:
        tokens.append((f"and {rest} other repositor{'y' if rest == 1 else 'ies'}", TX, 400))
    elif not names:
        tokens = [("No public contributions in the last year yet.", MU, 400)]
    lines, line, width = [], [], 0
    for text, col, wt in tokens:
        for word in text.split(" "):
            if not word:
                continue
            w = len(word + " ") * (9.2 if wt == 700 else 8.6)
            if width + w > 520 and line:
                lines.append(line)
                line, width = [], 0
            line.append((word + " ", col, wt))
            width += w
    if line:
        lines.append(line)
    p.append(f'<g transform="translate(40,80)"><path d="M2 1 h14 a2 2 0 0 1 2 2 v16 a1 1 0 0 1 -1 1 h-13 a2 2 0 0 1 -2 -2z M5 16 h12" fill="none" stroke="{MU}" stroke-width="1.6"/></g>')
    for i, ln in enumerate(lines[:5]):
        spans = "".join(f'<tspan fill="{c}" font-weight="{w}">{esc(t)}</tspan>' for t, c, w in ln)
        p.append(f'<text x="72" y="{96+i*26}" font-size="16" xml:space="preserve">{spans}</text>')
    # top repositories by commits
    top = [(n, c) for n, c in repos[:5] if c > 0]
    mx = max([c for _, c in top] or [1])
    y0 = 96 + max(1, len(lines[:5])) * 26 + 30
    H = max(400, y0 + 22 + len(top) * 34 + 30)
    if top:
        p.append(f'<text x="40" y="{y0}" font-size="11" fill="{MU}" letter-spacing="1.5" class="m">TOP REPOSITORIES BY COMMITS</text>')
    for i, (n, c) in enumerate(top):
        y = y0 + 22 + i * 34
        short = n if len(n) <= 34 else n[:33] + "…"
        p.append(f'<g class="in" style="animation-delay:{.2+i*.1:.1f}s"><text x="40" y="{y+13}" font-size="13.5" fill="{TX}">{esc(short)}</text>'
                 f'<rect x="330" y="{y+3}" width="210" height="10" rx="5" fill="#1b2540"/>'
                 f'<rect x="330" y="{y+3}" width="{max(4, 210*c/mx):.0f}" height="10" rx="5" fill="{OR if i == 0 else BL}" class="grow"/>'
                 f'<text x="560" y="{y+13}" font-size="12.5" fill="{MU}" class="m">{c}</text></g>')
    p.append(f'<line x1="610" y1="40" x2="610" y2="{H-40}" stroke="{BORDER}"/>')
    # cross chart
    cx, cy, L = 900, H // 2 + 10, 130
    total = sum(ov[k] for k in ("commits", "issues", "prs", "reviews")) or 1
    pct = {k: ov[k] / total for k in ("commits", "issues", "prs", "reviews")}
    pts = [(cx, cy - L * pct["reviews"]), (cx + L * pct["issues"], cy), (cx, cy + L * pct["prs"]), (cx - L * pct["commits"], cy)]
    p.append(f'<g stroke="{BL}" stroke-opacity=".55" stroke-width="2"><line x1="{cx}" y1="{cy-L}" x2="{cx}" y2="{cy+L}"/><line x1="{cx-L}" y1="{cy}" x2="{cx+L}" y2="{cy}"/></g>')
    p.append(f'<g class="pop"><polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{OR}" fill-opacity=".28" stroke="{OR}" stroke-width="3" stroke-linejoin="round"/>'
             + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{BG}" stroke="{OR}" stroke-width="2.5"/>' for x, y in pts) + '</g>')
    lab = lambda v: f"{round(v*100)}%"
    p.append(f'<text x="{cx}" y="{cy-L-14}" font-size="14" fill="{TX}" text-anchor="middle">Code review <tspan fill="{MU}">{lab(pct["reviews"])}</tspan></text>')
    p.append(f'<text x="{cx}" y="{cy+L+26}" font-size="14" fill="{TX}" text-anchor="middle">Pull requests <tspan fill="{MU}">{lab(pct["prs"])}</tspan></text>')
    p.append(f'<text x="{cx-L-14}" y="{cy-4}" font-size="15" fill="{MU}" text-anchor="end">{lab(pct["commits"])}</text><text x="{cx-L-14}" y="{cy+16}" font-size="14" fill="{TX}" text-anchor="end">Commits</text>')
    p.append(f'<text x="{cx+L+14}" y="{cy-4}" font-size="15" fill="{MU}">{lab(pct["issues"])}</text><text x="{cx+L+14}" y="{cy+16}" font-size="14" fill="{TX}">Issues</text>')
    style = f'''.pop{{transform-origin:{cx}px {cy}px;animation:pop 1s cubic-bezier(.2,.9,.3,1.2) both .3s}}
@keyframes pop{{from{{transform:scale(0);opacity:0}}to{{transform:scale(1);opacity:1}}}}
.grow{{transform-box:fill-box;transform-origin:left;animation:gw 1s ease-out both .4s}}@keyframes gw{{from{{transform:scaleX(0)}}}}'''
    return frame_svg(W, H, "".join(p), style)


def render_pet(s):
    """A tiny Tamagotchi-style pet whose level, mood and badges come from real GitHub activity."""
    days = s["days"]
    total = sum(v for d, v in days.items() if dt.date.fromisoformat(d) <= TODAY)
    cur, _, longest, _ = streaks(days)
    today = days.get(TODAY.isoformat(), 0)
    week = sum(days.get((TODAY - dt.timedelta(days=i)).isoformat(), 0) for i in range(7))
    level = int((total / 10) ** 0.5) + 1
    lo, hi = 10 * (level - 1) ** 2, 10 * level ** 2
    xp = (total - lo) / (hi - lo)
    happy = min(100, 20 + cur * 16)
    energy = min(100, week * 8)
    if today > 0:
        mood, state = f"Ate {today} commit{'s' if today != 1 else ''} today. Feeling great!", "happy"
    elif cur > 0:
        mood, state = f"{cur}-day streak! Feed me a commit today.", "ok"
    else:
        mood, state = "Hungry... push a commit to wake me up!", "sleep"
    W, H = 1200, 340
    p = []
    # arena
    p.append(f'<rect x="30" y="30" width="540" height="280" rx="16" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(f'<text x="50" y="58" font-size="11" fill="{MU}" letter-spacing="2" class="m">COMMIT CRITTER · LIVE</text>')
    p.append(f'<rect x="31" y="262" width="538" height="47" fill="#0d1a2e"/><line x1="31" y1="262" x2="569" y2="262" stroke="#1f3a5c" stroke-width="2"/>')
    rnd_x = [70, 120, 190, 410, 470, 520]
    p.append("".join(f'<rect x="{x}" y="{255 - (i % 3) * 3}" width="6" height="{7 + (i % 3) * 3}" rx="1" fill="#1f5a3a"/>' for i, x in enumerate(rnd_x)))
    if state != "sleep":
        for i in range(3):
            p.append(f'<rect x="{292 + (i - 1) * 4}" y="70" width="14" height="14" rx="3" fill="{SNAKE_COLORS[2 + i]}" class="food" style="animation-delay:{i*1.1:.1f}s"/>')
    # pet
    eyes = (f'<path d="M-26 -6 q9 7 18 0 M8 -6 q9 7 18 0" stroke="{BG}" stroke-width="3" fill="none" stroke-linecap="round"/>' if state == "sleep" else
            f'<g class="blink"><ellipse cx="-17" cy="-6" rx="10" ry="12" fill="#fff"/><ellipse cx="17" cy="-6" rx="10" ry="12" fill="#fff"/>'
            f'<circle cx="-15" cy="-4" r="5.5" fill="{BG}"/><circle cx="19" cy="-4" r="5.5" fill="{BG}"/>'
            f'<circle cx="-13" cy="-7" r="2" fill="#fff"/><circle cx="21" cy="-7" r="2" fill="#fff"/></g>')
    mouth = (f'<ellipse cx="0" cy="17" rx="5" ry="3" fill="{BG}" opacity=".7"/>' if state == "sleep" else
             f'<path d="M-9 13 q9 10 18 0" stroke="{BG}" stroke-width="3" fill="none" stroke-linecap="round"/><ellipse cx="0" cy="17" rx="6" ry="5" fill="#7a2d00" class="chomp"/>')
    p.append(f'''<ellipse cx="300" cy="262" rx="50" ry="8" fill="#000" opacity=".35" class="shadow"/>
<g transform="translate(300,200)"><g class="{'snooze' if state == 'sleep' else 'bounce'}">
  <line x1="0" y1="-48" x2="0" y2="-66" stroke="{OR}" stroke-width="3"/><circle cx="0" cy="-70" r="6" fill="{BL}" class="glow"/>
  <path d="M-48 10 q0 -58 48 -58 q48 0 48 58 v36 q-8 10 -16 0 q-8 10 -16 0 q-8 10 -16 0 q-8 10 -16 0 q-8 10 -16 0 q-8 10 -16 0z" fill="url(#pet)"/>
  <ellipse cx="-14" cy="-34" rx="14" ry="6" fill="#fff" opacity=".25"/>
  {eyes}
  <ellipse cx="-31" cy="10" rx="7" ry="3.5" fill="#ff7a8a" opacity=".65"/><ellipse cx="31" cy="10" rx="7" ry="3.5" fill="#ff7a8a" opacity=".65"/>
  {mouth}
</g></g>''')
    if state == "sleep":
        p.append("".join(f'<text x="{352+i*12}" y="{150-i*12}" font-size="{16+i*4}" font-weight="700" fill="{MU}" class="z" style="animation-delay:{i*.7:.1f}s">z</text>' for i in range(3)))
    else:
        heart = "M0 4 c-6 -6 -12 -2 -12 3 c0 6 12 12 12 12 s12 -6 12 -12 c0 -5 -6 -9 -12 -3z"
        p.append("".join(f'<path d="{heart}" fill="{OR if i % 2 else "#ff7a8a"}" transform="translate({370 + i*26},{160 - i*8}) scale(.8)" class="heart" style="animation-delay:{i*.9:.1f}s"/>' for i in range(3)))
    p.append(f'<text x="550" y="58" font-size="11" fill="{BL if state != "sleep" else MU}" text-anchor="end" class="m">{"● awake" if state != "sleep" else "○ sleeping"}</text>')
    # stats card
    x0 = 600
    p.append(f'<text x="{x0+20}" y="60" font-size="12" fill="{OR}" letter-spacing="3" class="m">MY GITHUB PET</text>')
    p.append(f'<text x="{x0+20}" y="98" font-size="30" font-weight="800" fill="{TX}">Commit Critter <tspan fill="{BL}" font-size="20">Lv.{level}</tspan></text>')
    p.append(f'<text x="{x0+20}" y="126" font-size="15" fill="{MU}">{esc(mood)}</text>')
    bars = [("XP", xp, f"{total:,} / {hi:,}", OR), ("HAPPINESS", happy / 100, f"{cur}-day streak", "#ff7a8a"), ("ENERGY", energy / 100, f"{week} this week", BL)]
    for i, (lab, v, txt, col) in enumerate(bars):
        y = 156 + i * 40
        p.append(f'<g class="in" style="animation-delay:{.2+i*.12:.2f}s"><text x="{x0+20}" y="{y}" font-size="11" fill="{MU}" letter-spacing="1.5" class="m">{lab}</text>'
                 f'<text x="{x0+300}" y="{y}" font-size="12" fill="{TX}" text-anchor="end" class="m">{txt}</text>'
                 f'<rect x="{x0+20}" y="{y+8}" width="280" height="10" rx="5" fill="#1b2540"/>'
                 f'<rect x="{x0+20}" y="{y+8}" width="{max(6, 280*min(v, 1)):.0f}" height="10" rx="5" fill="{col}" class="grow"/></g>')
    badges = [("First commit", total >= 1), ("100 contribs", total >= 100), ("250 contribs", total >= 250),
              ("5-day streak", longest >= 5), ("10 repos", s["repos"] >= 10), ("10 PRs", s["prs"] >= 10),
              ("500 contribs", total >= 500), ("30-day streak", longest >= 30)]
    p.append(f'<text x="{x0+340}" y="156" font-size="11" fill="{MU}" letter-spacing="1.5" class="m">BADGES {sum(b for _, b in badges)}/{len(badges)}</text>')
    for i, (name, ok) in enumerate(badges):
        bx, by = x0 + 340 + (i % 2) * 112, 172 + (i // 2) * 32
        col = OR if ok else "#3a4560"
        p.append(f'<g class="in" style="animation-delay:{.4+i*.06:.2f}s"><rect x="{bx}" y="{by}" width="104" height="24" rx="12" fill="{col}" fill-opacity="{.12 if ok else .25}" stroke="{col}"/>'
                 f'<text x="{bx+52}" y="{by+16}" font-size="11" fill="{TX if ok else "#56607a"}" text-anchor="middle">{"✓ " if ok else ""}{esc(name)}</text></g>')
    p.append(f'<text x="{x0+20}" y="300" font-size="11" fill="#56607a" class="m">level · mood · badges are computed from real GitHub activity</text>')
    style = '''.bounce{animation:bounce 1.4s ease-in-out infinite}
@keyframes bounce{0%,100%{transform:translateY(0) scale(1,1)}45%{transform:translateY(-16px) scale(.97,1.03)}90%{transform:translateY(0) scale(1.05,.95)}}
.snooze{animation:sn 3s ease-in-out infinite}@keyframes sn{50%{transform:scale(1.03,.97)}}
.shadow{transform-box:fill-box;transform-origin:center;animation:sh 1.4s ease-in-out infinite}@keyframes sh{45%{transform:scaleX(.75);opacity:.2}}
.blink{transform-box:fill-box;transform-origin:center;animation:bl 4s infinite}@keyframes bl{0%,94%,100%{transform:scaleY(1)}97%{transform:scaleY(.1)}}
.glow{animation:gl 1.6s ease-in-out infinite alternate}@keyframes gl{to{opacity:.4}}
.chomp{transform-box:fill-box;transform-origin:center;animation:ch 1.1s steps(2) infinite}@keyframes ch{50%{transform:scaleY(.2)}}
.food{animation:food 3.3s ease-in infinite;opacity:0}@keyframes food{0%{transform:translateY(0);opacity:0}10%{opacity:1}55%{transform:translateY(138px);opacity:1}60%,100%{transform:translateY(138px);opacity:0}}
.heart{animation:ht 2.7s ease-out infinite;opacity:0}@keyframes ht{0%{opacity:0;transform-origin:center}20%{opacity:1}100%{opacity:0;translate:0 -40px}}
.z{animation:z 2.1s ease-in-out infinite;opacity:0}@keyframes z{30%{opacity:1}100%{opacity:0;translate:10px -20px}}
.grow{transform-box:fill-box;transform-origin:left;animation:gw 1s ease-out both .4s}@keyframes gw{from{transform:scaleX(0)}}'''
    defs = f'<defs><linearGradient id="pet" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffc27a"/><stop offset="1" stop-color="{OR}"/></linearGradient></defs>'
    return frame_svg(W, H, defs + "".join(p), style)


def wrap_snake(raw, days):
    """Frame Platane/snk's grid with a title, the real last-year count, month labels and a legend."""
    import re
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', raw).group(1).split()]
    inner = raw[raw.index(">", raw.index("<svg")) + 1: raw.rindex("</svg>")]
    cols = max(int(x) for x in re.findall(r'<rect class="c[^"]*" x="(\d+)"', raw)) // 16 + 1
    first = TODAY - dt.timedelta(days=(TODAY.weekday() + 1) % 7) - dt.timedelta(weeks=cols - 1)
    year_total = sum(v for d, v in days.items() if first <= dt.date.fromisoformat(d) <= TODAY)
    W, X0, Y0 = 1200, 80, 96
    sw = W - X0 - 40
    sc = sw / vb[2]
    sh = vb[3] * sc
    H = int(Y0 + sh + 24)
    col_x = lambda c: X0 + (2 + c * 16 - vb[0]) * sc
    row_y = lambda r: Y0 + (2 + r * 16 + 6 - vb[1]) * sc
    months, last = [], -9
    for c in range(cols):
        d = first + dt.timedelta(weeks=c)
        if (c == 0 or d.month != (d - dt.timedelta(weeks=1)).month) and c - last >= 3 and c < cols - 2:
            months.append(f'<text x="{col_x(c):.0f}" y="{row_y(0) - 22:.0f}" font-size="13" fill="{MU}">{d.strftime("%b")}</text>')
            last = c
    wd = "".join(f'<text x="{X0 - 6}" y="{row_y(r) + 4:.0f}" font-size="12" fill="#56607a" text-anchor="end">{n}</text>'
                 for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri")))
    legend_x = W - 40 - 5 * 18 - 44
    legend = (f'<text x="{legend_x - 8}" y="62" font-size="12" fill="{MU}" text-anchor="end">Less</text>'
              + "".join(f'<rect x="{legend_x + i * 18}" y="50" width="14" height="14" rx="3" fill="{c}"/>' for i, c in enumerate(SNAKE_COLORS))
              + f'<text x="{legend_x + 5 * 18 + 6}" y="62" font-size="12" fill="{MU}">More</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{SANS}">
<defs><linearGradient id="sbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG}"/><stop offset="1" stop-color="{BG2}"/></linearGradient></defs>
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="22" fill="url(#sbg)" stroke="{BORDER}" stroke-width="1.5"/>
<text x="40" y="44" font-size="12" fill="{OR}" letter-spacing="3" font-family="{MONO}">CONTRIBUTION SNAKE</text>
<text x="40" y="70" font-size="20" font-weight="700" fill="{TX}">{year_total:,} contributions in the last year</text>
{legend}{''.join(months)}{wd}
<svg x="{X0}" y="{Y0}" width="{sw:.0f}" height="{sh:.0f}" viewBox="{' '.join(f'{v:g}' for v in vb)}">{inner}</svg>
</svg>
'''


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    stats = load()
    with open(os.path.join(OUT, "github-dashboard.svg"), "w", encoding="utf-8") as f:
        f.write(render(stats))
    with open(os.path.join(OUT, "github-overview.svg"), "w", encoding="utf-8") as f:
        f.write(render_overview(stats["overview"]))
    with open(os.path.join(OUT, "github-pet.svg"), "w", encoding="utf-8") as f:
        f.write(render_pet(stats))
    snake = os.path.join(OUT, "github-snake.svg")
    if os.path.exists(snake):
        with open(snake, encoding="utf-8") as f:
            raw = f.read()
        if "CONTRIBUTION SNAKE" not in raw:
            with open(snake, "w", encoding="utf-8") as f:
                f.write(wrap_snake(raw, stats["days"]))
    print("dashboard written:", {k: v for k, v in stats.items() if k not in ("days", "langs", "overview")}, {k: v for k, v in stats["overview"].items() if k != "repos"}, len(stats["overview"]["repos"]), "repos")
