"""Build the unified optional Horizon Lighting companion resource pack.

Includes:
- Round lunar phases (assets/minecraft/textures/environment/celestial/moon/*.png)
- Subtle translucent rain splash particles (assets/minecraft/textures/particle/splash_0..3.png)
  to match Horizon Lighting's custom translucent rain streaks without vanilla blue dots.
"""

import json
from math import cos, exp, hypot, pi, sin, sqrt
from pathlib import Path
from random import Random
from struct import pack
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from zlib import compress, crc32


MOON_SIZE = 128
MOON_RADIUS = 17.5
MOON_PHASES = (
    "full_moon", "waning_gibbous", "third_quarter", "waning_crescent",
    "new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous",
)
MOON_BASINS = ((-0.34, -0.27, 0.36), (0.24, -0.42, 0.27), (0.42, -0.11, 0.22),
               (-0.39, 0.22, 0.18), (0.10, 0.33, 0.19))

SPLASH_SIZE = 32
# Each frame is a list of delicate, separated micro-droplets: (cx, cy, rx, ry, peak_alpha)
# in normalized [0, 1] UV coordinates (y=0 top, y=1 bottom near ground impact).
SPLASH_FRAMES = (
    # Frame 0: tiny soft impact bead and faint mist kiss right at the surface.
    (
        (0.50, 0.80, 0.11, 0.05, 0.24),
        (0.46, 0.72, 0.032, 0.048, 0.34),
        (0.55, 0.74, 0.028, 0.042, 0.30),
    ),
    # Frame 1: 3 delicate micro-droplets lifting apart cleanly (no chunky clusters).
    (
        (0.36, 0.62, 0.028, 0.048, 0.32),
        (0.52, 0.56, 0.025, 0.052, 0.30),
        (0.66, 0.64, 0.028, 0.046, 0.28),
        (0.50, 0.82, 0.14, 0.04, 0.14),
    ),
    # Frame 2: fine dispersed mist beads arcing outward and fading.
    (
        (0.27, 0.58, 0.024, 0.036, 0.22),
        (0.47, 0.50, 0.022, 0.034, 0.20),
        (0.73, 0.60, 0.024, 0.036, 0.20),
        (0.60, 0.68, 0.020, 0.028, 0.16),
    ),
    # Frame 3: faint dissolving water specks.
    (
        (0.22, 0.68, 0.020, 0.028, 0.12),
        (0.44, 0.60, 0.018, 0.026, 0.11),
        (0.77, 0.70, 0.020, 0.028, 0.11),
    ),
)


def clamp(value):
    return min(max(value, 0.0), 1.0)


def png_chunk(kind, data):
    return pack(">I", len(data)) + kind + data + pack(">I", crc32(kind + data))


def encode_rgba_png(size, rows):
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", pack(">2I5B", size, size, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", compress(rows))
            + png_chunk(b"IEND", b""))


def moon_surface():
    rng = Random(73)
    craters = [(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.023, 0.145)) for _ in range(54)]
    for row in range(MOON_SIZE):
        for column in range(MOON_SIZE):
            x = (column + 0.5 - MOON_SIZE / 2) / MOON_RADIUS
            y = (row + 0.5 - MOON_SIZE / 2) / MOON_RADIUS
            distance = hypot(x, y)
            edge = clamp((1.0 - distance) * MOON_RADIUS + 0.5)
            depth = sqrt(max(0.0, 1.0 - distance * distance))
            maria = sum(exp(-((x - cx) ** 2 + (y - cy) ** 2) / radius ** 2) for cx, cy, radius in MOON_BASINS)
            detail = 0.0
            if edge > 0.0:
                for cx, cy, radius in craters:
                    crater = hypot(x - cx, y - cy) / radius
                    if crater < 1.35:
                        detail += 0.046 * exp(-((crater - 0.90) / 0.17) ** 2) - 0.071 * exp(-2.3 * crater ** 2)
            albedo = 0.88 - 0.24 * maria + detail + 0.025 * sin(51 * x + 29 * y) * cos(35 * y - 19 * x)
            yield x, depth, edge, albedo


def moon_png(surface, phase):
    angle = phase * pi / 4
    # The renderer flips the moon's atlas U coordinate in its celestial quad.
    light_x, light_depth = -sin(angle), cos(angle)
    rows = bytearray()
    for index, (x, depth, edge, albedo) in enumerate(surface):
        if index % MOON_SIZE == 0:
            rows.append(0)
        facing = x * light_x + depth * light_depth
        alpha = edge * clamp(facing * MOON_RADIUS + 0.5) if phase != 4 else 0.0
        value = albedo * (0.68 + 0.32 * max(0.0, facing) ** 0.45)
        rows.extend(round(255 * clamp(value * tint)) for tint in (0.95, 0.98, 1.04))
        rows.append(round(255 * alpha))
    return encode_rgba_png(MOON_SIZE, rows)


def splash_png(droplets):
    rows = bytearray()
    for py in range(SPLASH_SIZE):
        rows.append(0)
        v = (py + 0.5) / SPLASH_SIZE
        for px in range(SPLASH_SIZE):
            u = (px + 0.5) / SPLASH_SIZE
            alpha = 0.0
            for cx, cy, rx, ry, peak in droplets:
                dx = (u - cx) / rx
                dy = (v - cy) / ry
                d2 = dx * dx + dy * dy
                if d2 < 3.5:
                    alpha = max(alpha, peak * exp(-1.6 * d2))
            if alpha < 0.015:
                rows.extend((0, 0, 0, 0))
            else:
                # Cool translucent water mist matching Horizon Lighting's weather.wgsl streaks.
                rows.extend((216, 224, 232, round(255 * clamp(alpha))))
    return encode_rgba_png(SPLASH_SIZE, rows)


def main():
    distribution = Path(__file__).resolve().parents[1] / "dist" / "horizon-lighting-resources.zip"
    metadata = {"pack": {"description": "Horizon Lighting | Round moon & clear rain splashes",
                         "min_format": [97, 1], "max_format": [97, 1]}}
    surface = list(moon_surface())
    with ZipFile(distribution, "w") as archive:
        archive.writestr(ZipInfo("pack.mcmeta"), json.dumps(metadata), compress_type=ZIP_DEFLATED)
        for phase, name in enumerate(MOON_PHASES):
            path = f"assets/minecraft/textures/environment/celestial/moon/{name}.png"
            archive.writestr(ZipInfo(path), moon_png(surface, phase), compress_type=ZIP_DEFLATED)
        for index, droplets in enumerate(SPLASH_FRAMES):
            path = f"assets/minecraft/textures/particle/splash_{index}.png"
            archive.writestr(ZipInfo(path), splash_png(droplets), compress_type=ZIP_DEFLATED)
    print(distribution)


if __name__ == "__main__":
    main()
