# ShowMe-Bench labelling progress (counts only)

This repository publishes one page: how far each labelling code (X, Y, Z) has got in the ShowMe-Bench S2 round.

- `reports/X.json`, `Y.json`, `Z.json`: counts sent by each member's labelling kit when they click "Update my
  progress" (products done, requests done, minutes). The kit refuses to send anything else. Names, product ids,
  photos and labels are not part of what the kit sends.
- `gate.json`: lock counts from the project owner.
- `build.py` + `template.html` build the page; `.github/workflows/pages.yml` runs them **from a pinned commit**
  (`SITE_REF`) and publishes to GitHub Pages. Report lines that are not exactly a counts line are skipped and never
  reach the page. Files in this repository are public, so the build cannot hide what was committed; the kit's own
  check is what keeps anything else from being sent.

The research project itself is private.
