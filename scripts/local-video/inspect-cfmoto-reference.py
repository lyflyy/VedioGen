"""Collect version-specific official image references without confirming or importing them."""

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw, ImageOps

from vediogen_api.public_media import fetch_public_image
from vediogen_api.manufacturer_catalog import (GLOBAL_MODELS, ZXMOTO_MODELS, catalog_from_html,
    global_catalog_from_html, zxmoto_catalog_from_html, fetch_zxmoto_page)


def main():
    parser = argparse.ArgumentParser()
    model = parser.add_mutually_exclusive_group(required=True)
    model.add_argument("--slug")
    model.add_argument("--global-model", choices=GLOBAL_MODELS)
    model.add_argument("--zxmoto-model", choices=ZXMOTO_MODELS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--max-images", type=int, choices=range(1, 37), default=24)
    args = parser.parse_args()
    if args.slug and not re.fullmatch(r"[a-zA-Z0-9-]{1,50}", args.slug):
        raise ValueError("Invalid official vehicle slug")
    if args.zxmoto_model:
        name, route = ZXMOTO_MODELS[args.zxmoto_model]
        source = "https://www.zxmoto.com" + route
        catalog = zxmoto_catalog_from_html(fetch_zxmoto_page(route), source, name)
    else:
        source = ("https://www.cfmoto.com" + GLOBAL_MODELS[args.global_model][1] if args.global_model
                  else f"https://www.cfmoto.com/motorcycles/{args.slug}")
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            response = client.get(source)
            response.raise_for_status()
        catalog = (global_catalog_from_html(response.text, source, GLOBAL_MODELS[args.global_model][0])
                   if args.global_model else catalog_from_html(response.text, source))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.contact_sheet:
        candidates = [item for item in catalog["candidates"] if item.get("width") is None or item["width"] >= 900][:args.max_images]
        if not candidates:
            raise ValueError("No official reference images found")
        sheet = Image.new("RGB", (1000, ((len(candidates) + 3) // 4) * 185), "#eeeeee")
        draw = ImageDraw.Draw(sheet)
        for offset, candidate in enumerate(candidates):
            x, y = offset % 4 * 250, offset // 4 * 185
            try:
                content = fetch_public_image(candidate["imageUrl"])
                with Image.open(io.BytesIO(content)) as image:
                    image.load()
                    candidate.update(width=image.width, height=image.height)
                    preview = image.convert("RGBA")
                    background = Image.new("RGBA", preview.size, "#eeeeee")
                    background.alpha_composite(preview)
                    thumb = ImageOps.contain(background.convert("RGB"), (246, 158))
                    sheet.paste(thumb, (x + (250 - thumb.width) // 2, y))
                target = args.output / f"reference-{candidate['index']:02d}{Path(urlsplit(candidate['imageUrl']).path).suffix}"
                target.write_bytes(content)
                candidate.update(localFile=str(target.resolve()), sha256=hashlib.sha256(content).hexdigest())
                draw.text((x + 6, y + 160), f"#{candidate['index']:02d} {candidate['width']}x{candidate['height']}", fill="black")
            except Exception as error:
                candidate["downloadError"] = str(error)
                draw.text((x + 6, y + 160), f"#{candidate['index']:02d} download failed", fill="red")
            print(f"Reference {offset + 1}/{len(candidates)}", flush=True)
        sheet.save(args.output / "contact-sheet.jpg")
    (args.output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": catalog["model"], "candidateCount": len(catalog["candidates"]),
                      "downloaded": sum("localFile" in item for item in catalog["candidates"])}))


if __name__ == "__main__":
    main()
