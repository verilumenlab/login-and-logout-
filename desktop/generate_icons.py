import struct

# Create minimal valid 32x32 PNG file
# Minimal 1x1 transparent/blue PNG bytes
def make_simple_png(path, width, height):
    # Minimal 1x1 blue PNG
    import zlib
    raw_data = b"".join(b"\x00" + b"\x25\x63\xeb\xff" * width for _ in range(height))
    compressed = zlib.compress(raw_data)
    
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    # IHDR
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xffffffff)
    png.extend(struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + ihdr_crc)
    # IDAT
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xffffffff)
    png.extend(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc)
    # IEND
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xffffffff)
    png.extend(struct.pack(">I", 0) + b"IEND" + iend_crc)
    
    with open(path, "wb") as f:
        f.write(png)

# Make simple ICO file containing a 32x32 image (BMP or PNG format inside ICO)
def make_simple_ico(path, png_path):
    with open(png_path, "rb") as f:
        png_data = f.read()
    
    header = struct.pack("<HHH", 0, 1, 1) # Reserved, Type 1 (ICO), Count 1
    entry = struct.pack(
        "<BBBBHHII",
        32, 32, 0, 0, 1, 32, len(png_data), 6 + 16 # offset 22
    )
    with open(path, "wb") as f:
        f.write(header + entry + png_data)

import os
os.makedirs("desktop/src-tauri/icons", exist_ok=True)
make_simple_png("desktop/src-tauri/icons/32x32.png", 32, 32)
make_simple_png("desktop/src-tauri/icons/128x128.png", 128, 128)
make_simple_png("desktop/src-tauri/icons/128x128@2x.png", 256, 256)
make_simple_ico("desktop/src-tauri/icons/icon.ico", "desktop/src-tauri/icons/32x32.png")
with open("desktop/src-tauri/icons/icon.icns", "wb") as f:
    f.write(open("desktop/src-tauri/icons/128x128.png", "rb").read())
print("Icons successfully created.")

