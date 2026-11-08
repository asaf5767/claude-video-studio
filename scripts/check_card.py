"""Check a learned style card before finishing the learn-style skill.

    python scripts/check_card.py references/<id>

Reads references/<id>/style-card.md (the looks/<id>/card.md format: front matter with every
looks.REQUIRED_KEYS key on one non-empty line, then free notes) and, when present, the
creator's style-card.json ({"pinned": {key: value}}, or an older {"pinned": [keys]}). Every
pinned row must still read exactly the creator's value. Prints {"ok", "missing",
"changed_pins"} and exits 1 when not ok. Never writes anything.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'style-library'))
import looks  # noqa: E402  (REQUIRED_KEYS and the card parser shared with built-in looks)


def check(folder):
    folder = Path(folder)
    try:
        fields, _body = looks._front_matter((folder / 'style-card.md').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        fields = {}
    missing = [key for key in looks.REQUIRED_KEYS if not fields.get(key, '').strip()]
    try:
        pinned = json.loads((folder / 'style-card.json').read_text(encoding='utf-8')).get('pinned') or {}
    except (OSError, ValueError, AttributeError):
        pinned = {}
    if isinstance(pinned, list):
        changed = [key for key in pinned if isinstance(key, str) and not fields.get(key, '').strip()]
    else:
        changed = [key for key, value in pinned.items() if fields.get(key, '').strip() != str(value).strip()]
    return {'ok': not missing and not changed, 'missing': missing, 'changed_pins': changed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args(argv)
    result = check(args.folder)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
