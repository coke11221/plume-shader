# Photon-inspired Horizon Lighting roadmap

Bring Photon’s outdoor depth, soft lighting, and weather to Horizon Lighting in independently testable updates. Keep Horizon’s golden-hour palette, readable vanilla textures, and raster-only WGSL pipeline. The starting point is Horizon Lighting **0.3.9**, Shader API **0.2**, and the tested November 16 client **`85b5bcca`**.

**Current checkpoint** · 0.4.4 reduces the default aerial perspective strength and applies it to mobs and block entities. The next feature is Milestone 3. See the [handoff](../../NEXT-SESSION.md) and [fog validation](../../../validation/0.4.4/REVIEW.md).

Use the [cherry cliffs](https://media.forgecdn.net/attachments/1264/6/photon_cy2-jpg.jpg) as the target for sun/shade separation and the [rainbow valley](https://media.forgecdn.net/attachments/1264/5/p3-webp.webp) as the target for distance layering. The cliff shot uses custom settings. The [Photon source](https://github.com/sixthsurge/photon) explains the techniques. The [pinned Horizon API](https://github.com/horizon-rust/horizon/blob/85b5bcca7c79bb470b90bdb5914b413aa66fe7ae/docs/api/shaders-reference-0.2.md) determines which inputs the pack can use.

## How to work through the roadmap

- Take one milestone at a time. Before editing WGSL, use its implementation notes and acceptance checks to write the small plan for that milestone. Capture the current result, implement the feature in isolation, and compare it against the immediately preceding accepted build. Preserve the 0.3.9 captures as a long-term reference.
- Keep comparisons controlled. Record the world, camera position and orientation, time, weather, resolution, render distance, shadow settings, GPU/backend, and client revision. For animated effects, capture a short pan or transition as well as a still. Use an isolated profile or fixture world.
- Reuse the pack’s existing stages and settings where possible. Preserve color management, biome tints, alpha coverage, plain white torch light, dry grass and rain sheen, status effects, dimension fallbacks, and clear water. Treat each milestone’s proposed files and algorithm as starting points to verify on the current baseline.
- Run `./tools/check.ps1` from the project root for manifest, shader translation, and distribution checks. Check whether the optional GPU tests ran or skipped. For a release archive, run `./tools/check.ps1 -Package` and load the resulting `.hshader` in the isolated client. Record the visual result and timing alongside the build identity.
- Compare GPU timings on the same hardware and camera route, starting with the RTX 4050 Laptop GPU on Vulkan. Record the whole-frame delta and individual effects when exposed, including shadow and planar mirror costs. Use the existing 4 ms shader authoring target as a budgeting reference. Set quality defaults from measurements and leave expensive tiers optional when appropriate.
- Account for the API limits when adding passes. The pinned reference allows 12 post entries, 16 named outputs, 64 options, and a shared target memory budget. There are seven raster post entries today. Prefer reduced-resolution targets or reuse existing stages before adding another full-resolution pass.

## Milestone 0 · Establish the comparison scenes

- [ ] **Build a repeatable baseline.** Start with a wooded valley viewed from a ridge and a low sun crossing a cliff face. Reuse existing lake, underwater, and Nether emitter fixtures where possible. Add a small test area with a wall and detached overhang, leaves, stained glass, and two differently colored light sources separated by a wall and doorway. Capture noon, sunset, overcast, night, and an underwater view as applicable.
- **Accept when** the capture setup records enough settings to repeat the view, the 0.3.9 archive loads with ray tracing disabled, and the baseline records frame timing over a fixed route. Use the existing [0.3.9 runtime record](../../../validation/0.3.9/runtime.json) as a template.

## Milestone 1 · Give the sky and terrain a shared lighting model

- [x] **Build a directional sky model.** Start in `common.wgsl`, `sky.wgsl`, and `lighting.wgsl`. Use sun elevation and weather to define zenith color, horizon color, and the warm region around the sun. Use the same model for visible sky, direct-light color, and broad normal-dependent sky fill. Keep the vanilla skylight level as a visibility proxy for caves and roofs. Use the analytic model as the first approximation of Photon’s spherical-harmonic sky lighting, since material shaders cannot read computed kept resources on this baseline. Grade green Overworld vegetation toward natural biome colors.
- **Accept when** an open shaded face picks up sky color, a roofed room stays darker than outdoor shade, and a noon-to-sunset transition keeps grass green and sunlit stone readable. Review a neutral block on top, side, and under faces at noon, sunset, and night.

## Milestone 2 · Add height-dependent aerial perspective

- [x] **Make terrain recede into the sky.** Build on `fog.wgsl` and `post/composite.wgsl`. Use camera-relative ray height and distance to integrate a simple height-dependent density. Color the haze from the shared sky model, with a restrained forward-scattering component toward the sun. Reuse the current fog ownership where possible. Trace the material, opaque snapshot, water, and post paths so transmitted scenery receives fog once. Keep medium and status-effect routing intact.
- **Accept when** successive ridgelines pick up the horizon color while the near canopy holds its contrast. Compare the same view toward and away from the sun. Check shorelines, a clear submerged view, and a camera passing through fog without visible bands or abrupt transitions.

## Milestone 3 · Add clouds and connect them to sunlight

- [ ] **Render a bounded cloud layer.** Start with one world-anchored procedural layer and a low-cost sky-stage implementation. Add limited thickness or ray-marched lighting once the cloud silhouettes and motion read well. Share the coverage, world anchoring, wind, and weather inputs with an approximate sun-ray lookup in `lighting.wgsl`. Apply cloud attenuation to direct light first, then reuse it in `post/atmosphere.wgsl` when the approximation agrees with the cloud render. Keep a low-cost mode. The `[sky] clouds` switch is a manifest setting, so explicitly define what toggling the new effect does within the pack.
- **Accept when** clouds move continuously as the camera crosses chunks and their shading moves across terrain in the expected direction. Compare clear, broken cloud, and overcast scenes. Check composition with terrain silhouettes, reflections, and dimension-specific sky behavior. Add a second layer only if it improves the scene within the measured budget.

## Milestone 4 · Soften sun and moon shadow edges with distance

- [ ] **Add a variable-width shadow filter.** Extend `shadow.wgsl` with a bounded blocker search and a depth-dependent penumbra. Use the engine’s orthographic shadow depth, mapping, distortion, and texel scale. Preserve bias and out-of-range behavior. Keep a cheap filter tier and start with the advanced filter on surface receivers. Keep volumetric shadow lookups inexpensive and measure shafts with the new surface mode enabled. [Photon shadow reference](https://github.com/sixthsurge/photon/blob/main/shaders/include/lighting/shadows/pcss.glsl)
- **Accept when** a post’s ground contact stays tight and a high overhang casts a wider edge. Inspect foliage, silhouettes, the shadow-map boundary, and a slow pan for acne, detached edges, or flicker. Compare the modes at the same map resolution and coverage.

## Milestone 5 · Add stained-glass transmission

- [ ] **Apply colored sunlight in the shadowed region.** Sample `shadow_map`, `shadow_map_translucent`, and `shadow_color` to distinguish opaque occlusion from translucent transmission. Feed RGB visibility into direct diffuse and specular lighting, with an explicit treatment for water and clear glass. Once surface transmission passes, try tinted shafts as a separate change using the same visibility rules. Horizon exposes the nearest translucent caster; use that as the scope of the first implementation.
- **Accept when** red and blue glass paint distinct patches, opaque blocks still fully occlude the transmitted light, and clear glass leaves the scene close to the untreated case. Test overlapping panes, water, map boundaries, and the shadows-off setting.

## Milestone 6 · Add contact ambient occlusion

- [ ] **Prototype half-resolution GTAO.** Reconstruct the depth neighborhood and use `surface_at` normals where solid terrain metadata exists. Start with scalar AO and edge-aware upsampling in post. Apply it selectively to the ambient contribution or use a bounded shaded-area approximation. Define how the pass identifies eligible receivers given the already lit scene color. The current `set_surface` payload carries packed reflection F0, so preserve its meaning if adding metadata. Evaluate bent normals only when they can improve directional fill through a supported composition path. [Photon AO reference](https://github.com/sixthsurge/photon/blob/main/shaders/program/d3_ao.fsh)
- **Accept when** stair treads, cliff seams, and the bases of trees gain contact depth while sunlit faces keep their brightness. Check for dark halos around the skyline and for spill onto water, glass, entities, and sky. Verify glossy surfaces still receive the right reflection tint.

## Milestone 7 · Improve foliage and material response

- [ ] **Light thin foliage from the back.** Keep existing two-sided grass shading and add a controlled transmission term for eligible leaves and thin plants. Use light direction, shadow visibility, and material tags to keep trunks and soil opaque. Evaluate vertex wind separately if the still comparisons show foliage is a meaningful gap. Use the shared deformation path so the visible foliage and its shadow stay aligned.
- [ ] **Add optional LabPBR materials.** After foliage is accepted, wire the API’s normal and specular maps into material shading and existing gloss. Start with normal direction, roughness, and emission. Respect the engine’s defaults when maps are absent, and retain the current sprite finishes for vanilla textures. Scope relief or parallax to a later experiment if it warrants the cost.
- **Accept when** backlit leaves gain a soft colored rim and covered foliage stays dark. Verify normal and roughness response on a known LabPBR material, then load vanilla textures and confirm dry and wet grass finishes, alpha edges, emissive blocks, polished metals, and HDR highlights still behave as expected.

## Milestone 8 · Refine water and environment reflections

- [ ] **Make reflection fallbacks agree with the sky.** Reuse the sky model for the analytic environment fallback in `water.wgsl` and polished-surface shading. Improve transitions between screen-space hits, the horizontal planar mirror, and the environment using Fresnel, roughness, and hit confidence. The mirror contains terrain over the engine sky gradient. Keep that constraint explicit when evaluating cloud and sky continuity.
- [ ] **Prototype underwater caustics.** After the reflection transition is accepted, add a restrained pattern from the existing wave field to shallow, sunlit receivers. Gate it on water depth and sun visibility. Preserve the clear transmission path and existing underwater rays. Keep rain puddle tuning separate and limited to suitable surfaces.
- **Accept when** a grazing lake view and a pool at a different elevation both transition smoothly as the camera turns. Check out-of-screen hits, oblique shorelines, waterfalls, and cave pools. Caustics should move across a shallow lakebed and disappear under a solid roof.

## Milestone 9 · Improve exposure, highlight roll-off, and bloom

- [ ] **Tune the display curve with fixed exposure.** Refine `tonemap.wgsl` with the noon sky, dark caves, sunset highlights, lava, and saturated lights in view. Compare SDR and available HDR captures. Keep linear-light operations and respect `frame.headroom`. Tune the existing bloom from the same exposures before considering additional bloom scales.
- [ ] **Add optional adaptation.** Once the curve is accepted, meter a reduced-resolution scene luminance before bloom, and smooth an exposure value through a kept resource. Apply the exposure in a post pass that can bind the resource, then run the display mapping once in the tonemap stage. Define reset behavior for loads, dimension changes, teleports, and option changes. Keep manual exposure available.
- **Accept when** bright clouds and emissives retain shape and color, and a cave-to-daylight walk adapts without flashes or hunting. Compare locked and adaptive exposure with the same camera route. Check water glints, torch blooms, and sudden weather changes.

## Milestone 10 · Stabilize individual effects in motion

- [ ] **Use history to denoise one effect first.** Choose AO, cloud scattering, or SSR based on moving captures. Use a dedicated kept texture for that effect, camera reprojection for static geometry, and depth/normal or effect-specific history rejection. Reduce history weight at disocclusions, moving water, and animated foliage. Reset history on invalid frames and retain spatial AA for final image edges. The pinned client rejects the pack `[motion]` option and provides no subpixel projection jitter under pack-owned postprocessing.
- **Accept when** a fixed-speed pan shows less shimmer and turning past a tree or across a water edge leaves no visible trails. Test scene entry, a teleport, fast turns, and resize. Report the measured cost and motion cases it improves before reusing the approach in another effect.

## Milestone 11 · Add weather details after the lighting holds together

- [ ] **Calibrate rain and transitions.** Tie cloud coverage, direct sun, haze, and existing wetness to the same weather progression. Add Photon-style details one at a time, starting with a sun-relative rainbow when rain and directional sunlight coincide. Consider cloud-specific silhouettes, extra cloud layers, auroras, and camera effects individually once the primary weather transitions pass.
- **Accept when** clear-to-rain-to-clear behaves continuously, rough terrain retains texture in rain, and a rainbow responds to sun direction and weather. Check night, immersion, and non-Overworld fallbacks.

## Milestones that depend on Horizon client support

Check a newer client against these requirements when picking up one of these milestones. Keep the working pack path available while testing a client change.

| Milestone | Client requirement | First acceptance scene |
| --- | --- | --- |
| **12 · Propagated colored lighting** | A world-space input for occupancy, emission, and relevant transparency, plus a propagated RGB volume readable by terrain and entity stages. A raster-compatible compute pipeline can update the volume. For open-sky local-light scattering, expose the field to a sky or post stage that can integrate it along the view ray. | Two colored emitters behind a wall. Compare sealed wall, open door, and an emitter that has moved offscreen. Toggle bloom off to isolate lighting and scattering. Check chunk updates and boundary transitions. |
| **13 · TAA and temporal upscaling** | A compatible native resolve hook or pack-owned projection jitter and runtime motion vectors. Define jittered versus unjittered transforms, reset semantics, and how animated or translucent pixels are marked for history rejection. | A slow pan past tree leaves and thin diagonal geometry, followed by a moving mob and reflective water. Compare native resolution with upscaling only after the native-resolution temporal resolve is stable. |
| **14 · Higher-fidelity water mirrors** | A reflection pass that can include the desired sky, clouds, and entities. Support for multiple plane heights is a separate client requirement if one horizontal plane proves insufficient. | Two reflective pools at different elevations, with moving entities and layered clouds crossing both views. Verify reflection continuity and measure the extra scene-rendering cost. |

## Next implementation turn

Use the 0.4.2 ridge views for **Milestone 3**. Start with a single moving cloud layer and compare the sky, cloud shadows, and reflections on the same route.
