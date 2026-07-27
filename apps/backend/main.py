"""Compatibility entry point for existing ``uvicorn main:app`` commands."""

from app.main import app

__all__ = ["app"]
