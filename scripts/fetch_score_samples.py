"""Download the pinned CC0 recordings for the v6 score; verify every SHA-256."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "scripts/media/v6-samples.json").read_text())
    destination = ROOT / "video/edit-work/v6/samples"
    destination.mkdir(parents=True, exist_ok=True)
    for entry in manifest["samples"]:
        path = destination / entry["file"]
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        with urlopen(entry["url"], timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Sample checksum mismatch: {entry['source_path']}")
        path.write_bytes(data)
        print(f"Verified {entry['file']}")
    print(f"All {len(manifest['samples'])} sample/license files verified.")


if __name__ == "__main__":
    main()
