#!/usr/bin/env python3
"""Probe OpenAI image models for everything generate_image and generate_character rely on.

Why this exists: twice now a vendor capability that was probed and verified
was withdrawn later without the docs following. Gemini's responseFormat
aspect-ratio field was the first; gpt-image-2's transparent background, gone
in October 2026, was the second, and every illustrated video failed until a
release. Run this before adding a model to OPENAI_IMAGE_MODELS, and whenever
character generation starts failing.

Checked per model, each a real call:
  * generations, transparent, 1024x1024   (a character's first asset)
  * generations, transparent, 1088x1920   (CHARACTER_SIZES portrait, OPENAI_SIZE_BY_ASPECT 9:16)
  * generations, transparent, 1920x1088   (landscape)
  * edits, transparent, with a reference  (every later pose)
  * edits + input_fidelity                (expected REFUSED — mcp/server.py never sends it)

Each line shows the status, the REAL pixel size and the alpha range of the
returned image. Transparency is proven by alpha reaching 0, never by the
response echoing `background: transparent`.

A 403 "does not have access to model" means the key's OpenAI *project* has not
been granted the model; access is per project, and GET /v1/models lists models a
project still cannot call.

COSTS MONEY: about five images per model at medium quality, a few cents each.

    OPENAI_API_KEY=... python scripts/probe_openai_images.py [model ...]

With no models given, probes the shipped catalog (mcp/server.py's
OPENAI_IMAGE_MODELS). The key is read from the environment and never printed.
"""
import argparse
import base64
import io
import os
import sys

import httpx
from PIL import Image

GENERATIONS = "https://api.openai.com/v1/images/generations"
EDITS = "https://api.openai.com/v1/images/edits"
PROMPT = "a plain black circle, no shadow, no ground, no scenery"

# Keep in sync: mcp/server.py OPENAI_IMAGE_MODELS (the default when no model is named).
CATALOG = ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]


def describe(resp) -> tuple:
    """(one-line summary, PNG bytes or None)."""
    if resp.status_code == 401:
        # OpenAI's 401 echoes a masked slice of the key — never print it.
        return "401 the key was rejected", None
    try:
        body = resp.json()
    except ValueError:
        return f"{resp.status_code} non-JSON body", None
    if resp.status_code != 200:
        msg = (body.get("error") or {}).get("message", "")
        return f"{resp.status_code} {msg[:110]}", None
    raw = base64.b64decode(body["data"][0]["b64_json"])
    image = Image.open(io.BytesIO(raw))
    alpha = image.getchannel("A").getextrema() if "A" in image.getbands() else None
    tokens = (body.get("usage") or {}).get("total_tokens")
    return (f"200 {image.size[0]}x{image.size[1]} {image.mode} alpha={alpha} "
            f"tokens={tokens}"), raw


def probe(model: str, headers: dict) -> None:
    def gen(size):
        return httpx.post(GENERATIONS, headers=headers, timeout=300,
                          json={"model": model, "prompt": PROMPT, "size": size,
                                "background": "transparent"})

    def edit(reference, **extra):
        return httpx.post(EDITS, headers=headers, timeout=300,
                          data={"model": model, "prompt": PROMPT, "size": "1024x1024",
                                "background": "transparent", **extra},
                          files=[("image[]", ("ref.png", reference, "image/png"))])

    line, reference = describe(gen("1024x1024"))
    print(f"{model:24} gen 1024x1024 transparent   {line}", flush=True)
    if reference is None:
        return  # no access, or no transparency: nothing further is worth paying for
    for size in ("1088x1920", "1920x1088"):
        print(f"{model:24} gen {size} transparent   {describe(gen(size))[0]}", flush=True)
    print(f"{model:24} edits transparent + ref    {describe(edit(reference))[0]}", flush=True)
    print(f"{model:24} edits + input_fidelity     "
          f"{describe(edit(reference, input_fidelity='high'))[0]}  (expected: 400)", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="*", default=CATALOG)
    args = parser.parse_args(argv)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2
    headers = {"Authorization": f"Bearer {key}"}
    for model in args.models:
        probe(model, headers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
