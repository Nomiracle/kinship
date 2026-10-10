#!/usr/bin/env python3
"""生成合成测试素材（纯标准库，无需 Pillow）。

仓库红线：任何真实照片都不得进入本仓库。测试/截图用的图一律现场生成。

用法：
    python3 tests/fixtures/make_fixture.py            # 默认输出 generated/block.png
    python3 tests/fixtures/make_fixture.py out.png 64 64 "255,0,0"
"""
import os
import struct
import sys
import zlib

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated", "block.png")


def png_bytes(width: int, height: int, rgb: tuple) -> bytes:
    """手搓一个最小 PNG：8-bit truecolor，单色填充。"""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main(argv: list) -> int:
    out = argv[1] if len(argv) > 1 else DEFAULT_OUT
    width = int(argv[2]) if len(argv) > 2 else 48
    height = int(argv[3]) if len(argv) > 3 else 48
    rgb = tuple(int(x) for x in (argv[4] if len(argv) > 4 else "120,144,156").split(","))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(png_bytes(width, height, rgb))
    print(f"wrote {out} ({width}x{height}, rgb{rgb})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
