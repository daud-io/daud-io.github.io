"""Turn a wget mirror of the daud.io WordPress site into a self-contained static site.

usage: python3 -I staticify.py <mirror-dir> <out-dir>
"""
import os, re, shutil, sys, urllib.request
from urllib.parse import urlsplit, unquote
from bs4 import BeautifulSoup, Comment

SRC, OUT = sys.argv[1], sys.argv[2]
DISCORD = "https://discord.gg/5ak5FsU"
ORIGIN = re.compile(r"https?://(?:www\.)?daud\.io(/[^\s\"'()<>,]*)?")
DROP_PATH = re.compile(r"^/(wp-json|xmlrpc\.php|wp-admin|wp-login|wp-comments-post\.php|feed|comments/feed)")

if os.path.exists(OUT):
    for n in os.listdir(OUT):
        if n != ".git":
            p = os.path.join(OUT, n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
else:
    os.makedirs(OUT)
for n in os.listdir(SRC):
    s, d = os.path.join(SRC, n), os.path.join(OUT, n)
    shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)

# wget kept ?ver= query strings in some file names; static hosts can't serve those.
for root, _, files in os.walk(OUT):
    for name in files:
        if "?" in name:
            clean = os.path.join(root, name.split("?", 1)[0])
            if os.path.exists(clean):
                os.remove(os.path.join(root, name))
            else:
                os.rename(os.path.join(root, name), clean)

REL_ATTR = re.compile(r'((?:href|src|action|poster)=")(?![a-z]+:|#|/|data:)([^"]*)(")')

# wget saved two pages as flat .html files; give every page a dir/index.html,
# re-basing its relative links one level up.
for flat in ("reference-fish.html", "reference-flocking.html"):
    p = os.path.join(OUT, flat)
    d = os.path.join(OUT, flat[:-5])
    if os.path.exists(p):
        if not os.path.exists(os.path.join(d, "index.html")):
            os.makedirs(d, exist_ok=True)
            t = open(p, encoding="utf-8", errors="replace").read()
            t = REL_ATTR.sub(lambda m: m.group(1) + "../" + m.group(2) + m.group(3), t)
            t = re.sub(r"url\((['\"]?)(?![a-z]+:|data:|/|#)", lambda m: f"url({m.group(1)}../", t)
            t = re.sub(r'(srcset=")([^"]*)(")', lambda m: m.group(1) + ", ".join(
                ("../" + s.strip() if s.strip() and not re.match(r"[a-z]+:|/", s.strip()) else s.strip())
                for s in m.group(2).split(",")) + m.group(3), t)
            open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(t)
        os.remove(p)

# Scripts that only served removed features (social login, contact form,
# comments, admin bar, lazy loading).
DROP_SCRIPTS = re.compile(r"(miniorange|mo-social-login|mo_openid|contact-form-7|/swv\.|lazysizes|comment-reply|admin-bar|hoverintent)")

fetched, missing = set(), []


