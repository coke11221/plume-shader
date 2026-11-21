# Horizon Lighting — Photon-inspired development roadmap

**Updated for v0.5.11 · WGSL shader pack · Horizon Shader API 0.2**

Bring Photon’s outdoor depth, soft lighting, and weather to Horizon Lighting in independently testable updates. Keep Horizon’s golden-hour palette, readable vanilla textures, and raster-only WGSL pipeline. The starting point is Horizon Lighting 0.3.9, Shader API 0.2, and the tested November 16 client 85b5bcca.

**Current checkpoint.** v0.5.10 completes the Milestone 3.6 implementation with moonlit side fill, material-colored glints, and foliage backlighting. v0.5.11 revisits direct sunlight color, celestial sprites, cloud shadows and the rain transition on the same client. Full occlusion of individual colored light sources remains part of Milestone 12.

Use the **cherry cliffs** as the target for sun/shade separation and the **rainbow valley** as the target for distance layering. The cliff shot uses custom settings. The Photon source explains the techniques; the **pinned Horizon API** determines which inputs the pack can actually use.

## Working rules and non-negotiables

- Take one milestone at a time. Before editing WGSL, use its implementation notes and acceptance checks to write the small plan for that milestone. Capture the current result, implement the feature in isolation, and compare it against the immediately preceding accepted build. Preserve the 0.3.9 captures as a long-term reference.
- Keep comparisons controlled. Record the world, camera position and orientation, time, weather, resolution, render distance, shadow settings, GPU/backend, and client revision. For animated effects, capture a short pan or transition as well as a still. Use an isolated profile or fixture world.
- Reuse the pack’s existing stages and settings where possible. Preserve color management, biome tints, alpha coverage, plain white torch light, dry grass and rain sheen, status effects, dimension fallbacks, and clear water. Treat each milestone’s proposed files and algorithm as starting points to verify on the current baseline.
- Run ./tools/check.ps1 from the project root for manifest, shader translation, and distribution checks. Check whether the optional GPU tests ran or skipped. For a release archive, run ./tools/check.ps1 -Package and load the resulting .hshader in the isolated client. Record the visual result and timing alongside the build identity.
- Compare GPU timings on the same hardware and camera route, starting with the RTX 4050 Laptop GPU on Vulkan. Record the whole-frame delta and individual effects when exposed, including shadow and planar mirror costs. Use the existing 4 ms shader authoring target as a budgeting reference. Set quality defaults from measurements and leave expensive tiers optional when appropriate.
- Account for the API limits when adding passes. The pinned reference allows 12 post entries, 16 named outputs, 64 options, and a shared target memory budget. There are seven raster post entries today. Prefer reduced-resolution targets or reuse existing stages before adding another full-resolution pass.


### Scope and current architecture

- **Shader language:** WGSL. OpenGL, Vulkan, and DirectX 12 in the game settings are renderer **backends**, not separate shader languages. Keep one portable WGSL implementation; verify actual behavior on each supported backend.
- **Implementation model:** raster-only shader-pack stages available through the pinned API. Avoid assuming native compute hooks, geometry access, ray tracing, motion vectors, or shader-pack pass bindings that the client has not exposed.
- **Baseline:** Horizon Lighting **0.3.9** for long-term screenshots and runtime comparisons. The v0.5 visual release uses **0.4.10** as its immediate comparison.
- **Established look:** warm golden hour, natural biome vegetation, legible vanilla textures, restrained bloom and wetness, and believable rather than exaggerated atmospheric effects.
- **Performance:** use **4 ms** as the existing shader-authoring budgeting reference, **not** an unverified guarantee. Profile effects and the whole frame. Leave expensive quality modes optional.
- **API resource pressure:** the pinned reference specifies **12 post entries**, **16 named outputs**, **64 options**, and a shared target-memory budget; the original roadmap records **seven raster post entries** currently. Recheck these limits against the actual pinned validator before adding passes.

### Definition of done — apply to **every** milestone

