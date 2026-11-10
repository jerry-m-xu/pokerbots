"""Build and validate a reproducible submission with the official SDK packer."""
import json
from pathlib import Path
import sys
import tempfile

from poker_agent_sdk.bundle import pack

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'dist' / 'bot.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        archive = Path(temporary) / 'bot.zip'
        report = pack(ROOT / 'bot', archive)
        archive.replace(destination)
    print(json.dumps(dict(path=str(destination), sha256=report.sha256, bytes=report.size_bytes, files=report.files), indent=2))


if __name__ == '__main__':
    main()
