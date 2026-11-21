"""Build the seamless tileable 512x512 RGBA multi-layer cloud noise texture.

Channels:
  R: Multi-scale Perlin-Worley cumulus base silhouette
  G: Crisp 4-octave inverted Worley cauliflower billow detail
  B: Domain-warped wispy FBM for high-altitude cirrus and fine fluffy edges
  A: Smooth low-frequency macro weather-front coverage field
"""

from math import cos, pi, sin
from pathlib import Path
from random import Random
from struct import pack
from zlib import compress, crc32


SIZE = 512


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def make_perlin_grid(cells, seed):
    rng = Random(seed)
    return [[(cos(a), sin(a)) for a in (rng.uniform(0.0, 2.0 * pi) for _ in range(cells))]
            for _ in range(cells)]


def precompute_perlin(cells, seed):
    """Evaluate a periodic gradient Perlin octave across the full SIZE x SIZE grid."""
    grid = make_perlin_grid(cells, seed)
    inv = cells / SIZE
    # Precompute 1D index and fade tables for speed.
    i0 = [int(k * inv) % cells for k in range(SIZE)]
    i1 = [(v + 1) % cells for v in i0]
    frac = [k * inv - int(k * inv) for k in range(SIZE)]
    fade = [t * t * t * (t * (t * 6.0 - 15.0) + 10.0) for t in frac]

    out = [0.0] * (SIZE * SIZE)
    idx = 0
    for y in range(SIZE):
        y0 = i0[y]
        y1 = i1[y]
        fy = frac[y]
        fy1 = fy - 1.0
        uy = fade[y]
        row0 = grid[y0]
        row1 = grid[y1]
        for x in range(SIZE):
            x0 = i0[x]
            x1 = i1[x]
            fx = frac[x]
            fx1 = fx - 1.0
            ux = fade[x]

            g00 = row0[x0]
            g10 = row0[x1]
            g01 = row1[x0]
            g11 = row1[x1]

            n00 = g00[0] * fx + g00[1] * fy
            n10 = g10[0] * fx1 + g10[1] * fy
            n01 = g01[0] * fx + g01[1] * fy1
            n11 = g11[0] * fx1 + g11[1] * fy1

            nx0 = n00 + (n10 - n00) * ux
            nx1 = n01 + (n11 - n01) * ux
            val = (nx0 + (nx1 - nx0) * uy) * 1.41421356
            if val < -1.0:
                val = -1.0
            elif val > 1.0:
                val = 1.0
            out[idx] = 0.5 + 0.5 * val
            idx += 1
    return out


def make_worley_grid(cells, seed):
    rng = Random(seed)
    return [[(rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.95)) for _ in range(cells)]
            for _ in range(cells)]


def precompute_worley_inv(cells, grid):
    """Evaluate a periodic inverted Worley F1 octave across the full SIZE x SIZE grid."""
    inv = cells / SIZE
    c_idx = [int(k * inv) for k in range(SIZE)]
    c_frac = [k * inv - int(k * inv) for k in range(SIZE)]

    out = [0.0] * (SIZE * SIZE)
    idx = 0
    for y in range(SIZE):
        cy = c_idx[y]
        fy = c_frac[y]
        r_m = grid[(cy - 1) % cells]
        r_0 = grid[cy % cells]
        r_p = grid[(cy + 1) % cells]
        rows3 = ((-1.0 - fy, r_m), (-fy, r_0), (1.0 - fy, r_p))
        for x in range(SIZE):
            cx = c_idx[x]
            fx = c_frac[x]
            xm = (cx - 1) % cells
            x0 = cx % cells
            xp = (cx + 1) % cells
            min_d2 = 9.0
            for dy_base, row in rows3:
                px, py = row[xm]
                dx = -1.0 + px - fx
                dy = dy_base + py
                d2 = dx * dx + dy * dy
                if d2 < min_d2:
                    min_d2 = d2

                px, py = row[x0]
                dx = px - fx
                dy = dy_base + py
                d2 = dx * dx + dy * dy
                if d2 < min_d2:
                    min_d2 = d2

                px, py = row[xp]
                dx = 1.0 + px - fx
                dy = dy_base + py
                d2 = dx * dx + dy * dy
                if d2 < min_d2:
                    min_d2 = d2

            v = 1.0 - min_d2 * 0.86
            out[idx] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            idx += 1
    return out