- [ ] Capture **matched before/after stills** using the same world seed, camera, time, weather, resolution, render distance, settings, backend, and client revision.
- [ ] Record **motion footage**: slow pan, rapid turn, camera translation, and chunk crossing when relevant. Watch for shimmer, ghosting, banding, clipping and temporal instability, **even before Milestone 10**.
- [ ] Check **interactions**, not just the isolated effect: sun vs cloud coverage; water vs fog; terrain vs entities; transparent materials vs reflections; day/night vs weather; underwater and dimension fallbacks.
- [ ] Run `./tools/check.ps1` and note whether GPU tests executed or were skipped. Package releases via `./tools/check.ps1 -Package` and load the `.hshader` in the isolated client.
- [ ] Measure GPU timing deltas and target memory for each relevant quality mode. Start with **RTX 4050 Laptop / Vulkan**; perform **OpenGL and DX12 compatibility passes** on available hardware before a public release. Record failures explicitly rather than assuming backend equivalence.
- [ ] Maintain a reproducible build/capture identity and document any artifacts, missing API inputs, or client-dependent follow-up work. Add a brief screenshot comparison and performance note to the milestone record.

### Recommended visual test matrix

| Scene | What it protects |
|---|---|
| Cherry cliffs, noon and low sun | Warm/cool lighting separation, vegetation color, contact shadows |
| Rainbow valley, near and far ridges | Atmospheric depth, sky/terrain color agreement, fog stability |
| Forest canopy and detached overhang | Thin foliage, sunbeams, contact shadows, shadow penumbrae |
| Lake, shore, shallow underwater and elevated pool | SSR/planar/env transitions, water absorption, caustics, fog ownership |
| Rainy hillside and exposed grass | Weather transitions, preserved texture, wetness and reflections |
| Cave with lava, torch and colored stained glass | Dark exposure, emission, transmission, occlusion and future RGB lighting |
| Clear night and overcast night | Moon/sky fill, stars, visibility and night contrast |
| Nether and End | Correct dimension fallbacks, deliberate color identity, no overworld leakage |

## Milestone 0 — Establish the comparison scenes

- [ ] Build a repeatable baseline. Start with a wooded valley viewed from a ridge and a low sun crossing a cliff face. Reuse existing lake, underwater, and Nether emitter fixtures where possible. Add a small test area with a wall and detached overhang, leaves, stained glass, and two differently colored light sources separated by a wall and doorway. Capture noon, sunset, overcast, night, and an underwater view as applicable.
- Accept when the capture setup records enough settings to repeat the view, the 0.3.9 archive loads with ray tracing disabled, and the baseline records frame timing over a fixed route. Use the existing 0.3.9 runtime record as a template.

## Milestone 1 — Give the sky and terrain a shared lighting model

- [x] Build a directional sky model. Start in common.wgsl, sky.wgsl, and lighting.wgsl. Use sun elevation and weather to define zenith color, horizon color, and the warm region around the sun. Use the same model for visible sky, direct-light color, and broad normal-dependent sky fill. Keep the vanilla skylight level as a visibility proxy for caves and roofs. Use the analytic model as the first approximation of Photon’s spherical-harmonic sky lighting, since material shaders cannot read computed kept resources on this baseline. Grade green Overworld vegetation toward natural biome colors.
- Accept when an open shaded face picks up sky color, a roofed room stays darker than outdoor shade, and a noon-to-sunset transition keeps grass green and sunlit stone readable. Review a neutral block on top, side, and under faces at noon, sunset, and night.

## Milestone 2 — Add height-dependent aerial perspective

- [x] Make terrain recede into the sky. Build on fog.wgsl and post/composite.wgsl. Use camera-relative ray height and distance to integrate a simple height-dependent density. Color the haze from the shared sky model, with a restrained forward-scattering component toward the sun. Reuse the current fog ownership where possible. Trace the material, opaque snapshot, water, and post paths so transmitted scenery receives fog once. Keep medium and status-effect routing intact.
- Accept when successive ridgelines pick up the horizon color while the near canopy holds its contrast. Compare the same view toward and away from the sun. Check shorelines, a clear submerged view, and a camera passing through fog without visible bands or abrupt transitions.

## Milestone 3 — Add clouds and connect them to sunlight

