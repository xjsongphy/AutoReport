"""Canonical AutoReport project directory layout and migration helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from loguru import logger


PROJECT_DIRECTORIES = (
    "Data",
    "Data/Processed",
    "References",
    "Theory",
    "Theory/Derivations",
    "Plots",
    "Plots/Fig",
    "Plots/Scripts",
    "Outline",
    "Tex",
)

TOP_LEVEL_PROJECT_DIRECTORIES = ("Data", "References", "Theory", "Plots", "Outline", "Tex")

_LEGACY_PROJECT_MARKERS = ("data", "references", "theory", "plots", "tex")


def is_project_workspace(path: Path) -> bool:
    """Return True when path contains canonical or legacy AutoReport markers."""
    workspace = Path(path)
    markers = (*TOP_LEVEL_PROJECT_DIRECTORIES, *_LEGACY_PROJECT_MARKERS)
    return any(_find_exact_child(workspace, marker) is not None for marker in markers)


def ensure_project_structure(workspace: Path) -> None:
    """Create the canonical project layout and migrate old directory casing."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    data_dir = _ensure_child_case(workspace, "Data")
    _ensure_child_case(data_dir, "Processed")

    _ensure_child_case(workspace, "References")
    theory_dir = _ensure_child_case(workspace, "Theory")
    _ensure_child_case(theory_dir, "Derivations")
    plots_dir = _ensure_child_case(workspace, "Plots")
    _ensure_child_case(plots_dir, "Fig")
    _ensure_child_case(plots_dir, "Scripts")
    _ensure_child_case(workspace, "Outline")
    _ensure_child_case(workspace, "Tex")


def _ensure_child_case(parent: Path, canonical_name: str) -> Path:
    """Ensure one child directory exists using exactly ``canonical_name``."""
    parent.mkdir(parents=True, exist_ok=True)

    exact = _find_exact_child(parent, canonical_name)
    variants = [
        child
        for child in _iter_children(parent)
        if child.name.lower() == canonical_name.lower() and child.name != canonical_name
    ]

    if exact is None and variants:
        source = variants.pop(0)
        exact = _rename_directory_case(source, parent / canonical_name)

    if exact is None:
        exact = parent / canonical_name
        exact.mkdir(parents=True, exist_ok=True)

    for variant in variants:
        _merge_directory(variant, exact)

    return exact


def _find_exact_child(parent: Path, name: str) -> Path | None:
    for child in _iter_children(parent):
        if child.name == name:
            return child
    return None


def _iter_children(parent: Path) -> list[Path]:
    try:
        return list(parent.iterdir())
    except FileNotFoundError:
        return []


def _rename_directory_case(source: Path, target: Path) -> Path:
    if source == target:
        return target

    if target.exists() and not _is_same_file(source, target):
        _merge_directory(source, target)
        return target

    tmp = source.parent / f".autoreport-case-{os.getpid()}-{target.name}"
    while tmp.exists():
        tmp = tmp.with_name(f"{tmp.name}-x")

    try:
        source.rename(tmp)
        tmp.rename(target)
        logger.info("Normalized project directory case: {} -> {}", source, target)
    except OSError:
        if tmp.exists() and not target.exists():
            tmp.rename(source)
        raise
    return target


def _merge_directory(source: Path, target: Path) -> None:
    if not source.exists() or _is_same_file(source, target):
        return
    if not source.is_dir() or not target.is_dir():
        logger.warning("Skipping conflicting project path during case normalization: {}", source)
        return

    target.mkdir(parents=True, exist_ok=True)
    for child in list(source.iterdir()):
        destination = target / child.name
        if destination.exists():
            if child.is_dir() and destination.is_dir():
                _merge_directory(child, destination)
            else:
                logger.warning(
                    "Leaving conflicting project file in legacy directory: {}",
                    child,
                )
        else:
            shutil.move(str(child), str(destination))

    try:
        source.rmdir()
        logger.info("Merged legacy project directory into canonical path: {} -> {}", source, target)
    except OSError:
        logger.warning("Legacy project directory not empty after merge: {}", source)


def _is_same_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False
