#!/usr/bin/env bash
# S11 — publish dist/dataset to the three places the dataset lives.
#   scripts/publish.sh dry-run            print what the others would do
#   scripts/publish.sh zenodo             create a DRAFT deposition (sandbox by default)
#   scripts/publish.sh release v0.1.0     create a DRAFT GitHub release
#   scripts/publish.sh hf user/seafolk-danish-ais
#
# ORDER, first time through:
#   1. scripts/publish.sh dry-run
#   2. ZENODO_TOKEN=… scripts/publish.sh zenodo            (sandbox — rehearsal)
#   3. scripts/publish.sh release v0.1.0                   (draft; publish by hand)
#   4. HF_TOKEN=… scripts/publish.sh hf <user>/seafolk-danish-ais
#      — creates the dataset PRIVATE (a typo in the repo id must not create a
#        public dataset); flip it to public in the Hugging Face UI once the
#        card and the file list look right
#   5. ZENODO_LIVE=1 ZENODO_TOKEN=… scripts/publish.sh zenodo, then press
#      Publish in the Zenodo web UI yourself
#   6. write the concept DOI into docs/dataset-card.md, CITATION.cff, README.md
#      and the Hugging Face card, and commit.
#
# Nothing here publishes anything irreversibly. The GitHub release is a draft,
# the Zenodo deposition is never POSTed to /actions/publish (a DOI is one-way),
# and the Hugging Face upload is the only step that is live — it is also the
# only one that can be overwritten later.
#
# Every sub-command refuses to run unless scripts/export.sh has completed
# successfully, which it signals by touching dist/dataset/.tests-passed after
# scripts/test_export.py passes.
set -euo pipefail
cd "$(dirname "$0")/.."

DIST=dist/dataset
CARD=docs/dataset-card.md
REPO_URL=https://github.com/Maksim-Burtsev/seafolk

require_export() {
    [[ -d $DIST ]] || {
        echo "publish: $DIST does not exist — run scripts/export.sh first" >&2
        exit 1
    }
    [[ -f $DIST/.tests-passed ]] || {
        echo "publish: $DIST/.tests-passed is missing — scripts/test_export.py has" >&2
        echo "         not passed for the files on disk. Run scripts/export.sh." >&2
        exit 1
    }
    # The marker says "the tests passed", not "the tests passed on THESE
    # files". `scripts/ch.sh sql/70_export.sql` rewrites the parquet in place
    # and leaves the marker standing, so a file newer than the marker is a
    # file no test has seen.
    local newer; newer=$(find "$DIST" -newer "$DIST/.tests-passed" -type f)
    [[ -z $newer ]] || {
        echo "publish: newer than $DIST/.tests-passed, so untested:" >&2
        echo "$newer" | sed 's/^/           /' >&2
        echo "         Re-run scripts/export.sh." >&2
        exit 1
    }
}

