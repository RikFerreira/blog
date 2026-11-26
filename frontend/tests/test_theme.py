"""The theme: interface strings, icons, and the chrome every page inherits."""

import re

import pytest

from build import ContentError, flatten_keys, load_site, load_theme

THEME_NAME = "blog-plain"

# t('a.b'), ui("a.b"), action('a.b') as the templates spell them.
I18N_CALL = re.compile(r"\b(?:t|ui|action)\(\s*'([a-z_]+(?:\.[a-z_]+)+)'")


@pytest.fixture
def theme(fixture_content, theme_dir):
    return load_theme(theme_dir, load_site(fixture_content).settings)


# --------------------------------------------------------------------------
# interface strings
# --------------------------------------------------------------------------

def test_both_language_files_declare_exactly_the_same_keys(theme):
    english = flatten_keys(theme.translations["en"])
    portuguese = flatten_keys(theme.translations["pt"])
    assert english == portuguese


def test_every_key_a_template_asks_for_exists(theme, theme_dir):
    known = flatten_keys(theme.translations["en"])
    for template in sorted((theme_dir / "templates").rglob("*.html")):
        for key in I18N_CALL.findall(template.read_text(encoding="utf-8")):
            assert key in known, f"{template.name} asks for a missing string: {key}"


def test_an_unknown_key_is_an_error_rather_than_an_empty_string(theme):
    with pytest.raises(ContentError, match="nav.nope"):
        theme.t("nav.nope")


def test_t_returns_the_default_language(theme):
    assert theme.t("nav.posts") == "Posts"
    assert theme.t("nav.home") == "Home"


# --------------------------------------------------------------------------
# bilingual markup
# --------------------------------------------------------------------------

def test_ui_emits_one_data_attribute_per_language(theme):
    assert theme.ui("nav.home") == 'data-en="Home" data-pt="Início"'


def test_ui_escapes_quotes(theme):
    theme.translations["en"]["nav"]["home"] = 'He said "hi"'
    assert "&#34;hi&#34;" in theme.ui("nav.home")


def test_action_emits_a_tooltip_and_its_translations(theme):
    markup = theme.action("action.read_post")
    assert 'title="Read post"' in markup
    assert 'aria-label="Read post"' in markup
    assert 'data-en-title="Read post"' in markup
    assert 'data-pt-title="Ler o post"' in markup


# --------------------------------------------------------------------------
# icons
# --------------------------------------------------------------------------

def test_icon_renders_an_svg_at_the_requested_size(theme):
    markup = theme.icon("menu", 16)
    assert markup.startswith("<svg")
    assert 'width="16" height="16"' in markup
    assert 'stroke-width="1.75"' in markup
    assert 'viewBox="0 0 24 24"' in markup
    assert 'aria-hidden="true"' in markup


def test_icons_that_the_handoff_draws_square_keep_their_linecap(theme):
    assert 'stroke-linecap="square"' in theme.icon("arrow_right")
    assert "stroke-linecap" not in theme.icon("github")


def test_an_unknown_icon_is_an_error(theme):
    with pytest.raises(ContentError, match="sparkle"):
        theme.icon("sparkle")


# --------------------------------------------------------------------------
# urls
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("base", "path", "expected"),
    [
        ("/", "css/styles.css", "/css/styles.css"),
        ("/", "/posts/", "/posts/"),
        ("https://rikalves.com/", "css/styles.css", "https://rikalves.com/css/styles.css"),
        ("https://rikalves.com", "/posts/", "https://rikalves.com/posts/"),
    ],
)
def test_url_joins_the_base_url(theme, base, path, expected):
    theme.settings.data.setdefault("site", {})["base_url"] = base
    assert theme.url(path) == expected


# --------------------------------------------------------------------------
# the chrome
# --------------------------------------------------------------------------

def _chrome(theme, **context):
    template = theme.env.from_string(
        '{% extends "base.html" %}{% block content %}<p>body</p>{% endblock %}'
    )
    return template.render(**theme.context(**context))


def test_the_page_opens_in_the_default_language(theme):
    assert '<html lang="en">' in _chrome(theme)


def test_the_navigation_marks_the_current_section(theme):
    html = _chrome(theme, active_nav="posts")
    assert 'href="/posts/" class="nav-link is-active"' in html
    assert 'href="/publications/" class="nav-link"' in html


def test_the_navigation_is_bilingual(theme):
    html = _chrome(theme)
    assert 'data-en="Publications" data-pt="Publicações">Publications</a>' in html


def test_the_chrome_appears_once_for_the_sidebar_and_once_for_the_drawer(theme):
    html = _chrome(theme)
    assert html.count('class="lang-toggle"') == 2
    assert html.count('class="icon-row"') == 2
    assert html.count('id="mobile-drawer"') == 1


def test_the_language_toggle_offers_every_declared_language(theme):
    html = _chrome(theme)
    assert '<button type="button" class="lang-btn is-active" data-lang="en">EN</button>' in html
    assert '<button type="button" class="lang-btn" data-lang="pt">PT</button>' in html


def test_profile_links_are_rendered_from_the_settings(theme):
    html = _chrome(theme)
    assert 'href="https://github.com/RikFerreira"' in html
    assert 'rel="noopener noreferrer"' in html


def test_the_sidebar_and_drawer_are_kept_out_of_print(theme):
    html = _chrome(theme)
    assert html.count("no-print") == 3
