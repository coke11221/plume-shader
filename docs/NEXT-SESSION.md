# Horizon Lighting next-session handoff

Resume from **0.5.17** in `horizon_lighting/`, with the archive at `dist/horizon_lighting-0.5.17.hshader`. Use the raster-only Shader API 0.2 path on client `85b5bcca` or a compatible newer client. The optional `dist/horizon-round-moon.zip` supplies round lunar phases through Horizon's resource pack system. The next task is bloom from direct sun reflections on block faces.

## Where the roadmap stands

- **Milestone 1 is implemented.** `common.wgsl` defines `overworld_sky_radiance(direction)` for clear, rainy, and night sky colors. It includes the low-sun horizon glow based on `sun_colour()`. `sky.wgsl` blends this model with the engine’s backdrop and uses the engine backdrop for immersion and other dimensions. `lighting.wgsl` uses a luminance-normalized sample of the dome to tint ambient fill, with more sky contribution on upward faces. Minecraft’s skylight level still controls access around roofs and in caves.
- **Natural greens are the visual target.** `material.wgsl` uses original textures and biome tints. `lighting.wgsl` gives exposed leaves a softer directional response and more diffuse skylight toward the top of the crown.
- **0.4.3 extends the wet finish to all exposed solid terrain.** Grass blocks and vertical faces now reflect the environment when wet. Leaves and thin plants get a softer sheen. Sheltered faces with low skylight stay dry. **Wet surfaces in clear weather** holds the coating at full weather strength. [Wet terrain comparison](../validation/0.4.3/REVIEW.md)
- **Milestone 2 is implemented.** Terrain uses the shared sky model and integrates air density along the ray beyond the near field. The water snapshot already contains haze. Only new reflected radiance is fogged or attenuated at the receiver. The engine's planar water mirror lacks reflected-hit depth; its distant terrain can look more saturated than the direct view. Optional Experimental fog still applies as a final grade. [Paired validation](../validation/0.4.2/REVIEW.md)
- **0.4.4 lowers the default Aerial perspective strength from 1.0 to 0.5.** Mobs and block entities use the same atmospheric haze as the terrain. The engine still applies its environmental fog to entities. [Fog comparison](../validation/0.4.4/REVIEW.md)
- **Milestone 0 has reusable comparison scenes.** Directional sky, neutral stone, and roofed interior views are in `validation/0.4.0/`. Wet-surface, ridge, shoreline, and submerged matches are in `validation/0.4.2/`. Add the shadow and colored-emitter fixtures when those milestones come up.

See the [roadmap](superpowers/plans/2026-11-17-photon-inspired-roadmap.md), [milestone 1 plan](superpowers/plans/2026-11-17-directional-sky.md), [tuning notes](../TUNING.md), and [capture review](../validation/0.4.0/REVIEW.md).

## Clouds and sunlight

The cloud reference targets rounded, broken cumulus with irregular soft edges, gray undersides, and light on sun-facing edges. Compare the same GoldenLab sky angles and flight, especially the horizon and rain gaps. The sky, water reflections, and directional shadows share the field in `common.wgsl`. Tune `cloud_column()` for coverage and rain banks, `cloud_billows()` and `cloud_density()` for the volume, and `cloud_volume()` for scattering. Check measured cost before adding more samples. If more detail is needed, prototype filtered tileable noise in a packed texture and compare it with the procedural version. [Matched cloud captures](../validation/0.5.14/REVIEW.md)

0.5.11 draws the solar disc and glare behind the procedural sky layer. The cloud rendering and ground shadows integrate the same density field. The sun stays active in rain, with the cloud layer providing most of the attenuation. The block-light color field and its airborne glow now require propagated block light at the receiver. Individual source occlusion remains a client dependency.

0.4.6 adds cloud thickness, warm low-sun scattering, and reflections on water and glossy surfaces. **Volumetric clouds** switches to the cheaper cloud plane when disabled. **Clouds and cloud shadows** turns the whole effect off. See the [volume comparison](../validation/0.4.6/REVIEW.md) and the [original cloud-layer review](../validation/0.4.5/REVIEW.md).

0.4.7 aligns cloud rays with view bobbing and filters distant cloud detail to reduce banding. See the [walking comparison](../validation/0.4.7/REVIEW.md).

0.4.8 replaces the air-shaft integrator with height-dependent, shadowed scattering that follows the same cloud field as the terrain. It uses the existing Sun shafts controls and half-resolution target. See the [Milestone 3.5 review](../validation/0.4.8/REVIEW.md).

0.4.9 raises the default Sun shaft strength to 0.85 and applies the slider after compressing bright beams. See the [strength comparison](../validation/0.4.9/REVIEW.md).

0.4.10 adds direct moonlight and moon shafts, and softens gloss on top faces. See the [moonlight and gloss comparison](../validation/0.4.10/REVIEW.md).

## Animated water normals

Milestone 8 now uses a bundled tileable linear normal map. Two world-space layers travel at equal speeds in opposite directions and feed reflection, glint, and refraction. In 0.5.17 the ripples are smaller and shallower, with more varied crest directions. The layers share a footprint fade at grazing angles. Wave speed zero freezes both layers, and their phases join across the 3,600-second clock wrap.

## Next task · Bloom from sun reflections

1. Make every solid block face eligible for a direct solar highlight using its surface normal. In `material.wgsl`, the `top` checks currently limit the polished finish and full wet coating to upward faces. Trace the existing dry, polished, and wet responses before adjusting eligibility so their highlights combine without counting the same reflection twice.
2. Use `L` from the surface toward the sun, `V` from the surface toward the camera, and the surface normal `N`. The mirror peak occurs when `dot(reflect(-L, N), V)` approaches 1, equivalently when `N` aligns with `normalize(L + V)` for a visible, lit face. `dot(V, L) = 0` only measures their separation. Use the half-vector specular lobe already in `surface_highlight()` in `lighting.wgsl`. Keep material roughness, Fresnel, direct shadowing, skylight access, and cloud attenuation in the response. Faces with `dot(N, L) <= 0` receive zero direct solar reflection.
3. Feed the resulting HDR highlight into the existing `post/bloom_extract.wgsl` and blur passes. Tune the solar highlight energy and width before changing the global bloom threshold. Compare low-sun stone, polished and wet blocks across tops and all vertical orientations, with an underside and a shadowed face as controls. Run with bloom on and off to verify that bloom spreads around the aligned highlight and follows it as the camera moves.

## Local validation

The isolated fixture runs on Vulkan with an RTX 4050 Laptop GPU and ray tracing off. The [control script](../validation/0.4.2/capture-aerial.ctl) is reusable with a fresh copy of GoldenLab. See the [review](../validation/0.4.2/REVIEW.md) for the runner options and matched captures. The sandbox may require localhost approval for the offscreen control socket. If Horizon reports that agent control is disabled, the setting belongs to the user.
