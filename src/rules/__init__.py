"""Decentraland wearable and emote limits, vendored from @dcl-regenesislabs/wearable-validator (see manifest.lock)."""

import json
import os

RULES_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(RULES_DIR, "manifest.json")
LOCK_PATH = os.path.join(RULES_DIR, "manifest.lock")

_manifest = None


def manifest():
    global _manifest
    if _manifest is None:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            _manifest = json.load(f)
    return _manifest


def rules_version():
    return manifest()["version"]


def triangle_limit(category, hides=()):
    """Mirror of the rule book's effectiveTriangleLimit: hidden slots add their budget, head hiders cap at the helmet limit."""
    tris = manifest()["triangles"]
    hides_head = "head" in hides
    hidden = set(hides) | (set(tris["headSlots"]) if hides_head else set())
    hidden.discard(category)
    limit = tris["perCategory"].get(category, tris["default"])
    for slot in hidden:
        limit += tris["hiddenHandsBudget"] if slot == "hands" else tris["perCategory"].get(slot, 0)
    if category == "helmet" or hides_head:
        return min(limit, tris["hiddenHeadLimit"])
    return limit
