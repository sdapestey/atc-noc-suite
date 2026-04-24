from pathlib import Path


def test_noc_head_includes_theme_bootstrap_and_script():
    tpl = Path("templates/partials/noc_head.html").read_text(encoding="utf-8")
    assert 'localStorage.getItem("theme")' in tpl
    assert "prefers-color-scheme: dark" in tpl
    assert "data-theme" in tpl
    assert "js/theme-toggle.js" in tpl


def test_noc_topbar_renders_theme_toggle_button():
    tpl = Path("templates/partials/noc_topbar.html").read_text(encoding="utf-8")
    assert "data-theme-toggle" in tpl
    assert "Modo: Dark" in tpl
