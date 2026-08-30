#!/usr/bin/env python3
"""Maintain and resolve the deterministic Hermes profile-to-X-display map."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


DISPLAY_POOL = tuple(f":{number}" for number in range(100, 110))
DEFAULT_PROFILE = "default"
DEFAULT_DISPLAY = DISPLAY_POOL[0]


class DisplayMapError(RuntimeError):
    pass


def _map_path(data_dir: Path) -> Path:
    return data_dir / ".displays.json"


def _load_mapping(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DisplayMapError(f"invalid display map: {path}") from exc
    if not isinstance(payload, dict) or not all(
        isinstance(profile, str) and profile and isinstance(display, str)
        for profile, display in payload.items()
    ):
        raise DisplayMapError("display map must be a profile-to-display object")
    if any(display not in DISPLAY_POOL for display in payload.values()):
        raise DisplayMapError("display map contains a display outside :100..:109")
    if len(set(payload.values())) != len(payload):
        raise DisplayMapError("display map contains duplicate display assignments")
    if payload.get(DEFAULT_PROFILE, DEFAULT_DISPLAY) != DEFAULT_DISPLAY:
        raise DisplayMapError("default profile must use display :100")
    return payload


def _profile_names(data_dir: Path) -> list[str]:
    profiles_dir = data_dir / "profiles"
    if not profiles_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in profiles_dir.iterdir()
        if entry.is_dir() and not entry.is_symlink()
    )


def _plan_mapping(
    current: dict[str, str], profile_names: list[str]
) -> dict[str, str]:
    desired_names = [DEFAULT_PROFILE, *profile_names]
    planned = {
        profile: display
        for profile, display in current.items()
        if profile in desired_names
    }
    planned[DEFAULT_PROFILE] = DEFAULT_DISPLAY
    used = set(planned.values())
    for profile in desired_names:
        if profile in planned:
            continue
        display = next((item for item in DISPLAY_POOL if item not in used), None)
        if display is None:
            raise DisplayMapError("display pool exhausted (:100..:109)")
        planned[profile] = display
        used.add(display)
    return dict(sorted(planned.items()))


def _write_mapping(path: Path, mapping: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent), text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def ensure(data_dir: Path, *, publish: bool = True) -> dict[str, str]:
    path = _map_path(data_dir)
    mapping = _plan_mapping(_load_mapping(path), _profile_names(data_dir))
    if publish:
        _write_mapping(path, mapping)
    return mapping


def check_capacity(data_dir: Path, profile: str) -> None:
    names = _profile_names(data_dir)
    if profile not in names:
        names.append(profile)
        names.sort()
    _plan_mapping(_load_mapping(_map_path(data_dir)), names)


def release(data_dir: Path, profile: str) -> dict[str, str]:
    if profile == DEFAULT_PROFILE:
        raise DisplayMapError("the default display assignment cannot be released")
    path = _map_path(data_dir)
    mapping = _load_mapping(path)
    mapping.pop(profile, None)
    mapping = _plan_mapping(mapping, _profile_names(data_dir))
    _write_mapping(path, mapping)
    return mapping


def _home_profile(home: str) -> str:
    if not home:
        return ""
    path = Path(home.rstrip("/"))
    return path.name if path.parent.name == "profiles" else ""


def current_display(path: Path) -> str:
    mapping = _load_mapping(path)
    session_profile = os.environ.get("HERMES_SESSION_PROFILE", "").strip()
    home_profile = _home_profile(os.environ.get("HERMES_HOME", "").strip())
    if session_profile and home_profile and session_profile != home_profile:
        raise DisplayMapError(
            "profile context mismatch between HERMES_SESSION_PROFILE and HERMES_HOME"
        )
    profile = session_profile or home_profile or DEFAULT_PROFILE
    display = mapping.get(profile)
    if display is None:
        raise DisplayMapError(f"no display assigned to profile {profile!r}")
    return display


def _print_mapping(mapping: dict[str, str]) -> None:
    print(f"{'PROFILE':28} DISPLAY")
    for profile, display in sorted(mapping.items(), key=lambda item: int(item[1][1:])):
        print(f"{profile:28} {display}")


def main(argv: list[str]) -> int:
    try:
        command = argv[1]
        target = Path(argv[2])
    except IndexError:
        print(
            "usage: profile-displays.py ensure|check|release|list|current <data-or-map> [profile]",
            file=sys.stderr,
        )
        return 2
    try:
        if command == "ensure":
            ensure(target)
        elif command == "check":
            check_capacity(target, argv[3])
        elif command == "release":
            release(target, argv[3])
        elif command == "list":
            _print_mapping(ensure(target))
        elif command == "current":
            print(current_display(target))
        else:
            raise DisplayMapError(f"unknown command: {command}")
    except (DisplayMapError, IndexError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
