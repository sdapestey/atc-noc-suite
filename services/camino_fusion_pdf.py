"""Generación PDF reporte fusión (Playwright o Chrome headless — fiel al modelo Bentley)."""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_WATERMARK_SVG = os.path.join(_ROOT, "static", "img", "american-tower-logo.svg")
_WATERMARK_PNG = os.path.join(_ROOT, "static", "img", "american-tower-watermark.png")
_WATERMARK_PLACEHOLDER = "__BENTLEY_WATERMARK__"
_HEADER_LOGO_PLACEHOLDER = "__BENTLEY_HEADER_LOGO__"
# Incrementar al cambiar rasterizado (fuerza regenerar PNG en caché).
_WATERMARK_GEN = 2
_WATERMARK_BAKED_OPACITY = 0.18


def fusion_html_to_pdf(html: str, *, base_url: str = "http://127.0.0.1:9000/") -> bytes:
    """Renderiza HTML a PDF 1368×943 pt como Modelo SF01-R1301-010."""
    if not base_url.endswith("/"):
        base_url = base_url + "/"

    html = _embed_fusion_assets(html)

    try:
        return _pdf_playwright(html, base_url)
    except Exception:
        return _pdf_chrome(html, base_url)


def _watermark_cache_stale() -> bool:
    if not os.path.isfile(_WATERMARK_PNG):
        return True
    stamp_path = _WATERMARK_PNG + ".gen"
    try:
        with open(stamp_path, encoding="ascii") as fh:
            if int(fh.read().strip()) == _WATERMARK_GEN:
                mtime_svg = os.path.getmtime(_WATERMARK_SVG) if os.path.isfile(_WATERMARK_SVG) else 0
                return os.path.getmtime(_WATERMARK_PNG) < mtime_svg
    except (OSError, ValueError):
        pass
    return True


def _ensure_watermark_png() -> str:
    """Rasteriza el SVG a PNG con transparencia y opacidad horneada (Chromium no imprime SVG en PDF)."""
    if not _watermark_cache_stale():
        return _WATERMARK_PNG

    if not os.path.isfile(_WATERMARK_SVG):
        return _WATERMARK_PNG if os.path.isfile(_WATERMARK_PNG) else ""

    from playwright.sync_api import sync_playwright

    with open(_WATERMARK_SVG, "rb") as fh:
        svg = re.sub(rb"\s+", b" ", fh.read()).strip()
    svg_uri = "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
    op = _WATERMARK_BAKED_OPACITY
    html = (
        "<!DOCTYPE html><html><body style='margin:0;background:transparent'>"
        f'<img id="wm" src="{svg_uri}" style="width:2500px;height:auto;opacity:{op};display:block">'
        "</body></html>"
    )
    launch_opts: dict = {"headless": True}
    if shutil.which("google-chrome") or shutil.which("chromium"):
        launch_opts["channel"] = "chrome"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_opts)
        page = browser.new_page(viewport={"width": 2500, "height": 1200})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(200)
        png_bytes = page.locator("#wm").screenshot(type="png", omit_background=True)
        browser.close()
    with open(_WATERMARK_PNG, "wb") as fh:
        fh.write(png_bytes)
    with open(_WATERMARK_PNG + ".gen", "w", encoding="ascii") as fh:
        fh.write(str(_WATERMARK_GEN))
    return _WATERMARK_PNG


def prepare_watermark_asset() -> str:
    """Asegura que exista el PNG de marca de agua (preview HTML y PDF)."""
    return _ensure_watermark_png()


def watermark_placeholder() -> str:
    return _WATERMARK_PLACEHOLDER


def header_logo_data_uri() -> str:
    if not os.path.isfile(_WATERMARK_SVG):
        return ""
    with open(_WATERMARK_SVG, "rb") as fh:
        svg = re.sub(rb"\s+", b" ", fh.read()).strip()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


def header_logo_placeholder() -> str:
    return _HEADER_LOGO_PLACEHOLDER


def watermark_data_uri() -> str:
    png_path = _ensure_watermark_png()
    if not png_path:
        return ""
    with open(png_path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def _embed_fusion_assets(html: str) -> str:
    """Inline CSS y marca de agua (data URI) para PDF sin depender de red."""
    css_path = os.path.join(_ROOT, "static", "css", "camino-fusion-bentley.css")
    if os.path.isfile(css_path):
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        html = re.sub(
            r'<link[^>]+camino-fusion-bentley\.css[^>]*>',
            f"<style>{css}</style>",
            html,
            count=1,
        )

    if _WATERMARK_PLACEHOLDER in html and (
        os.path.isfile(_WATERMARK_SVG) or os.path.isfile(_WATERMARK_PNG)
    ):
        uri = watermark_data_uri()
        if uri:
            html = html.replace(_WATERMARK_PLACEHOLDER, uri)

    if _HEADER_LOGO_PLACEHOLDER in html and os.path.isfile(_WATERMARK_SVG):
        logo_uri = header_logo_data_uri()
        if logo_uri:
            html = html.replace(_HEADER_LOGO_PLACEHOLDER, logo_uri)

    return html


_BENTLEY_PAGE_W_PT = 1368
_BENTLEY_PAGE_H_PT = 943
_PT_TO_PX = 96 / 72


def _pdf_playwright(html: str, base_url: str) -> bytes:
    del base_url
    from playwright.sync_api import sync_playwright

    launch_opts: dict = {"headless": True}
    if shutil.which("google-chrome") or shutil.which("chromium"):
        launch_opts["channel"] = "chrome"

    viewport_w = int(_BENTLEY_PAGE_W_PT * _PT_TO_PX)
    viewport_h = int(_BENTLEY_PAGE_H_PT * _PT_TO_PX)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_opts)
        page = browser.new_page(viewport={"width": viewport_w, "height": viewport_h})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(800)
        pdf = page.pdf(
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()
        return pdf


def _pdf_chrome(html: str, base_url: str) -> bytes:
    del base_url
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise RuntimeError("No hay navegador headless (Playwright ni Chrome/Chromium).")

    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "report.html")
        pdf_path = os.path.join(tmp, "report.pdf")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=8000",
                f"--print-to-pdf={pdf_path}",
                "--no-pdf-header-footer",
                f"file://{html_path}",
            ],
            check=True,
            capture_output=True,
        )
        with open(pdf_path, "rb") as fh:
            return fh.read()
