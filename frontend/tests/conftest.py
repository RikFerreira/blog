import sys
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FRONTEND))

FIXTURE_CONTENT = Path(__file__).resolve().parent / "fixtures" / "content"

MINIMAL_INDEX = """
[site]
title            = "test"
base_url         = "/"
theme            = "blog-plain"
default_language = "en"
languages        = ["en", "pt"]
"""

MINIMAL_SECTION = """
[section]
kind = "post"
"""


@pytest.fixture
def fixture_content():
    return FIXTURE_CONTENT


@pytest.fixture
def theme_dir():
    return FRONTEND / "themes" / "blog-plain"


@pytest.fixture
def make_content(tmp_path):
    """Write a content tree from a {relative path: text} mapping.

    `index.toml` and `posts/posts.toml` are supplied unless overridden, so a
    test only spells out the file it is actually about.
    """

    def _make(files, *, with_defaults=True):
        root = tmp_path / "content"
        tree = {}
        if with_defaults:
            tree["index.toml"] = MINIMAL_INDEX
            tree["posts/posts.toml"] = MINIMAL_SECTION
        tree.update(files)
        for relative, text in tree.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    return _make
