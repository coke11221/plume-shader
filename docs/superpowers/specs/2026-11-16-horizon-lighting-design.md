# Horizon Lighting shader pack design

Date: 2026-11-16
Status: Approved by user; implemented. See execution ledger for verified implementation refinements and test scope.

## Intent and agreed constraints

Create a standalone lighting shader pack for the latest Horizon Rust Minecraft client. The project folder starts empty. The user wants sunlight, shadows, reflections, and volumetric light while keeping ordinary Minecraft textures. The user has an NVIDIA RTX 4050, explicitly excludes ray tracing, and wants a generally supported pack.

Compatibility means Horizon's native shader API 0.2 on supported raster backends, without hardware ray-query requirements. It does not mean compatibility with other Minecraft clients or the Iris/OptiFine pack format. API 0.2 is experimental; record the upstream revision used for implementation and validation in the README.

## Approaches

1. Post-processing alone: simplest and relatively inexpensive, but screen-space rays and reflections have visibility limits and cannot replace proper surface lighting and cast shadows. Rejected because it underserves the requested effects.
2. Raster lighting with Horizon shadow maps and its planar water reflection: covers the requested effects without ray queries. Add depth-aware volumetric sunlight in post-processing. Recommended in the preceding discussion; the user's preference for general support and exclusion of ray tracing selects this direction. Exact defaults below are builder proposals.
3. Hardware ray tracing: could support more general reflections and lighting, at additional cost and hardware restrictions. Excluded by the user.

## Visual goals

- Preserve recognizable vanilla textures and biome colours.
- Natural daylight with a modest warm tint near sunrise/sunset, cool restrained moonlight, and readable interiors.
- Terrain and entities receive consistent directional lighting and filtered cast shadows, without crushing vanilla block light or ambient occlusion.
- Water reflects surrounding terrain and sky with a view-dependent reflection weight and subtle procedural ripple normals.
- Sun shafts show where shadowed geometry interrupts light in a light atmospheric haze. Weather changes their strength.
- Subtle bloom and a controlled highlight roll-off; avoid a permanently orange picture, heavy blur, overbright nights, and thick fog everywhere.

No special texture maps or external image assets are required. Normal/specular resource packs are outside the initial scope. No hardware tracing, path tracing, screen-space global illumination, arbitrary mirrors, local-light shadow maps, or volumetric beams from every torch are promised.

## Pack structure and rendering

Deliver `horizon_lighting/` containing `horizon-shaders.toml` and WGSL files, plus repository-level README and a packaged `.hshader` after successful validation. Use a descriptive working name, Horizon Lighting, with id `horizon_lighting`.

Use only documented API 0.2 hooks. Declare no `[ray_tracing]` table, trace functions, custom bindings, or entry points. Colours are linear light. Prefer `[frame] blend = "linear"` after verifying the current checker and runtime agree on it; otherwise explicitly document the validated blend mode.

### Surface lighting

Provide `[material]` and `[entity]` stages. Stage-specific adapters call shared lighting functions that take plain vectors/scalars rather than terrain-only structs. Multiply existing texture/tint data carefully: Horizon's tint already includes directional shade and ambient occlusion, so do not apply another full vanilla directional shade. Preserve baked terrain tint rather than dividing by a shade guessed from camera-facing normals; GPU regression tests demonstrated excess underwater/diagonal brightness from that guess. Entity fallback paths retain the separate vanilla shade before overlays. Keep block-light contribution and emission distinct from the sun/moon term. Shadowing attenuates direct directional light, not all ambient and block light.

Request `[shadow]`; use `frame.light_direction` and the engine's shadow-coordinate helper. Filter depth comparisons with a bounded small PCF kernel. Bias scales with map texel size and surface angle. Treat samples outside the shadow square/depth interval as unshadowed and fade shadow influence near its boundary. Follow the engine's night/day and dimension data; keep Nether/End lighting readable without an Overworld sun model. Retain engine coverage/alpha handling and distance fog for both surface stages.

### Water

Identify water through `input.fluid` rather than altered textures. Read Horizon's reflection texture only when `frame.has_reflection` is valid and the camera/surface is compatible with the horizontal mirror plane. Use animated procedural normals, Fresnel weighting, a small bounded distortion, and a water colour fallback. Preserve coverage and alpha so water remains usable from above and below; reduce or disable the mirror underwater and on waterfall/side faces or surfaces whose height is incompatible with `frame.water_plane`.

Horizon's mirror is half resolution, uses a horizontal water plane, and contains solid terrain over the vanilla sky gradient. It is not a general reflection of entities, custom sky, or arbitrary surfaces. Document those limits. A reflection enable option must gate the engine pass through `[reflection] option`, so disabling it saves the mirror rendering work.

### Volumetric sunlight

Use a named half-resolution post target for atmospheric scattering. Reconstruct the view segment from scene depth with the documented camera-relative helper. At a bounded number of stratified positions along it, test the shadow map and accumulate distance-weighted scattering with a forward scattering phase function. This is raster shadow-map sampling, not hardware ray tracing. Clamp the integration reach to useful shadow coverage, fade outdoors/indoors with camera light, respond to rain/thunder, and suppress it in sunless dimensions or unsuitable underwater/lava views. Use an ambient haze rather than illuminated shafts where no reliable shadow data exists.