- [ ] Render a bounded cloud layer. Start with one world-anchored procedural layer and a low-cost sky-stage implementation. Add limited thickness or ray-marched lighting once the cloud silhouettes and motion read well. Share the coverage, world anchoring, wind, and weather inputs with an approximate sun-ray lookup in lighting.wgsl. Apply cloud attenuation to direct light first, then reuse it in post/atmosphere.wgsl when the approximation agrees with the cloud render. Keep a low-cost mode. The [sky] clouds switch is a manifest setting, so explicitly define what toggling the new effect does within the pack.
- Accept when clouds move continuously as the camera crosses chunks and their shading moves across terrain in the expected direction. Compare clear, broken cloud, and overcast scenes. Check composition with terrain silhouettes, reflections, and dimension-specific sky behavior. Add a second layer only if it improves the scene within the measured budget.
- **Integration requirement:** drive visible cloud coverage and terrain sunlight attenuation from compatible inputs (world position, wind, weather and sun direction). Avoid cloud shadows moving out of phase with their visible cloud layer. Keep the analytic sky fallback intact when clouds are disabled.
- **Motion gate:** slow panning and horizontal traversal must not cause cloud swimming, chunk seams or noisy silhouettes. Record an overcast-to-clear transition and inspect planar/water reflection mismatches.


## Milestone 3.5 — Add dedicated volumetric sunlight and atmospheric shafts **(new)**

**Why:** Milestone 2 adds aerial perspective and Milestone 3 approximates cloud attenuation, but visible shafts through mist and foliage deserve their own acceptance target. This is **not** the same thing as brightening fog or adding bloom.

- [x] Use the post stage's scene depth and shadow map for bounded volumetric ray integration.
- [x] Share sun direction, sky radiance, cloud attenuation, weather and the haze density profile with Milestones 1–3. Keep the terrain haze and underwater paths separate from the airborne shafts.
- [x] Compare half and quarter resolution. The half-resolution pass uses depth-aware reconstruction and the existing off switch and sample control.
- [x] Respect solid shadow casters and scene depth. Fade the air shafts at high sun and in heavy overcast.
- **Accept when** shafts from a low sun look coherent in the wooded valley and under canopy; turning the camera does not produce detached halos or screen-center artifacts; a camera moving indoors or underwater changes the effect correctly; clouds and shafts respond to the **same** sunlight state.
- **Fallback:** if the pack cannot access enough occlusion data, ship a restrained analytic sun-haze effect and register proper volumetric shadow integration as a **client-dependent enhancement**. Do not call an unoccluded glow "volumetric shafts."

## Milestone 3.6 — Natural Vibrancy and Artistic Grading (v0.5)

Give the Overworld a vibrant, natural palette, strong golden-hour lighting, and smooth cinematic highlight roll-off at fixed exposure.

- **Vegetation and materials.** Preserve the original texture and biome tint in `material.wgsl`. Let directional sunlight and diffuse skylight shape the color and brightness of exposed foliage.
- **Sunlight and time of day.** Use `common.wgsl` and `lighting.wgsl` for cleaner neutral daylight, soft apricot sunrise, rich golden sunset, and cool moonlit nights. Keep outdoor shade readable and let rain mute direct sunlight.
- **Dry surface response.** Use sprite-based material defaults for sunlight and moonlight highlights on ordinary block faces and shadow-aware transmission through foliage. Tune direct sun with RGB controls and moonlight with Night brightness. Use the rain coating for wet reflections.
- **Atmosphere.** Use the shared horizon palette for sky, cloud lighting and aerial perspective in `common.wgsl` and `fog.wgsl`. Keep pale cloud texture, clear foregrounds and layered distant ridges with the existing passes.
- **Color grading.** Shape midtone contrast and roll off highlights in `tonemap.wgsl` using linear light and display headroom. Preserve color ratios through the grade and keep fixed exposure. Temporal adaptation remains in Milestone 9.
- **Acceptance.** Compare matched 0.4.10 and v0.5 captures for noon, sunrise, sunset, rain, overcast and midnight. Check recognizable neutral and saturated materials, biome greens, water clarity and motion. Package the build, run the GPU checks, and record the matched Vulkan flight timing and available backend checks.

## Milestone 4 — Soften sun and moon shadow edges with distance

- [ ] Add a variable-width shadow filter. Extend shadow.wgsl with a bounded blocker search and a depth-dependent penumbra. Use the engine’s orthographic shadow depth, mapping, distortion, and texel scale. Preserve bias and out-of-range behavior. Keep a cheap filter tier and start with the advanced filter on surface receivers. Keep volumetric shadow lookups inexpensive and measure shafts with the new surface mode enabled. Photon shadow reference
- Accept when a post’s ground contact stays tight and a high overhang casts a wider edge. Inspect foliage, silhouettes, the shadow-map boundary, and a slow pan for acne, detached edges, or flicker. Compare the modes at the same map resolution and coverage.

## Milestone 5 — Add stained-glass transmission

