# daud.io

Static copy of the daud.io website. It was a WordPress site on SiteGround until
2026-10; it's now plain HTML served by GitHub Pages.

The game itself lives elsewhere (play.daud.io, us.daud.io; see
`daud-io/daud` and `daud-io/daud-hosting`). This repo is only the landing pages,
FAQ, release notes and blog posts.

## Editing

Edit the HTML files directly and push to `main`. Pages redeploys in about a minute.
Each page is `<slug>/index.html`, and images are under `wp-content/uploads/`.

What changed from the WordPress version:
- The contact form is gone; it points to Discord instead.
- Comment forms, search, social login, newsletter widgets and Google Tag
  Manager are removed.
- Lazy-loaded images load directly.

`tools/staticify.py` is the script that converted the wget mirror. It's kept
for reference; you don't need it to edit the site.
