"""Registry versioning helpers.

The registry as a whole carries a semantic version (`data/registry/*.seed.yaml` ->
`registry_version` on every record). Bump rules, enforced by convention and checked in
`registry/validator.py`:

- PATCH: metadata fixes (typos, TODO -> verified quote) that do not change any
  mechanism's epistemic_status or default_activation_policy.
- MINOR: new mechanism or evidence record added; no existing mechanism's
  epistemic_status is loosened.
- MAJOR: an existing mechanism's epistemic_status changes (in either direction), or a
  mechanism is retired/merged.
"""

from __future__ import annotations

import re

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

CURRENT_REGISTRY_VERSION = "0.1.0"


def is_valid_registry_version(value: str) -> bool:
    return bool(_SEMVER_RE.match(value))


def parse_registry_version(value: str) -> tuple[int, int, int]:
    if not is_valid_registry_version(value):
        raise ValueError(f"Not a valid semver registry_version: {value!r}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)