- [ ] Apply colored sunlight in the shadowed region. Sample shadow_map, shadow_map_translucent, and shadow_color to distinguish opaque occlusion from translucent transmission. Feed RGB visibility into direct diffuse and specular lighting, with an explicit treatment for water and clear glass. Once surface transmission passes, try tinted shafts as a separate change using the same visibility rules. Horizon exposes the nearest translucent caster; use that as the scope of the first implementation.
- Accept when red and blue glass paint distinct patches, opaque blocks still fully occlude the transmitted light, and clear glass leaves the scene close to the untreated case. Test overlapping panes, water, map boundaries, and the shadows-off setting.

## Milestone 6 — Add contact ambient occlusion

- [ ] Prototype half-resolution GTAO. Reconstruct the depth neighborhood and use surface_at normals where solid terrain metadata exists. Start with scalar AO and edge-aware upsampling in post. Apply it selectively to the ambient contribution or use a bounded shaded-area approximation. Define how the pass identifies eligible receivers given the already lit scene color. The current set_surface payload carries packed reflection F0, so preserve its meaning if adding metadata. Evaluate bent normals only when they can improve directional fill through a supported composition path. Photon AO reference
- Accept when stair treads, cliff seams, and the bases of trees gain contact depth while sunlit faces keep their brightness. Check for dark halos around the skyline and for spill onto water, glass, entities, and sky. Verify glossy surfaces still receive the right reflection tint.
- **Do not accept a simple whole-image darkening pass as the final AO implementation.** With already-lit scene color, verify the available masking/metadata can approximate ambient-only modulation. If not, keep AO subtle or defer a more correct compositing path until the client exposes it.


## Milestone 7 — Improve foliage and material response

- [ ] Refine the thin foliage transmission added in Milestone 3.6. Use light direction, shadow visibility, and material tags to keep trunks and soil opaque. Evaluate vertex wind separately if the still comparisons show foliage is a meaningful gap. Use the shared deformation path so the visible foliage and its shadow stay aligned.
- [ ] Add optional LabPBR materials. After foliage is accepted, wire the API’s normal and specular maps into material shading and existing gloss. Start with normal direction, roughness, and emission. Respect the engine’s defaults when maps are absent, and retain the current sprite finishes for vanilla textures. Scope relief or parallax to a later experiment if it warrants the cost.
- Accept when backlit leaves gain a soft colored rim and covered foliage stays dark. Verify normal and roughness response on a known LabPBR material, then load vanilla textures and confirm dry and wet grass finishes, alpha edges, emissive blocks, polished metals, and HDR highlights still behave as expected.

## Milestone 7.5 — Audit lighting consistency across render categories **(new)**

- [ ] Compare **terrain, entities, dropped items, particles, held items, plants, water and stained glass** in the same noon/sunset/night shots. Identify which use the shared sun/sky terms and which still use vanilla/default lighting.
- [ ] Fix inconsistencies that are reachable through the current pack stages without adding unnecessary new passes or damaging alpha coverage, fog ownership or material ID semantics.
- [ ] Record **unexposed rendering categories** in a client backlog (rather than inventing pack-side fixes). Make sure a missing hook cannot silently delay unrelated shader milestones.
- **Accept when** the same scene has no obvious warm/cool lighting discontinuity between supported categories. Unsupported categories are explicitly tracked with reproduction screenshots and required native client inputs.

## Milestone 8 — Refine water and environment reflections

- [ ] Replace procedural ripple gradients with animated water normal maps. Pack tileable normal textures through `[[textures]]` and scroll two world-anchored layers at different speeds. Preserve ripple strength, pause support, distant filtering, and the existing refraction and reflection paths. Compare shallow pools, shorelines, and cave waterfalls before replacing the procedural path.
- [ ] Make reflection fallbacks agree with the sky. Reuse the sky model for the analytic environment fallback in water.wgsl and polished-surface shading. Improve transitions between screen-space hits, the horizontal planar mirror, and the environment using Fresnel, roughness, and hit confidence. The mirror contains terrain over the engine sky gradient. Keep that constraint explicit when evaluating cloud and sky continuity.
- [ ] Prototype underwater caustics. After the reflection transition is accepted, add a restrained pattern from the existing wave field to shallow, sunlit receivers. Gate it on water depth and sun visibility. Preserve the clear transmission path and existing underwater rays. Keep rain puddle tuning separate and limited to suitable surfaces.
- Accept when a grazing lake view and a pool at a different elevation both transition smoothly as the camera turns. Check out-of-screen hits, oblique shorelines, waterfalls, and cave pools. Caustics should move across a shallow lakebed and disappear under a solid roof.
- **Cloud/reflection boundary:** the existing horizontal planar mirror contains terrain over the engine sky gradient, not necessarily the custom cloud rendering. Use truthful sky fallbacks and smooth confidence blending; don't promise perfect cloud reflections until the client exposes the necessary mirror inputs (Milestone 14).


