"""Serve the optional production build after the API routes."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, directory: Path) -> bool:
    """Mount a production build at / if it exists; report whether it was mounted."""
    if (directory / 'index.html').is_file():
        app.mount('/', StaticFiles(directory=directory, html=True), name='frontend')
        return True
    return False


def mount_first_build(app: FastAPI, directories: list[Path]) -> Path | None:
    """Mount the first existing build, in order of preference, and return it."""
    for directory in directories:
        if mount_frontend(app, directory):
            return directory
    return None
