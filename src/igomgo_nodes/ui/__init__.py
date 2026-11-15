"""Optional Streamlit graph editor; core never imports this package."""

from .adapter import EditorAdapter
from .editor import render_editor

__all__ = ["EditorAdapter", "render_editor"]
