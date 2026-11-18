#!/usr/bin/env bash
# Publish RadiusStats Europe to GitHub Pages ("Deploy from a branch": gh-pages, / root).
#
#   scripts/deploy-gh-pages.sh --dry-run   # build the app and assemble site/ (app + data), push nothing
#   scripts/deploy-gh-pages.sh             # same, then (after a y/N prompt) force-push site/ to gh-pages
#
# The site is the app build (app/dist) plus the validated data build (data/build) under data/.
# Every deploy replaces the gh-pages branch with ONE new commit (orphan, force-push), so the ~150 MB of
# data does not pile up in the branch history. Your main branch is not touched.
# Env: REMOTE (default origin), BRANCH (default gh-pages), YES=1 to skip the prompt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-gh-pages}"
SITE="$ROOT/site"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

die() { echo "error: $*" >&2; exit 1; }

# --- 1. checks -----------------------------------------------------------------------------------
[ -f "$ROOT/data/build/manifest.json" ] || die "no data build: run pipeline/run.sh build first"
[ -f "$ROOT/data/build/validation_report.json" ] || die "data build not validated: run pipeline/run.sh validate"
node -e '
  const v = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
  const failed = v.checks.filter((c) => !c.ok).length;
  if (failed) { console.error(`validation_report.json: ${failed} failed checks`); process.exit(1); }
  console.log(`data: ${v.checks.length} validation checks passed`);
' "$ROOT/data/build/validation_report.json" || die "fix the failed validation checks before deploying"
if [ "$DRY" = 0 ]; then
  git -C "$ROOT" remote get-url "$REMOTE" >/dev/null 2>&1 || die "no git remote '$REMOTE' (git remote add origin https://github.com/<user>/<repo>.git)"
fi

# --- 2. build the app ----------------------------------------------------------------------------
(cd "$ROOT/app" && npm run build)

# --- 3. assemble the site ------------------------------------------------------------------------
rm -rf "$SITE"
mkdir -p "$SITE/data"
cp -R "$ROOT/app/dist/." "$SITE/"
cp -R "$ROOT/data/build/." "$SITE/data/"
touch "$SITE/.nojekyll"      # serve files as they are (no Jekyll processing)
big=$(find "$SITE" -type f -size +95M)
[ -z "$big" ] || die "files over GitHub's 100 MB limit: $big"
echo "site: $(du -sh "$SITE" | cut -f1) in $SITE"

if [ "$DRY" = 1 ]; then
  echo "dry run: nothing pushed. Preview: node scripts/serve-site.mjs  ->  http://localhost:4173/radiusstats-europe/"
  exit 0
fi

# --- 4. publish ----------------------------------------------------------------------------------
URL="$(git -C "$ROOT" remote get-url "$REMOTE")"
REV="$(git -C "$ROOT" rev-parse --short HEAD)"
if [ "${YES:-0}" != 1 ]; then
  read -r -p "Replace branch '$BRANCH' on $URL with this site (commit $REV)? [y/N] " ok
  [ "$ok" = "y" ] || [ "$ok" = "Y" ] || { echo "not pushed"; exit 1; }
fi
rm -rf "$SITE/.git"
git -C "$SITE" init -q -b "$BRANCH"
git -C "$SITE" add -A
git -C "$SITE" commit -q -m "Deploy RadiusStats Europe from $REV"
git -C "$SITE" push -f "$URL" "$BRANCH:$BRANCH"
rm -rf "$SITE/.git"
echo "pushed. When GitHub Pages has finished (Actions tab, 'pages build and deployment'), check it with:"
echo "  node scripts/check-deploy.mjs https://<user>.github.io/<repo>/"
