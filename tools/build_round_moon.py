"""Build the optional Horizon round moon sprites without external assets."""

import json
from math import cos, exp, hypot, pi, sin, sqrt
from pathlib import Path
from random import Random
from struct import pack
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from zlib import compress, crc32


SIZE = 128
RADIUS = 17.5
PHASES = (
    "full_moon", "waning_gibbous", "third_quarter", "waning_crescent",
    "new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous",
)
BASINS = ((-0.34, -0.27, 0.36), (0.24, -0.42, 0.27), (0.42, -0.11, 0.22),
          (-0.39, 0.22, 0.18), (0.10, 0.33, 0.19))


def clamp(value):
    return min(max(value, 0.0), 1.0)


def moon_surface():
    rng = Random(73)
    craters = [(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.023, 0.145)) for _ in range(54)]
    for row in range(SIZE):
        for column in range(SIZE):
            x = (column + 0.5 - SIZE / 2) / RADIUS
            y = (row + 0.5 - SIZE / 2) / RADIUS
            distance = hypot(x, y)
            edge = clamp((1.0 - distance) * RADIUS + 0.5)
            depth = sqrt(max(0.0, 1.0 - distance * distance))
            maria = sum(exp(-((x - cx) ** 2 + (y - cy) ** 2) / radius ** 2) for cx, cy, radius in BASINS)
            detail = 0.0
            if edge > 0.0:
                for cx, cy, radius in craters:
                    crater = hypot(x - cx, y - cy) / radius
                    if crater < 1.35:
                        detail += 0.046 * exp(-((crater - 0.90) / 0.17) ** 2) - 0.071 * exp(-2.3 * crater ** 2)
            albedo = 0.88 - 0.24 * maria + detail + 0.025 * sin(51 * x + 29 * y) * cos(35 * y - 19 * x)
            yield x, depth, edge, albedo


def png_chunk(kind, data):
    return pack(">I", len(data)) + kind + data + pack(">I", crc32(kind + data))


def moon_png(surface, phase):
    angle = phase * pi / 4
    # The renderer flips the moon's atlas U coordinate in its celestial quad.
    light_x, light_depth = -sin(angle), cos(angle)
    rows = bytearray()
    for index, (x, depth, edge, albedo) in enumerate(surface):
        if index % SIZE == 0:
            rows.append(0)
        facing = x * light_x + depth * light_depth
        alpha = edge * clamp(facing * RADIUS + 0.5) if phase != 4 else 0.0
        value = albedo * (0.68 + 0.32 * max(0.0, facing) ** 0.45)
        rows.extend(round(255 * clamp(value * tint)) for tint in (0.95, 0.98, 1.04))
        rows.append(round(255 * alpha))
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", pack(">2I5B", SIZE, SIZE, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", compress(rows)) + png_chunk(b"IEND", b""))


def main():
    distribution = Path(__file__).resolve().parents[1] / "dist" / "horizon-round-moon.zip"
    metadata = {"pack": {"description": "Horizon Lighting | Round lunar phases",
                         "min_format": [97, 1], "max_format": [97, 1]}}
    surface = list(moon_surface())
    with ZipFile(distribution, "w") as archive:
        archive.writestr(ZipInfo("pack.mcmeta"), json.dumps(metadata), compress_type=ZIP_DEFLATED)
        for phase, name in enumerate(PHASES):
            path = f"assets/minecraft/textures/environment/celestial/moon/{name}.png"
            archive.writestr(ZipInfo(path), moon_png(surface, phase), compress_type=ZIP_DEFLATED)
    print(distribution)


if __name__ == "__main__":
    main()
