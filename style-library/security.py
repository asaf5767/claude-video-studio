"""Confinement for explicitly registered personal media and notes."""
from pathlib import Path
import re

TOKEN = re.compile(r'^[a-z0-9][a-z0-9-]*$')
# Windows device names no file or folder may take (compare upper-cased; final review M13c).
RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{d}' for d in '123456789'} | {f'LPT{d}' for d in '123456789'}
MEDIA = {'.mp4', '.mov', '.webm', '.m4v', '.png', '.jpg', '.jpeg', '.webp', '.gif'}
AUDIO = {'.mp3', '.wav', '.m4a', '.aac'}
NOTES = {'.md', '.txt', '.json', '.csv', '.srt', '.vtt'}

def registered_file(studio, relative, extensions):
    if not isinstance(relative, str):
        raise ValueError('A registered path must be relative text')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or len(path.parts) < 3:
        raise ValueError('Use a project or reference relative path')
    collection, slug = path.parts[:2]
    if collection not in {'projects', 'references'} or not TOKEN.fullmatch(slug):
        raise ValueError('Media belongs in projects/<slug> or references/<slug>')
    studio = studio.resolve()
    parent = (studio / collection).resolve()
    root = (parent / slug).resolve()
    if parent.parent != studio or root.parent != parent:
        raise ValueError('Collection or project root escapes the studio')
    target = (studio / path).resolve()
    if (not target.is_relative_to(root) or target.suffix.lower() not in extensions or
            any(p.startswith('.') for p in path.parts) or not target.is_file()):
        raise ValueError('Missing or unsupported registered file')
    return target