def local_target(path):
    """Map a site path to a file inside OUT, downloading assets when needed."""
    path = unquote(path)
    if path in ("", "/"):
        return "index.html"
    if path.startswith(("/wp-content/", "/wp-includes/")):
        rel = path.lstrip("/")
        dest = os.path.join(OUT, rel)
        if not os.path.exists(dest) and rel not in fetched:
            fetched.add(rel)
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                req = urllib.request.Request("https://daud.io" + path, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                    f.write(r.read())
            except Exception as e:
                missing.append((path, str(e)))
                return None
        return rel if os.path.exists(dest) else None
    cand = path.strip("/") + "/index.html"
    if os.path.exists(os.path.join(OUT, cand)):
        return cand
    return None


def rewrite_url(url, from_file):
    m = ORIGIN.fullmatch(url.strip())
    if not m:
        return url
    parts = urlsplit(url.strip())
    if DROP_PATH.match(parts.path):
        return None
    target = local_target(parts.path)
    if target is None:
        return url
    rel = os.path.relpath(os.path.join(OUT, target), os.path.dirname(from_file))
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")] or "./"
    return rel + ("#" + parts.fragment if parts.fragment else "")


def rewrite_css_urls(text, from_file, root=False):
    # root=True for CSS inside HTML: the theme puts url()s in CSS variables that
    # browsers resolve against the stylesheet using them, so only a site-root
    # path works from every page.
    def sub(m):
        if root:
            t = local_target(urlsplit(m.group(2)).path)
            new = "/" + t if t else None
        else:
            new = rewrite_url(m.group(2), from_file)
        return f"url({m.group(1)}{new or m.group(2)}{m.group(1)})"
    return re.sub(r"url\((['\"]?)(https?://(?:www\.)?daud\.io/[^'\")]+)\1\)", sub, text)


def rewrite_srcset(val, from_file):
    out = []
    for part in val.split(","):
        bits = part.strip().split()
        if bits:
            bits[0] = rewrite_url(bits[0], from_file) or bits[0]
            out.append(" ".join(bits))
    return ", ".join(out)


for root, _, files in os.walk(OUT):
    for name in files:
        f = os.path.join(root, name)
        if name.endswith(".css"):
            t = open(f, encoding="utf-8", errors="replace").read()
            open(f, "w", encoding="utf-8").write(rewrite_css_urls(t, f))
            continue
        if not name.endswith(".html"):
            continue
        soup = BeautifulSoup(open(f, encoding="utf-8", errors="replace").read(), "html.parser")

        # Lazy-loaded media: load directly instead of via the cache plugin's JS.
        for el in soup.select("[data-src], [data-srcset]"):
            if el.get("data-src"):
                el["src"] = el["data-src"]
                del el["data-src"]
            if el.get("data-srcset"):
                el["srcset"] = el["data-srcset"]
                del el["data-srcset"]
            if el.get("class"):
                el["class"] = [c for c in el["class"] if c != "lazyload"]

        # Google Tag Manager / analytics.
        for s in soup.find_all(["script", "noscript"]):
            txt = str(s)
            if "googletagmanager" in txt or "dataLayer" in txt or "gtag(" in txt:
                s.decompose()
        for l in soup.find_all("link", href=re.compile("googletagmanager")):
            l.decompose()
        for s in soup.find_all("script", src=DROP_SCRIPTS):
            s.decompose()
        for l in soup.find_all("link", href=DROP_SCRIPTS):
            l.decompose()
        for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
            c.extract()

        # WordPress API / feed / editor discovery links.
        for l in soup.find_all("link"):
            rel = " ".join(l.get("rel") or [])
            href = l.get("href") or ""
            if rel in ("EditURI", "wlwmanifest", "https://api.w.org/", "shortlink", "pingback") \
                    or (rel == "alternate" and ("json" in (l.get("type") or "") or "oembed" in href or "rss" in (l.get("type") or ""))):
                l.decompose()

        # Comment forms (posts) and the blog search box need a server.
        for el in soup.select("#respond, .comment-respond, .comments-area"):
            el.decompose()
        for form in soup.find_all("form"):
            if form.find("input", attrs={"name": "s"}):
                (form.find_parent(class_=re.compile("widget|search")) or form).decompose()

        # Contact form -> point people at Discord.
        for form in soup.select("form.wpcf7-form"):
            wrap = form.find_parent(class_="wpcf7") or form
            p = soup.new_tag("p")
            p.append("The contact form is retired. The best way to reach us is on ")
            a = soup.new_tag("a", href=DISCORD)
            a.string = "Discord"
            p.append(a)
            p.append(".")
            wrap.replace_with(p)

        # Point everything at local copies.
        for el in soup.find_all(True):
            for attr in ("href", "src", "action", "poster"):
                if el.get(attr):
                    new = rewrite_url(el[attr], f)
                    if new is None:
                        if el.name == "a":
                            el[attr] = "./" if attr == "href" else el[attr]
                        else:
                            del el[attr]
                    else:
                        el[attr] = new
            if el.get("srcset"):
                el["srcset"] = rewrite_srcset(el["srcset"], f)
            if el.get("style") and "url(" in el["style"]:
                el["style"] = rewrite_css_urls(el["style"], f, root=True)
        for st in soup.find_all("style"):
            if st.string and "url(" in st.string:
                st.string = rewrite_css_urls(st.string, f, root=True)

        open(f, "w", encoding="utf-8").write(str(soup))

# Final pass: local links must name real files without query strings;
# fetch any WordPress asset that wget didn't save.
def fix_local(url, from_file):
    u = url.strip()
    if not u or re.match(r"^([a-z]+:|#|//|/)", u):
        return url
    frag = "#" + u.rsplit("#", 1)[1] if "#" in u else ""
    path = re.split(r"\?|%3F|#", u, maxsplit=1, flags=re.I)[0]
    if not path:
        return frag
    target = os.path.normpath(os.path.join(os.path.dirname(from_file), unquote(path)))
    if not os.path.exists(target) and target.endswith(".html") \
            and os.path.exists(os.path.join(target[:-5], "index.html")):
        return path[:-5] + "/" + frag  # flat page we moved into a folder
    if not os.path.exists(target):
        rel = os.path.relpath(target, OUT)
        if rel.startswith(("wp-content/", "wp-includes/")):
            local_target("/" + rel)
    return path + frag


def css_to_root(text, from_file):
    """Relative url()s in page CSS -> site-root paths (see rewrite_css_urls)."""
    def sub(m):
        u = fix_local(m.group(2), from_file)
        p = os.path.normpath(os.path.join(os.path.dirname(from_file), unquote(u)))
        return f"url({m.group(1)}/{os.path.relpath(p, OUT)}{m.group(1)})"
    return re.sub(r"url\((['\"]?)(?![a-z]+:|data:|/|#)([^'\")]+)\1\)", sub, text)


for root, _, files in os.walk(OUT):
    for name in files:
        if not name.endswith(".html"):
            continue
        f = os.path.join(root, name)
        soup = BeautifulSoup(open(f, encoding="utf-8", errors="replace").read(), "html.parser")
        for el in soup.find_all(True):
            for attr in ("href", "src", "poster"):
                if el.get(attr):
                    el[attr] = fix_local(el[attr], f)
            if el.get("srcset"):
                el["srcset"] = ", ".join(
                    " ".join([fix_local(b.split()[0], f)] + b.split()[1:])
                    for b in el["srcset"].split(",") if b.strip())
            if el.get("style") and "url(" in el["style"]:
                el["style"] = css_to_root(el["style"], f)
        for st in soup.find_all("style"):
            if st.string and "url(" in st.string:
                st.string = css_to_root(st.string, f)
        open(f, "w", encoding="utf-8").write(str(soup))


def fix_css(text, from_file):
    return re.sub(r"url\((['\"]?)(?![a-z]+:|data:|/|#)([^'\")]+)\1\)",
                  lambda m: f"url({m.group(1)}{fix_local(m.group(2), from_file)}{m.group(1)})", text)


# Assets pulled in by rewritten CSS may themselves reference more assets.
for root, _, files in os.walk(OUT):
    for name in files:
        if name.endswith(".css"):
            f = os.path.join(root, name)
            t = open(f, encoding="utf-8", errors="replace").read()
            open(f, "w", encoding="utf-8").write(fix_css(rewrite_css_urls(t, f), f))

# No CNAME yet: it would make Pages redirect the preview to the live daud.io.
open(os.path.join(OUT, ".nojekyll"), "w").write("")
print("downloaded", len(fetched) - len(missing), "assets; missing:", len(missing))
for m in missing[:20]:
    print("  missing", m)