def sample_bilinear(field, u, v):
    x = (u % 1.0) * SIZE - 0.5
    y = (v % 1.0) * SIZE - 0.5
    x0 = int(x // 1) % SIZE
    y0 = int(y // 1) % SIZE
    x1 = (x0 + 1) % SIZE
    y1 = (y0 + 1) % SIZE
    fx = x - (x // 1)
    fy = y - (y // 1)
    r0 = y0 * SIZE
    r1 = y1 * SIZE
    a = field[r0 + x0] + (field[r0 + x1] - field[r0 + x0]) * fx
    b = field[r1 + x0] + (field[r1 + x1] - field[r1 + x0]) * fx
    return a + (b - a) * fy


def normalize_field(values, lo_target=0.01, hi_target=0.99):
    vmin = min(values)
    vmax = max(values)
    span = max(vmax - vmin, 1e-6)
    scale = (hi_target - lo_target) / span
    return [clamp(lo_target + (v - vmin) * scale) for v in values]


def png_chunk(kind, data):
    return pack(">I", len(data)) + kind + data + pack(">I", crc32(kind + data))


def build_cloud_noise():
    n = SIZE * SIZE

    # Base Perlin octaves
    p2 = precompute_perlin(2, 1313)
    p3 = precompute_perlin(3, 79)
    p4 = precompute_perlin(4, 101)
    p6 = precompute_perlin(6, 151)
    p8 = precompute_perlin(8, 202)
    p12 = precompute_perlin(12, 257)
    p16 = precompute_perlin(16, 303)
    p32 = precompute_perlin(32, 353)
    p64 = precompute_perlin(64, 389)

    # Inverted Worley octaves for crisp cauliflower cumulus tufts
    w4 = precompute_worley_inv(4, make_worley_grid(4, 404))
    w8 = precompute_worley_inv(8, make_worley_grid(8, 505))
    w32 = precompute_worley_inv(32, make_worley_grid(32, 707))
    w64 = precompute_worley_inv(64, make_worley_grid(64, 808))

    # Secondary Worley seed for rich billow detail channel (G)
    g8 = precompute_worley_inv(8, make_worley_grid(8, 911))
    g16 = precompute_worley_inv(16, make_worley_grid(16, 1019))
    g32 = precompute_worley_inv(32, make_worley_grid(32, 1123))
    g64 = precompute_worley_inv(64, make_worley_grid(64, 1231))

    # Cirrus domain-warp & wispy base fields
    cw_x = precompute_perlin(4, 1427)
    cw_y = precompute_perlin(4, 1543)
    c_base = [0.46 * p4[i] + 0.27 * p8[i] + 0.15 * p16[i] + 0.08 * p32[i] + 0.04 * p64[i]
              for i in range(n)]

    r_raw = [0.0] * n
    g_raw = [0.0] * n
    b_raw = [0.0] * n
    a_raw = [0.0] * n

    inv_size = 1.0 / SIZE
    for i in range(n):
        # R: Smooth low-frequency Perlin-Worley volumetric envelope (Nyquist-safe against raymarch slicing).
        pb = 0.56 * p3[i] + 0.30 * p6[i] + 0.14 * p12[i]
        wb = 0.65 * w4[i] + 0.35 * w8[i]
        w_floor = (1.0 - wb) * 0.42
        pw = clamp((pb - w_floor) / max(1.0 - w_floor, 0.30))
        r_raw[i] = 0.42 * pb + 0.58 * pw

        # G: Crisp 4-octave inverted Worley cauliflower tufts (8..64 cells across 512px).
        g_raw[i] = 0.44 * g8[i] + 0.28 * g16[i] + 0.18 * g32[i] + 0.10 * g64[i]

        # A: Smooth low-frequency macro weather front coverage field.
        a_raw[i] = 0.62 * p2[i] + 0.28 * p4[i] + 0.10 * p8[i]

    # B: Domain-warped wispy cirrus & high-frequency cotton detail.
    idx = 0
    for y in range(SIZE):
        v = (y + 0.5) * inv_size
        for x in range(SIZE):
            u = (x + 0.5) * inv_size
            wx = (cw_x[idx] - 0.5) * 0.22
            wy = (cw_y[idx] - 0.5) * 0.22
            # Gently anisotropic stretched domain warp produces realistic silky cirrus filaments.
            warped = sample_bilinear(c_base, u + wx, v * 2.0 + wy * 0.65)
            wisps = sample_bilinear(c_base, u * 2.0 - wy * 0.8, v + wx * 0.8)
            fine = 0.55 * w32[idx] + 0.45 * w64[idx]
            b_raw[idx] = 0.54 * warped + 0.28 * wisps + 0.18 * fine
            idx += 1

    r_norm = normalize_field(r_raw, 0.01, 0.99)
    g_norm = normalize_field(g_raw, 0.01, 0.99)
    b_norm = normalize_field(b_raw, 0.01, 0.99)
    a_norm = normalize_field(a_raw, 0.03, 0.97)

    rows = bytearray()
    idx = 0
    for _ in range(SIZE):
        rows.append(0)
        for _ in range(SIZE):
            rows.append(round(255.0 * r_norm[idx]))
            rows.append(round(255.0 * g_norm[idx]))
            rows.append(round(255.0 * b_norm[idx]))
            rows.append(round(255.0 * a_norm[idx]))
            idx += 1

    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", pack(">2I5B", SIZE, SIZE, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", compress(rows, level=6))
            + png_chunk(b"IEND", b""))


def main():
    out = Path(__file__).resolve().parents[1] / "horizon_lighting" / "cloud-noise.png"
    out.write_bytes(build_cloud_noise())
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
