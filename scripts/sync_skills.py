"""Mirror canonical skills into project-local Codex and Claude Code discovery paths."""

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail instead of writing stale copies")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stale = []
    for source in sorted((root / "skills").glob("*/SKILL.md")):
        for agent in (".agents", ".claude"):
            target = root / agent / "skills" / source.parent.name / "SKILL.md"
            expected = source.read_bytes()
            if not target.exists() or target.read_bytes() != expected:
                if args.check:
                    stale.append(str(target.relative_to(root)))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(expected)
    if stale:
        parser.exit(1, "Stale skill copies: " + ", ".join(stale) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
