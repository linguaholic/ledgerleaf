# LedgerLeaf

A practice project: a tiny static marketing site for **LedgerLeaf**, a fictional accounting software brand,
run with a company-style SEO/GEO workflow and Claude Code agents.

Live site: https://linguaholic.github.io/ledgerleaf/

## How work happens here

1. Every change starts as a **GitHub issue**.
2. Work happens on a branch named `feat/...` or `fix/...`.
3. A **pull request** links the issue and fills in the template.
4. **Checks** run automatically (`seo-checks`). Red checks block the merge.
5. The **code owner** reviews and approves.
6. The owner **merges**. Agents never merge.
7. Merging to `main` **deploys** the site to GitHub Pages.

## Layout

| Path | What |
|---|---|
| `site/` | The website (plain HTML) |
| `checks/` | Deterministic SEO checks, run on every pull request |
| `.github/workflows/` | CI checks and deploy |

Run the checks locally:

```bash
python3 checks/seo_checks.py
```
