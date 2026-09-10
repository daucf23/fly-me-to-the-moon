"""Derive the test vehicle from a stock KSP craft by removing named part types.

Default: stock "Kerbal 1" minus its four R8 winglets, saved as "Fly By Wire". Without
fins the rocket is aerodynamically unstable and only the pod's reaction wheel and the
engine gimbal can hold it, which is the point. Copy the result into
<KSP>/saves/<your save>/Ships/VAB/ and it appears in the VAB and in kRPC's launch_vessel.

    uv run python scripts/make_craft.py
    uv run python scripts/make_craft.py --install "KSP Coding Testing"
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

KSP = Path.home() / "Library/Application Support/Steam/steamapps/common/Kerbal Space Program"
STOCK = KSP / "Ships/VAB/Kerbal 1.craft"
OUT = Path(__file__).resolve().parent.parent / "craft" / "Fly By Wire.craft"
REMOVE = ("R8winglet",)
NAME = "Fly By Wire"
DESCRIPTION = (
    "Stock Kerbal 1 with the winglets removed. Aerodynamically unstable on purpose: a "
    "fruit-fly connectome holds the yaw axis through kRPC. No living fly is involved."
)


def split_parts(text):
    """Return (header, [part_block, ...]) for a craft file. Blocks are top-level PART {}."""
    parts = []
    header_end = text.index("PART\n{")
    header = text[:header_end]
    pos = header_end
    while True:
        start = text.find("PART\n{", pos)
        if start < 0:
            break
        depth = 0
        i = text.index("{", start)
        while True:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        end = i + 1
        while end < len(text) and text[end] == "\n":
            end += 1
        parts.append(text[start:end])
        pos = end
    return header, parts


def part_name(block):
    return re.search(r"^\tpart = (\S+)", block, re.M).group(1)


def build(source, remove, name, description):
    text = source.read_text()
    header, parts = split_parts(text)
    removed = {part_name(b) for b in parts if part_name(b).startswith(remove)}
    kept = [b for b in parts if part_name(b) not in removed]
    cleaned = []
    for block in kept:
        lines = [
            line
            for line in block.split("\n")
            if not any(
                re.fullmatch(rf"\s*(link|sym) = {re.escape(r)}", line) for r in removed
            )
        ]
        for r in removed:
            lines = [re.sub(rf"(attN = \w+), {re.escape(r)}\b", r"\1, Null", ln) for ln in lines]
        cleaned.append("\n".join(lines))
    header = re.sub(r"^ship = .*$", f"ship = {name}", header, flags=re.M)
    header = re.sub(r"^description = .*$", f"description = {description}", header, flags=re.M)
    header = re.sub(r"^vesselType = .*$", "vesselType = Ship", header, flags=re.M)
    out = header + "".join(cleaned)
    for r in removed:
        if r in out:
            raise RuntimeError(f"Dangling reference to removed part {r}")
    return out, removed, len(kept)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, default=STOCK)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--install", metavar="SAVE", help="Also copy into <KSP>/saves/SAVE/Ships/VAB/")
    a = p.parse_args()
    if not a.source.exists():
        sys.exit(f"Stock craft not found: {a.source}")
    text, removed, kept = build(a.source, REMOVE, NAME, DESCRIPTION)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text)
    print(f"wrote {a.out}: kept {kept} parts, removed {sorted(removed)}")
    if a.install:
        target = KSP / "saves" / a.install / "Ships/VAB" / a.out.name
        if not target.parent.parent.exists():
            sys.exit(f"Save not found: {target.parent.parent}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.out, target)
        print(f"installed to {target}")


if __name__ == "__main__":
    main()