## Milestone 9 — Improve exposure, highlight roll-off, and bloom

- [ ] Tune the display curve with fixed exposure. Refine tonemap.wgsl with the noon sky, dark caves, sunset highlights, lava, and saturated lights in view. Compare SDR and available HDR captures. Keep linear-light operations and respect frame.headroom. Tune the existing bloom from the same exposures before considering additional bloom scales.
- [ ] Add optional adaptation. Once the curve is accepted, meter a reduced-resolution scene luminance before bloom, and smooth an exposure value through a kept resource. Apply the exposure in a post pass that can bind the resource, then run the display mapping once in the tonemap stage. Define reset behavior for loads, dimension changes, teleports, and option changes. Keep manual exposure available.
- Accept when bright clouds and emissives retain shape and color, and a cave-to-daylight walk adapts without flashes or hunting. Compare locked and adaptive exposure with the same camera route. Check water glints, torch blooms, and sudden weather changes.
- **Exposure safety:** keep manual/fixed exposure available, clamp adaptation rate to avoid pulsating indoor light, and do not meter after display tone mapping. Verify the luminance history is actually writable/readable through a supported kept resource before implementing persistence.


## Milestone 10 — Stabilize individual effects in motion

- [ ] Use history to denoise one effect first. Choose AO, cloud scattering, or SSR based on moving captures. Use a dedicated kept texture for that effect, camera reprojection for static geometry, and depth/normal or effect-specific history rejection. Reduce history weight at disocclusions, moving water, and animated foliage. Reset history on invalid frames and retain spatial AA for final image edges. The pinned client rejects the pack [motion] option and provides no subpixel projection jitter under pack-owned postprocessing.
- Accept when a fixed-speed pan shows less shimmer and turning past a tree or across a water edge leaves no visible trails. Test scene entry, a teleport, fast turns, and resize. Report the measured cost and motion cases it improves before reusing the approach in another effect.
- **Scope guard:** this milestone is effect-specific stabilization, **not full-frame TAA**. Without valid pack-owned projection jitter, motion vectors and supported resolve integration, use history selectively and fall back to spatial anti-aliasing on image edges. Keep the full temporal reconstruction design in Milestone 13.


## Milestone 11 — Add weather details after the lighting holds together

- [ ] Calibrate rain and transitions. Tie cloud coverage, direct sun, haze, and existing wetness to the same weather progression. Add Photon-style details one at a time, starting with a sun-relative rainbow when rain and directional sunlight coincide. Consider cloud-specific silhouettes, extra cloud layers, auroras, and camera effects individually once the primary weather transitions pass.
- Accept when clear-to-rain-to-clear behaves continuously, rough terrain retains texture in rain, and a rainbow responds to sun direction and weather. Check night, immersion, and non-Overworld fallbacks.

## Milestone 11.5 — Give night and each dimension a coherent atmosphere **(new)**

- [ ] **Overworld night:** calibrate moon/sky fill, star visibility, night haze, shadow color, water reflections and cave-to-moonlit outdoor readability using the shared sky model. Preserve gameplay visibility; avoid bright blue "daylight at midnight" and fully crushed outdoor shadows.
- [ ] **Weather at night:** confirm rain/overcast reduce moonlight and stars appropriately without causing exposure oscillations or abrupt changes.
- [ ] **Nether:** maintain a deliberately enclosed, emissive-driven palette, fog behavior and reflection fallback without leaking Overworld sun/moon/cloud logic.
- [ ] **End:** keep a deliberate sparse, eerie lighting response and safe dimension-specific atmosphere, without inheriting inappropriate Overworld daytime terms.
- **Accept when** the same vanilla materials remain readable through dawn/dusk, a clear night and overcast night; Nether and End retain stable distinct identities; teleports between dimensions do not flash or contaminate history/exposure.

## Client-dependent milestones (do not block the shader-only roadmap)

