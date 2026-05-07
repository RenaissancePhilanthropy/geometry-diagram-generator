"""Update Croissant URLs to point at an anonymous.4open.science mirror.

After uploading geogenbench_supp_v1.zip to anonymous.4open.science and
receiving an anonymized repo URL like:

    https://anonymous.4open.science/r/geogenbench-anon-2026-ABCD

run this script with the repo-id (the part after `/r/`):

    python paper/scripts/update_croissant_urls.py \\
        --repo-id geogenbench-anon-2026-ABCD \\
        --output tmp/submission/croissant.json

The script:
  - Reads the canonical Croissant from benchmark/definitions/croissant.json
  - Rewrites the top-level `url` and the `distribution[].contentUrl`
    fields to point at the anonymous mirror
  - Writes the updated file to --output
  - Validates the result via mlcroissant (best-effort; fetches over the
    network)

Use the resulting file as the Croissant metadata for the OpenReview
submission.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "benchmark" / "definitions" / "croissant.json"


def update(repo_id: str, src_path: Path, out_path: Path) -> dict:
    base = f"https://anonymous.4open.science/r/{repo_id}"
    api_base = f"https://anonymous.4open.science/api/repo/{repo_id}/file"

    c = json.loads(src_path.read_text())

    # 1) Top-level url -> the anon mirror landing page
    c["url"] = base

    # 2) Distribution contentUrls -> per-file API URLs
    for fo in c.get("distribution", []):
        fid = fo.get("@id") or fo.get("name") or ""
        if fid.endswith(".jsonl"):
            fo["contentUrl"] = f"{api_base}/{fid}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(c, indent=2, ensure_ascii=False))
    return c


def validate(out_path: Path) -> str:
    try:
        import mlcroissant as mlc  # type: ignore
    except ImportError:
        return "mlcroissant not installed; skipping validation. (pip install mlcroissant)"
    ds = mlc.Dataset(jsonld=str(out_path))
    issues = ds.metadata.ctx.issues.report()
    return issues if issues else "OK"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo-id", required=True,
        help="anonymous.4open.science repo-id (the part after /r/, e.g. geogenbench-anon-2026-ABCD)",
    )
    p.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "tmp" / "submission" / "croissant.json",
        help="Where to write the updated Croissant file",
    )
    p.add_argument(
        "--source", type=Path, default=SRC,
        help="Source Croissant file (default: benchmark/definitions/croissant.json)",
    )
    args = p.parse_args()

    if not args.source.exists():
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        return 2

    c = update(args.repo_id, args.source, args.output)

    print(f"Updated Croissant file written to: {args.output}")
    print(f"  url:                  {c['url']}")
    for fo in c.get("distribution", []):
        if fo.get("contentUrl"):
            print(f"  contentUrl:           {fo['contentUrl']}")
    print()
    print(f"Validation: {validate(args.output)}")
    print()
    print("Next steps:")
    print(f"  1. Drag {args.output} into https://huggingface.co/spaces/MLCommons/croissant-validator")
    print(f"     to confirm it validates against the official 1.1 spec.")
    print(f"  2. Submit on OpenReview with the dataset URL ({c['url']})")
    print(f"     plus the updated Croissant file ({args.output}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