files() { ls "$DIST"/*.parquet "$DIST"/README.md; }

# --include, so the .tests-passed marker (and anything else local) never goes
# up, and --private, so a mistyped repo id cannot create a PUBLIC dataset. The
# repo is flipped to public by hand in the Hugging Face UI once it looks right;
# --private is ignored for a repo that already exists.
HF_ARGS=(--repo-type dataset --private --include '*.parquet' --include 'README.md')

# The card MINUS its YAML front matter. Hugging Face needs that front matter; a
# GitHub release does NOT strip it and would render it as the first lines of the
# release notes, so the release gets this copy and not $CARD itself.
card_body() {
    python3 - "$CARD" <<'PY'
import re, sys
print(re.sub(r'(?s)^---\n.*?\n---\n', '', open(sys.argv[1]).read()), end='')
PY
}

# The first paragraph of the card, as Zenodo's description: PLAIN TEXT. Zenodo
# renders Markdown as literal characters, so the card's [Seafolk](url) link is
# spelled out as "Seafolk (url)" here.
first_paragraph() {
    card_body | python3 -c '
import re, sys
body = re.sub(r"(?m)^#.*$", "", sys.stdin.read()).strip()
para = body.split("\n\n")[0].replace("\n", " ")
print(re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 (\2)", para))'
}

cmd_release() {
    local tag=$1
    require_export
    local notes; notes=$(mktemp -t seafolk-release-notes)
    card_body > "$notes"
    gh release create "$tag" --draft \
        --title "Seafolk — Danish AIS aggregates $tag" \
        --notes-file "$notes" \
        $(files)
    rm -f "$notes"
}

cmd_hf() {
    local repo_id=$1
    require_export
    [[ -n ${HF_TOKEN:-} ]] || {
        echo "publish: HF_TOKEN is not set — create a write token at" >&2
        echo "         https://huggingface.co/settings/tokens and export it" >&2
        exit 1
    }
    # `huggingface-cli` was renamed to `hf` in huggingface_hub 0.34; used once,
    # by a human, so it is not a project dependency (docs/DECISIONS.md).
    uv run --with huggingface_hub hf upload "${HF_ARGS[@]}" "$repo_id" "$DIST" .
}

cmd_zenodo() {
    require_export
    [[ -n ${ZENODO_TOKEN:-} ]] || {
        echo "publish: ZENODO_TOKEN is not set — get one at" >&2
        echo "         https://sandbox.zenodo.org/account/settings/applications/tokens/new/" >&2
        echo "         (or https://zenodo.org/... for ZENODO_LIVE=1)" >&2
        exit 1
    }
    local base; base=$(zenodo_base)
    echo "publish: Zenodo at $base"

    local dep; dep=$(curl -sSf -X POST "$base/api/deposit/depositions" \
        -H "Authorization: Bearer $ZENODO_TOKEN" \
        -H 'Content-Type: application/json' -d '{}')
    local id bucket doi concept
    id=$(json_get "$dep" id)
    bucket=$(json_get "$dep" links.bucket)
    doi=$(json_get "$dep" metadata.prereserve_doi.doi)
    # The concept DOI is NOT this version's DOI with its last component cut
    # off: it is built from `conceptrecid`, the id that groups every version of
    # the deposition (developers.zenodo.org, read 2026-09-12). Zenodo's prefix
    # is 10.5281; the sandbox mints 10.5072.
    concept=$(json_get "$dep" conceptrecid)
    echo "publish: deposition $id created, prereserved DOI $doi"

    local f
    for f in $(files); do
        echo "publish: uploading $(basename "$f") ($(du -h "$f" | cut -f1))"
        curl -sSf -o /dev/null -X PUT "$bucket/$(basename "$f")" \
            -H "Authorization: Bearer $ZENODO_TOKEN" --upload-file "$f"
    done

    curl -sSf -o /dev/null -X PUT "$base/api/deposit/depositions/$id" \
        -H "Authorization: Bearer $ZENODO_TOKEN" \
        -H 'Content-Type: application/json' \
        -d "$(zenodo_metadata)"

    echo
    echo "publish: draft ready, NOT published — open it, check it, press Publish:"
    echo "  $base/deposit/$id"
    local prefix=10.5072
    [[ ${ZENODO_LIVE:-} == 1 ]] && prefix=10.5281
    echo "publish: concept DOI once published: $prefix/zenodo.$concept  (this version: $doi)"
}

zenodo_base() {
    if [[ ${ZENODO_LIVE:-} == 1 ]]; then echo https://zenodo.org
    else echo https://sandbox.zenodo.org; fi
}

# One field out of a JSON document, by dotted path. python3 stdlib, so the
# script has no jq dependency.
json_get() {
    python3 -c '
import json, sys
o = json.loads(sys.argv[1])
for k in sys.argv[2].split("."):
    o = o[k]
print(o)' "$1" "$2"
}

zenodo_metadata() {
    python3 - "$(first_paragraph)" "$REPO_URL" <<'PY'
import json, sys
description, repo = sys.argv[1], sys.argv[2]
print(json.dumps({"metadata": {
    "title": "Seafolk — Danish AIS aggregates",
    "upload_type": "dataset",
    "version": "0.1.0",
    "creators": [{"name": "Burtsev, Maksim"}],
    "description": description,
    "license": "cc-by-4.0",
    "keywords": ["AIS", "maritime", "Denmark", "leisure boating", "ferries", "H3"],
    "related_identifiers": [
        {"identifier": repo, "relation": "isSupplementTo", "resource_type": "software"},
    ],
}}))
PY
}

cmd_dry_run() {
    require_export
    echo "files ($(files | wc -l | tr -d ' ')), $(du -sh "$DIST" | cut -f1) total:"
    ls -lh $(files) | awk '{printf "  %8s  %s\n", $5, $9}'
    echo
    echo "release:  gh release create <tag> --draft --title 'Seafolk — Danish AIS aggregates <tag>' \\"
    echo "              --notes-file <$CARD minus its YAML front matter> $(files | tr '\n' ' ')"
    echo
    echo "hf:       uv run --with huggingface_hub hf upload $(printf '%q ' "${HF_ARGS[@]}")<repo_id> $DIST ."
    echo "          HF_TOKEN ${HF_TOKEN:+set}${HF_TOKEN:-UNSET}"
    echo
    echo "zenodo:   POST $(zenodo_base)/api/deposit/depositions"
    echo "          PUT  <bucket>/<name> for each file above"
    echo "          PUT  $(zenodo_base)/api/deposit/depositions/<id> with:"
    zenodo_metadata | python3 -m json.tool | sed 's/^/            /'
    echo "          ZENODO_TOKEN ${ZENODO_TOKEN:+set}${ZENODO_TOKEN:-UNSET}, never POSTs /actions/publish"
    echo "          concept DOI printed from the deposition's conceptrecid, not from the version DOI"
}

case "${1:-}" in
    dry-run) cmd_dry_run ;;
    release) cmd_release "${2:?usage: publish.sh release <tag>}" ;;
    hf)      cmd_hf      "${2:?usage: publish.sh hf <repo_id>}" ;;
    zenodo)  cmd_zenodo ;;
    *) sed -n '2,9p' "$0" >&2; exit 2 ;;
esac
