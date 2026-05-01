#!/usr/bin/env python
"""Render a recipe's worked example to SVG for visual verification.

Combines the recipe's ``setup`` section with its ``example.construction``,
lowers to DiagramIR, and renders via the SVG renderer (no Docker required).

Usage:
    .venv/bin/python docs/render_recipe.py <recipe_name> [--catalog default,genexam]
    .venv/bin/python docs/render_recipe.py rectilinear_polygon --catalog genexam
    .venv/bin/python docs/render_recipe.py incircle --catalog default

Output is saved to /tmp/<recipe_name>.svg (or --out path).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recipe.catalog import load_recipe
from recipe.dsl import RecipeDSL
from recipe.lower import lower_to_ir
from ir.to_sympy import compile_defs
from ir.to_svg import ir_to_svg


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("recipe", help="Recipe name, e.g. rectilinear_polygon")
    p.add_argument(
        "--catalog", default="default,genexam",
        help="Catalog(s) to search (comma-separated). Default: 'default,genexam'",
    )
    p.add_argument(
        "--out", default=None,
        help="Output SVG path (default: /tmp/<recipe>.svg)",
    )
    args = p.parse_args()

    recipe = load_recipe(args.recipe, catalog=args.catalog)
    print(f"Loaded recipe: {recipe.name!r} from catalog search: {args.catalog!r}")

    # Combine setup (prerequisite objects) + example construction
    combined_construction = recipe.setup + recipe.example.get("construction", [])
    mode = recipe.example.get("mode", "abstract")
    annotations = recipe.example.get("annotations", {})

    combined_dict = {
        "mode": mode,
        "construction": combined_construction,
        "annotations": annotations,
    }
    dsl = RecipeDSL.model_validate(combined_dict)
    print(f"  Construction ops: {len(dsl.construction)}")

    ir = lower_to_ir(dsl)
    print(f"  IR defs: {len(ir.define)}, render ops: {len(ir.render)}")

    sym = compile_defs(ir)
    svg = ir_to_svg(ir, sym)
    print(f"  SVG size: {len(svg):,} bytes")

    out_path = args.out or f"/tmp/{args.recipe}.svg"
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Saved: {out_path}")
    print("Open in a browser to inspect visually.")


if __name__ == "__main__":
    main()
