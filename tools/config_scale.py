#!/usr/bin/env python3
"""Scale thread/physics configs by core count and host role.

Client role  = singleplayer / LAN host on a laptop: leave cores for the render thread.
Server role  = dedicated server: no render thread, so workers and physics can scale up.

Only fixed-value configs are rewritten here. C2ME is handled natively at runtime by
its parallelism expression (which reads `is_client`, `cores`, `cpus`, `mem_gb`).

Usage:
  python3 tools/config_scale.py --role client
  python3 tools/config_scale.py --role server --cores 8
  python3 tools/config_scale.py --role client --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

PACK = Path(os.environ.get("PACK_DIR", Path(__file__).resolve().parents[1]))

C2ME_EXPRESSION = (
    "max(1, min(if(is_smt_probably_enabled, cores, cpus) - if(is_client, 4, 1), "
    "(mem_gb - if(is_client, 2.0, 0.5)) * 2.0))"
)

CLIENT_RANGES = {
    "raider": 96, "water": 64, "villager": 64, "zombie": 64,
    "monster-below": 64, "flying-monster": 96, "monster": 96,
    "animal": 64, "creature": 64,
}
DEFAULT_RANGES = {
    "raider": 48, "water": 16, "villager": 16, "zombie": 16,
    "monster-below": 32, "flying-monster": 48, "monster": 32,
    "animal": 16, "creature": 24,
}


def physical_cores() -> int:
    try:
        ids = set()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("core id"):
                ids.add(line.split(":", 1)[1].strip())
        return len(ids) or os.cpu_count() or 4
    except OSError:
        return os.cpu_count() or 4


def sub(path: Path, pattern: str, replacement: str, expected: int = 1) -> str:
    text = path.read_text()
    new, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} match(es) for {pattern!r}, got {count}")
    path.write_text(new)
    return text


def toml_int(path: Path, key: str, value: int) -> None:
    sub(path, rf"^(\s*){re.escape(key)}\s*=\s*[^\n#]+", rf"\g<1>{key} = {value}")


def toml_str(path: Path, key: str, value: str) -> None:
    sub(path, rf"^(\s*){re.escape(key)}\s*=\s*[^\n#]+", rf'\g<1>{key} = "{value}"')


def json_int(path: Path, key: str, value: int) -> None:
    sub(path, rf'("{re.escape(key)}"\s*:\s*)[0-9]+', rf"\g<1>{value}")


def yaml_number(path: Path, key: str, value: float) -> None:
    sub(path, rf"^(\s*){re.escape(key)}:\s*[0-9.]+", rf"\g<1>{key}: {value}")


def yaml_section_toggle(path: Path, section: str, key: str, value: str) -> None:
    text = path.read_text()
    start = text.index(section + ":")
    end = text.find("\n", start)
    # section ends at the next top-level (unindented) key
    for line in text[end + 1:].splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            break
        end += len(line) + 1
    block = text[start:end]
    new_block, count = re.subn(
        rf"^(\s*){re.escape(key)}:\s*\w+", rf"\g<1>{key}: {value}", block, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise SystemExit(f"{path}: could not toggle {section}.{key}")
    path.write_text(text[:start] + new_block + text[end:])


def yaml_ranges(path: Path, ranges: dict) -> None:
    text = path.read_text()
    for name, value in ranges.items():
        pattern = rf"(- name: '{re.escape(name)}'\n\s+activation-range:\s*)[0-9]+"
        text, count = re.subn(pattern, rf"\g<1>{value}", text)
        if count != 1:
            raise SystemExit(f"{path}: activation range entry {name!r} matched {count} times")
    path.write_text(text)


def apply(role: str, cores: int, dry_run: bool) -> None:
    if role == "client":
        dh_threads = max(1, min(3, cores // 3))
        dh_ratio = "0.6"
        dh_priority = 3
        # Chunk meshing is the dominant chunk-crossing stall (ChunkBuilderMeshingTask).
        sodium_threads = max(2, min(4, cores - 2))
        preview_threads = max(1, cores // 3)
        sable_substeps = 1
        target_mspt = 17
        activation = "true"
        ranges = CLIENT_RANGES
    else:
        dh_threads = max(2, min(8, cores - 1))
        dh_ratio = "1.0"
        dh_priority = 5
        sodium_threads = 0  # Sodium is client-only; auto is irrelevant on a dedicated server
        preview_threads = max(2, min(8, cores - 2))
        sable_substeps = 2
        target_mspt = 50
        activation = "false"
        ranges = DEFAULT_RANGES

    print(f"role={role} cores={cores}")
    print(
        f"  DH={dh_threads}@{dh_ratio} prio={dh_priority}, C2ME=expression, "
        f"Sodium={sodium_threads}, WorldPreview={preview_threads}, "
        f"Sable substeps={sable_substeps}, ServerCore target_mspt={target_mspt}, "
        f"activation-range={activation}"
    )
    if dry_run:
        return

    # C2ME: native runtime scaling by core count and client/server role
    toml_str(PACK / "config/c2me.toml", "defaultGlobalExecutorParallelismExpression", C2ME_EXPRESSION)
    toml_str(PACK / "config/c2me.toml", "globalExecutorParallelism", "default")

    # Distant Horizons / Sodium / World Preview: fixed caps, scaled here
    toml_int(PACK / "config/DistantHorizons.toml", "numberOfThreads", dh_threads)
    toml_str(PACK / "config/DistantHorizons.toml", "threadRunTimeRatio", dh_ratio)
    toml_int(PACK / "config/DistantHorizons.toml", "threadPriority", dh_priority)
    json_int(PACK / "config/sodium-options.json", "chunk_builder_threads", sodium_threads)
    json_int(PACK / "config/world_preview/config.json", "numThreads", preview_threads)

    # Physics: full accuracy on a dedicated server, cheaper on the client host
    toml_int(PACK / "config/sable-server.toml", "sub_level_substeps_per_tick", sable_substeps)

    # ServerCore: load-based entity tuning at the relevant tick budget
    yaml_number(PACK / "config/servercore/config.yml", "target-mspt", target_mspt)
    yaml_section_toggle(PACK / "config/servercore/config.yml", "activation-range", "enabled", activation)
    yaml_ranges(PACK / "config/servercore/config.yml", ranges)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("client", "server"), required=True)
    parser.add_argument("--cores", type=int, default=None, help="physical cores (auto-detected by default)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    apply(args.role, args.cores or physical_cores(), args.dry_run)


if __name__ == "__main__":
    main()
