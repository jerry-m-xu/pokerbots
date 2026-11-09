"""Zip bot/ for upload and run the server's static checks locally.

    python3 tools/pack.py [OUT.zip]

Once the kit is installed, prefer its own `poker-agent pack bot OUT.zip`,
which runs the official checks. This mirrors the published limits: agent.py
at the zip root, no file importing poker_engine/pokerkit, agent.py under
1 MB, under 1,000 entries, 50 MB zipped / 200 MB unpacked.
"""
import ast
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = os.path.join(ROOT, "bot")
FORBIDDEN = {"poker_engine", "pokerkit"}


def files():
    for dirpath, dirnames, filenames in os.walk(BOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
        for f in sorted(filenames):
            if f.startswith(".") or f.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, f)
            if os.path.islink(full):
                sys.exit(f"refusing symlink {full}")
            yield full, os.path.relpath(full, BOT)


def check_imports(path, rel):
    tree = ast.parse(open(path, encoding="utf-8").read(), rel)
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            if n.split(".")[0] in FORBIDDEN:
                sys.exit(f"{rel}:{node.lineno} imports {n}, which the server rejects")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "bot.zip")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    entries = list(files())
    if not any(rel == "agent.py" for _, rel in entries):
        sys.exit("bot/agent.py missing")
    if os.path.getsize(os.path.join(BOT, "agent.py")) > 1_000_000:
        sys.exit("agent.py exceeds 1 MB")
    unpacked = 0
    for full, rel in entries:
        if rel.endswith(".py"):
            check_imports(full, rel)
        unpacked += os.path.getsize(full)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in entries:
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as f:
                z.writestr(info, f.read())
    n_dirs = len({os.path.dirname(rel) for _, rel in entries} - {""})
    if len(entries) + n_dirs >= 1000:
        sys.exit("too many archive entries")
    size = os.path.getsize(out)
    if size > 50_000_000 or unpacked > 200_000_000:
        sys.exit("package too large")
    print(f"wrote {out}: {len(entries)} files, {size / 1024:.0f} KB zipped, {unpacked / 1024:.0f} KB unpacked")


if __name__ == "__main__":
    main()
