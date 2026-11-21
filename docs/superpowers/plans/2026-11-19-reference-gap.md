# Plume visual and performance plan

**Goal** Bring Plume closer to the supplied reference’s cloud depth, foreground contact shading, and directional lighting, with 120 FPS as the target for the matched Balanced scene.

**Scope** Start from raster-only 0.6.7 on Horizon Shader API 0.2. Keep the installed shader and both game profiles as the comparison controls. Work in the order below so the cloud savings can fund any added contact shading.

## What the comparison shows

- **Clouds and atmospheric depth.** This is the largest visible gap. The reference has broken, fine-edged cumulus, brighter sun-facing edges, darker undersides and many cloud scales toward the horizon. Plume’s clouds look smoother, and repeated bands are visible near the top of the comparison. The reference also fades distant terrain more decisively into the horizon. Use the noon sky and overcast references as separate targets.
- **Foreground and sunlight.** The reference grounds grass clumps and stair-stepped terrain with short shadows at their bases. It also separates sunny faces from shaded ones more strongly and has warmer transmission through grass and cane when backlit. Framing differs between the two sides. Match the camera and sun angle before adjusting the palette, fog or exposure.
- **Existing AO.** Horizon supplies vertex AO, face shading and biome color together in the material tint, and Plume uses it. The pack has no screen-space contact AO pass. The terrain’s broad noon fill can also soften local contrast, so check each contribution before deciding how much additional AO is useful. [Terrain material](../../../horizon_lighting/material.wgsl) · [Diffuse lighting](../../../horizon_lighting/lighting.wgsl) · [Milestone 6](../../../Horizon_Lighting_Updated_Roadmap.md#milestone-6--add-contact-ambient-occlusion)

## What the timing establishes

The comparison overlay shows **61 FPS, 16.3 ms frame time, 15.4 ms GPU and 4.6 ms CPU** on Plume. GPU time is the strongest lead for that view. **120 FPS means an 8.33 ms total frame budget.** The local Iris profile selects Photon v1.4 with Sodium present, so engine, mod and preset differences are plausible factors. The screenshot gives no matched CPU/GPU baseline for Photon.

An isolated A/B ran the same **0.6.7** archive on Vulkan with the RTX 4050 Laptop GPU at 2000×1125, 12 chunks, clear weather and fixed time. Only `volumetric_clouds` changed. The flat mode replaces the volume and uses the cheaper cloud-shadow calculation. Each cell is one five-second sample.

| GoldenLab view | Default GPU mean / p95 | Flat cloud GPU mean / p95 | Mean saved |
| --- | ---: | ---: | ---: |
| Valley, terrain in frame | 9.64 / 10.06 ms | 4.41 / 4.59 ms | 5.23 ms |
| Tilted up, sky-heavy | 4.77 / 4.87 ms | 2.95 / 3.15 ms | 1.82 ms |

The larger valley delta makes per-surface cloud-light transmission a leading suspect. The switch also changes sky and reflected-cloud paths, so the probe leaves attribution among them open. Keep the flat mode available as a low-cost preset. [Benchmark script](../../../.tools/reference-gap/bench.ctl) · [Default log](../../../.tools/reference-gap/default.log) · [Flat-cloud log](../../../.tools/reference-gap/flat-clouds.log)

## Work order

### 1. Measure the actual comparison scene

- [ ] Capture the same world, coordinates, yaw, pitch, FOV, sun angle, weather and exposure. Match internal pixel size, render and simulation distance, shadow coverage and quality as closely as each renderer allows. Record backend, GPU, mods, presets and actual render scale. For benchmark runs, disable FPS caps, VSync and dynamic resolution in the test copies.
- [ ] Record CPU and GPU frame time plus p95 over at least three warm runs for both clients with shaders off and with their respective packs on. Measure the fixed valley, a view mostly filled by sky, and the water-facing view. Keep a short flight for motion and streaming. Compare shader-on against shader-off within each client to distinguish renderer overhead from the cost of the packs.
- [ ] Use Horizon’s `gpu-passes detail` and individual feature switches to rank cloud volume, water mirror, glossy SSR, shafts, shadows and full-resolution post work. Use whole-frame deltas when the pinned client reports only some pass labels. Record exact configurations with the captures. The result of this step is a ranked table in milliseconds. [Existing benchmark workflow](../../../README.md#in-game-visual-checklist)

### 2. Resume Milestone 3 with cloud cost and shape together

- [ ] In `common.wgsl`, isolate `cloud_light_transmission()` from `cloud_volume()` in disposable test builds. The terrain path currently uses the 16-step cloud budget too. First try a cheaper, filtered cloud-shadow lookup with the existing density, wind and weather inputs. Hold visible sky quality fixed for that test, then measure terrain and water views again.
- [ ] Improve the visible cloud silhouette and lighting with the savings. Tune irregular coverage, filtered edge detail, undersides and sun-facing illumination inside the existing bounded layer. Check the clear-to-overcast transition before considering another layer. Keep terrain cloud shadows, shafts and reflections in phase. Compare slow pans and flight for banding, swimming and reflection mismatches. [Cloud implementation](../../../horizon_lighting/common.wgsl) · [Milestone 3](../../../Horizon_Lighting_Updated_Roadmap.md#milestone-3--add-clouds-and-connect-them-to-sunlight)

### 3. Tune directional light before adding AO

- [ ] In `lighting.wgsl`, capture ambient and direct light separately in a test build. A/B the broad noon fill and shade floor on a sand staircase, open grass and a forest edge. Aim for warm sunlit faces, cool readable shade and visible texture in the grass. Check sunset and overcast as controls.
- [ ] Use the existing thin-foliage response for backlit grass and leaves. Try a targeted cane material mapping in `horizon-shaders.toml` and `gloss.wgsl` if matched front/back captures still show a gap. Check that an opaque wall still stops transmission.
- [ ] Match the distant land-to-sky separation with the existing `fog.wgsl` curve after the lights match. Use the distant valley and shoreline for this test. Keep the clear foreground and single application of water fog.

### 4. Prototype contact AO only where the matched views still need it

- [ ] First compare the baked contact shading on sand, a wall base and grass roots after step 3. If the surfaces still look ungrounded, try a small-radius half-resolution depth/normal AO pass in `post/contact_ao.wgsl`, with edge-aware reconstruction in `post/composite.wgsl`. Keep it optional and preserve the existing surface metadata layout.
- [ ] The pinned API gives post-processing an already lit scene color. For the first prototype use a bounded correction on eligible opaque terrain, fading with distance and haze. Reserve ambient-only composition for an explicit lighting input if the approximation proves visibly wrong. Inspect silhouettes, foreground cutouts, hands, water, emissives, caves and camera motion for halos or double-darkening.
- [ ] Keep the prototype only if contact shading is visibly better in both sun and overcast and the median added GPU cost stays within a provisional **0.5 ms** on the matched scene. Run `./tools/check.ps1` after each shader change that survives the visual and timing comparison.