Upsample with depth-aware weighting at composition to reduce light bleeding across silhouettes. Ordinary post outputs force alpha to 1, so the atmospheric target stores additive scattering in RGB only. Keep the engine's existing distance fog for extinction, rather than applying a second full distance-fog replacement. Sky pixels use a finite integration distance. Add stable spatial jitter to reduce banding without temporal history or camera projection jitter.

### Bloom and final output

Generate a quarter-resolution bright-pass target and blur it with bounded separable filters. Composite the atmospheric target and bloom with the original scene in a full-resolution post pass; use a dedicated `[tonemap]` stage for exposure and highlight roll-off, respecting display headroom. All reads of named targets follow writes in manifest order. Each target must explicitly hold the signal later passes expect; do not rely on `previous` changing when a named output is written.

Plan for approximately six post passes: atmosphere, bloom extraction, horizontal blur, vertical blur, atmosphere/bloom composition, and optional lightweight final adjustment only if required. Prefer five if no separate final adjustment is needed. Stay within the current checker limits rather than relying on older documented limits. No temporal accumulation, kept resources, compute passes, or TAA in version one.

## Settings and proposed defaults

Expose a compact set of options on Lighting, Water, and Atmosphere pages. Every declared option must be used by WGSL or an engine option hook and pass checker validation.

| Setting | Balanced default | Lower-cost guidance | Higher-quality guidance |
| --- | --- | --- | --- |
| Shadow resolution | 2048 | 1024 | 4096 |
| Shadow coverage distance (engine half-side, blocks) | 96 | 64 | 128 |
| Shadow filter | Small bounded PCF kernel | Fewer taps | More taps within checker budget |
| Water reflections | On | Off | On |
| Volumetric samples | 12, half resolution | 6 or disabled | 20 |
| Bloom | Subtle, quarter resolution | Disabled/zero intensity | Adjustable intensity |
| Exposure | Neutral starting value | Same | Same |

These are starting settings, not measured performance promises. Include suggested Low/Balanced/High combinations in README; native preset selection is optional and only included if the current manifest supports it without extra machinery. Disabling shadows/reflections must gate their corresponding engine passes. Explain if setting post-effect strength to zero retains a small pass cost.

## Validation and delivery

1. Inspect upstream examples, current API reference, and checker implementation; record the source commit. Check stage/resource signatures against that revision.
2. Locate an existing `horizon-shader` tool or Rust toolchain. Initial command discovery found neither `horizon-shader`, `cargo`, nor `rustc` on PATH. If needed, stage a build of the authoring tool in a clearly separate tools/vendor directory without copying the entire Horizon client into the pack. Obtain dependencies only as needed and follow environment approval rules.
3. Run `horizon-shader check horizon_lighting` (including supported option boundary checks and backend translation). Resolve shader, manifest, derivative-uniformity, resource-use, and budget errors. Do not substitute text-only checks for the official checker or claim GPU rendering from checker success.
4. Package with `horizon-shader pack horizon_lighting` and inspect the resulting archive for a root manifest and all referenced WGSL files. Keep development tooling and documentation outside the pack archive.
5. Where a Horizon runtime is available, visually check daylight, sunset, moonlight, a torch-lit interior, a cave entrance, leaves, an entity, water from above/below, rain, Nether, and End. Pay attention to shadow acne, detached shadows, water transparency, silhouette halos, and near/far transitions. Test shadows/reflections disabled and the recommended quality combinations. Record only measured frame costs, using comparable scenes/settings.
6. If the client cannot be run here, deliver the checked pack with the limitation stated plainly and a short in-game checklist. Runtime visual quality and cross-GPU performance remain unverified until tested in Horizon.

README includes installation in Horizon's `shaderpacks/` directory, shader selection, live reload, supported API/revision, settings, known reflection limitations, and exact validation commands/results. A successful static build alone is not a claim of compatibility across all devices. No FPS target is asserted without measurements.

## Builder discretion

The implementer may settle filenames, exact sun/ambient curves, PCF offsets, ripple equations, atmospheric coefficients, bloom threshold, and stage ordering details within this design. Choose conservative natural defaults and tune with available render evidence. Changes that add ray tracing, require special texture packs, or replace the broad raster compatibility goal need user direction.

## Sources

- https://github.com/horizon-rust/horizon/blob/main/docs/shaders.md
- https://github.com/horizon-rust/horizon/blob/main/docs/api/shaders.md
- https://github.com/horizon-rust/horizon/blob/main/docs/api/shaders-reference-0.2.md
- https://github.com/horizon-rust/horizon/blob/main/crates/horizon-client-render/src/gfx/native_shadow.rs

Source documentation inspected 2026-11-16. Upstream `main` resolved to `85b5bcca7c79bb470b90bdb5914b413aa66fe7ae` during research. Use this revision for both implementation reference and checker, or record and recheck a newer revision together. No local git repository exists yet, so this design has not been committed.