Check a newer client against these requirements when picking up one of these milestones. Keep the working pack path available while testing a client change.

|Milestone                             |Client requirement                                                                                                                                                                                                                                                                                                            |First acceptance scene                                                                                                                                                                                         |
|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**12 · Propagated colored lighting**  |A world-space input for occupancy, emission, and relevant transparency, plus a propagated RGB volume readable by terrain and entity stages. A raster-compatible compute pipeline can update the volume. For open-sky local-light scattering, expose the field to a sky or post stage that can integrate it along the view ray.|Two colored emitters behind a wall. Compare sealed wall, open door, and an emitter that has moved offscreen. Toggle bloom off to isolate lighting and scattering. Check chunk updates and boundary transitions.|
|**13 · TAA and temporal upscaling**   |A compatible native resolve hook or pack-owned projection jitter and runtime motion vectors. Define jittered versus unjittered transforms, reset semantics, and how animated or translucent pixels are marked for history rejection.                                                                                          |A slow pan past tree leaves and thin diagonal geometry, followed by a moving mob and reflective water. Compare native resolution with upscaling only after the native-resolution temporal resolve is stable.   |
|**14 · Higher-fidelity water mirrors**|A reflection pass that can include the desired sky, clouds, and entities. Support for multiple plane heights is a separate client requirement if one horizontal plane proves insufficient.                                                                                                                                    |Two reflective pools at different elevations, with moving entities and layered clouds crossing both views. Verify reflection continuity and measure the extra scene-rendering cost.                            |


### Additional native-client requests to track (not promised by WGSL alone)

- **Volume-aware direct-light integration:** if shadow-map/depth inputs are insufficient for convincing foliage shafts, expose an occlusion/shadow sampling path in post/volumetric stages or a native froxel/volume integration target. See Milestone 3.5.
- **Consistent object lighting:** expose aligned sun/sky/fog/material hooks for entities, particles, dropped items and first-person hands currently outside the pack's control. See Milestone 7.5.
- **Motion metadata for temporal effects:** provide jittered/unjittered transforms, per-pixel motion, reactive/transparent masks and history reset signals. See Milestone 13.
- **Reflection pass composition:** permit custom clouds/sky/entities and, if worth the cost, additional reflection plane heights. See Milestone 14.

### Quality presets — establish from measurements, not guesses

| Preset | Design intent | Typical tradeoff |
|---|---|---|
| Performance | Playable atmosphere on constrained hardware | Simpler cloud coverage, cheaper shadow filter, minimal AO, no costly ray marching |
| Balanced (default candidate) | Strong atmosphere without constant visual noise | Bounded clouds/shafts, selected SSR and AO, moderate shadows, stable fixed exposure |
| Ultra (optional) | Better penumbrae, clouds and reflections if profiling permits | Higher sample counts/resolution and potentially larger history allocations |

Treat these as **targets**, not a guarantee of a particular FPS or GPU requirement. Prefer one compact preset option plus a few high-value overrides to respect the **64-option** limit; never increase render targets casually when the pass/output/memory budgets are already tight.

### Prioritized execution order

1. **Prior checkpoint:** Milestone 3.5 adds sun and moon shafts across 0.4.8–0.4.10. See the [moonlight and gloss comparison](validation/0.4.10/REVIEW.md).
2. **Current build:** Milestone 3.6, Natural Vibrancy and Artistic Grading (v0.5). [Matched captures](validation/0.5.0/REVIEW.md)
3. **Core material depth:** Milestones 4–8, with 7.5 as a parity audit and motion/quality checks on every feature.
4. **Finish + polish:** Milestones 9–11.5, exposure/tone mapping, effect-specific stabilization, synchronized weather, night/dimension identity.
5. **Only when native support exists:** Milestones 12–14 and the tracked client requests above.

## Next implementation turn

Use v0.5.10 as the shader baseline for Milestone 4. Compare penumbrae on foliage and neutral block faces at noon and golden hour.

**Agent handoff instruction:** For each milestone, first inspect the relevant WGSL files, manifest, shader API reference and latest accepted captures. Propose a minimal change list and known limitations, implement **one** effect in isolation, validate it using the milestone's acceptance scene and the global definition of done, and report visual changes, GPU impact, compatibility regressions and any client-side feature request. Do not silently skip an acceptance condition, mark a milestone complete without evidence, or add features from a future milestone early.
