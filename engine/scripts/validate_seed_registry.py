#!/usr/bin/env python
"""Validate the bootstrap seed registry. Exits non-zero on any integrity problem.

Usage: uv run python scripts/validate_seed_registry.py [seed_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

from wittgenstein.registry.loader import RegistryLoadError, load_registry
from wittgenstein.registry.validator import RegistrySeedIntegrityError
from wittgenstein.services.registry_service import default_seed_dir


def main(seed_dir: Path | None = None) -> int:
    seed_dir = seed_dir or default_seed_dir()
    try:
        registry = load_registry(seed_dir)
    except (RegistryLoadError, RegistrySeedIntegrityError) as exc:
        print(f"REGISTRY VALIDATION FAILED\n{exc}", file=sys.stderr)
        return 1
    print(
        f"OK: {len(registry.mechanisms)} mechanisms, {len(registry.evidence)} evidence records, "
        f"{len(registry.gates)} manifest gates, {len(registry.triggers)} trace triggers, "
        f"{len(registry.review_actions)} review actions."
    )
    return 0


if __name__ == "__main__":
    seed = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(seed))
