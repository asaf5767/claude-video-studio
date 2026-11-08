"""Task 12: the effects board catalogs.

Two static, committed JSON lists the studio UI shows as live demo cards:
  - effects/effects.json   After-Effects-style motion graphics (the "אפקטים" tab)
  - looks/presenter.json   presenter looks, "איך אתם נראים" (a separate tab); each one
                           also says whether it needs the presenter cut out of the
                           background first (requires_matte -> scripts/matte.py)

Every entry is {"id", "name_key", "desc_key", "category", "demo", "instructions"}: the
name/description/category labels are i18n keys (dist/i18n/<lang>.json, category key
"fx.cat.<category>"), "demo" names a live demo registered in dist/fx-demos.js, and
"instructions" is the English recipe Claude follows to build it in HyperFrames/FFmpeg.

A malformed catalog is a bug in shipped content, not user input: list() raises
ValueError and GET /effects answers 503.
"""
import builtins
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EFFECTS_PATH = ROOT / 'effects' / 'effects.json'
LOOKS_PATH = ROOT / 'looks' / 'presenter.json'
REQUIRED = ('id', 'name_key', 'desc_key', 'category', 'demo', 'instructions')
ID_TOKEN = re.compile(r'[a-z][a-z0-9-]{0,39}')


def _read(path, is_look):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, builtins.list):
        raise ValueError(f'{path.name} must be a JSON list')
    items = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f'{path.name}: every entry must be an object')
        for key in REQUIRED:
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f'{path.name}: {entry.get("id")!r} is missing {key}')
        if not ID_TOKEN.fullmatch(entry['id']) or not ID_TOKEN.fullmatch(entry['demo']):
            raise ValueError(f'{path.name}: bad id {entry["id"]!r}')
        if is_look and not isinstance(entry.get('requires_matte'), bool):
            raise ValueError(f'{path.name}: {entry["id"]!r} must say requires_matte true/false')
        items.append(dict(entry))
    return items


def list():
    """effects.list() -> {"effects": [...], "looks": [...]}, both catalogs validated,
    ids unique across the two."""
    result = {'effects': _read(EFFECTS_PATH, False), 'looks': _read(LOOKS_PATH, True)}
    ids = [item['id'] for item in result['effects'] + result['looks']]
    if len(ids) != len(set(ids)):
        raise ValueError('effect and look ids must be unique across both catalogs')
    return result


def effect_ids():
    return [item['id'] for item in list()['effects']]


def look_ids():
    return [item['id'] for item in list()['looks']]


def get(item_id):
    """The catalog entry for an effect or presenter-look id, or None."""
    data = list()
    return next((item for item in data['effects'] + data['looks'] if item['id'] == item_id), None)
