"""Freeze the tested installed dependency closure, including platform variants.

Run from the project virtualenv after resolving pyproject.toml dependencies.
Requires packaging (installed with the development tools).
"""

import tomllib
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]


def closure(roots):
    pending = [Requirement(item) for item in roots]
    visited = set()
    versions = {}
    while pending:
        request = pending.pop()
        name = canonicalize_name(request.name)
        key = (name, tuple(sorted(request.extras)))
        if key in visited:
            continue
        visited.add(key)
        installed = distribution(name)
        versions[name] = installed.version
        for item in installed.requires or []:
            child = Requirement(item)
            # Include either supported deployment platform in the lock.
            if child.marker is None or any(
                child.marker.evaluate(
                    {
                        "extra": extra,
                        "sys_platform": platform,
                        "platform_system": system,
                    }
                )
                for extra in ["", *request.extras]
                for platform, system in [("win32", "Windows"), ("linux", "Linux")]
            ):
                pending.append(child)
    return (
        "# Resolved and tested dependencies; regenerate with scripts/lock_dependencies.py\n"
        + "".join(f"{name}=={version}\n" for name, version in sorted(versions.items()))
    )


(ROOT / "backend/requirements.lock").write_text(closure(project["dependencies"]))
(ROOT / "backend/requirements-dev.lock").write_text(
    closure(project["dependencies"] + project["optional-dependencies"]["dev"])
)
