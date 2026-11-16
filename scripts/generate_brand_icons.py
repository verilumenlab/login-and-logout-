"""Generate WorkPulse brand icons for web, Electron installer, and desktop UI."""

from __future__ import annotations

import shutil
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC_CANDIDATES = [
    ROOT / "brand" / "workpulse-logo-source.jpg",
    Path(r"C:\Users\subha\.cursor\projects\c-login-and-logout\assets\image-7d952cc4-4c1b-43b5-a798-42f19864a77f.jpg"),
]


def find_source() -> Path:
    for p in SRC_CANDIDATES:
        if p.is_file():
            return p
    raise FileNotFoundError("WorkPulse logo source image not found")


def write_png_ico(canvas: Image.Image, dest: Path, sizes: list[int]) -> None:
    """Write a multi-resolution .ico with PNG-compressed frames (Windows Vista+)."""
    entries: list[tuple[int, bytes]] = []
    for s in sizes:
        im = canvas.resize((s, s), Image.Resampling.LANCZOS)
        buf = BytesIO()
        im.save(buf, format="PNG")
        entries.append((s, buf.getvalue()))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    entry_bytes = b""
    blob = b""
    for s, data in entries:
        wb = 0 if s >= 256 else s
        hb = 0 if s >= 256 else s
        entry_bytes += struct.pack("<BBBBHHII", wb, hb, 0, 0, 1, 32, len(data), offset)
        blob += data
        offset += len(data)
    dest.write_bytes(header + entry_bytes + blob)


def main() -> None:
    src = find_source()
    brand_dir = ROOT / "brand"
    brand_dir.mkdir(parents=True, exist_ok=True)
    dest_src = brand_dir / "workpulse-logo-source.jpg"
    if src.resolve() != dest_src.resolve():
        shutil.copy2(src, dest_src)

    img = Image.open(dest_src).convert("RGBA")
    w, h = img.size
    print(f"source {w}x{h} from {dest_src}")

    web_brand = ROOT / "web" / "public" / "brand"
    web_public = ROOT / "web" / "public"
    desktop_public = ROOT / "desktop" / "public"
    desktop_build = ROOT / "desktop" / "build"
    tauri_icons = ROOT / "desktop" / "src-tauri" / "icons"
    for d in (web_brand, web_public, desktop_public, desktop_build, tauri_icons):
        d.mkdir(parents=True, exist_ok=True)

    # Full logo (white background) for headers / login
    full_white = Image.new("RGB", (w, h), (255, 255, 255))
    full_white.paste(img.convert("RGB"), (0, 0))
    full_white.save(web_brand / "workpulse-logo.png", optimize=True)
    full_white.save(desktop_public / "workpulse-logo.png", optimize=True)
    shutil.copy2(dest_src, web_brand / "workpulse-logo.jpg")

    # Crop mark (icon above wordmark)
    mark_bottom = int(h * 0.62)
    mark = img.crop((0, 0, w, mark_bottom))
    side = max(mark.size)
    pad = int(side * 0.08)
    canvas_size = side + pad * 2
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
    ox = (canvas_size - mark.width) // 2
    oy = (canvas_size - mark.height) // 2
    canvas.paste(mark, (ox, oy), mark)

    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    sized: dict[int, Image.Image] = {}
    for s in sizes:
        resized = canvas.resize((s, s), Image.Resampling.LANCZOS)
        sized[s] = resized
        resized.save(desktop_build / f"icon-{s}.png")

    sized[512].save(desktop_build / "icon.png")
    sized[512].save(web_public / "icon-512.png")
    sized[32].save(web_public / "favicon-32.png")
    sized[16].save(web_public / "favicon-16.png")
    canvas.resize((180, 180), Image.Resampling.LANCZOS).save(web_public / "apple-touch-icon.png")
    sized[128].save(web_brand / "workpulse-mark.png")
    sized[128].save(desktop_public / "workpulse-mark.png")

    # Tauri / legacy icon paths
    sized[32].save(tauri_icons / "32x32.png")
    sized[128].save(tauri_icons / "128x128.png")
    sized[256].save(tauri_icons / "128x128@2x.png")

    ico_path = desktop_build / "icon.ico"
    write_png_ico(canvas, ico_path, [16, 24, 32, 48, 64, 128, 256])
    write_png_ico(canvas, tauri_icons / "icon.ico", [16, 24, 32, 48, 64, 128, 256])

    # NSIS installer sidebar / header bitmaps (electron-builder optional)
    header = Image.new("RGB", (150, 57), (255, 255, 255))
    mark_h = canvas.resize((48, 48), Image.Resampling.LANCZOS).convert("RGB")
    header.paste(mark_h, (12, (57 - 48) // 2))
    header.save(desktop_build / "installerHeader.bmp")

    sidebar = Image.new("RGB", (164, 314), (15, 23, 42))  # slate-900
    mark_s = canvas.resize((96, 96), Image.Resampling.LANCZOS).convert("RGB")
    sidebar.paste(mark_s, ((164 - 96) // 2, 40))
    sidebar.save(desktop_build / "installerSidebar.bmp")

    print(f"ICO {ico_path} ({ico_path.stat().st_size} bytes)")
    print("Brand icons generated for web + Electron installer")


if __name__ == "__main__":
    main()
