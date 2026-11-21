# Tuning the golden look

In-game settings expose only the **Quality preset** selector (**Lite**, **Balanced**, **High**, **Ultra**) so the pack's tuned lighting look stays consistent across every tier. Source edits below control the actual palette, locked strength defaults, and curves. All shader RGB constants are **linear light**, not display RGB or hex colours.

## Lighting and colour

| What to change | Source location | What it does |
| --- | --- | --- |
| Daylight color | `horizon_lighting/common.wgsl`, `NOON_SUN` | The near-neutral color of high sunlight. |
| Noon block fill | `lighting.wgsl`, `day_ambient` | Cool skylight keeps shaded faces readable. Direct sunlight follows the surface angle and cast shadows. |
| Close contact shading | **Lighting → Contact ambient occlusion** | Shades the lower blades of grass and ferns, with half-resolution shading on adjacent terrain and block junctions. The terrain effect fades out between 14 and 26 blocks. |
| Sunrise and sunset colors | `common.wgsl`, `SUNRISE_SUN` and `SUNSET_SUN` | Apricot morning and golden evening light for surfaces, clouds and haze. |
| How long golden hour lasts | `common.wgsl`, `golden_hour()` | The two `smoothstep` elevations set where the warm low-sun colour blends toward the noon colour. Elevations are the sun direction's Y, not clock ticks. |
| Strength of direct light | `lighting.wgsl`, `sunlight_strength` and `solar_radiance()` | Controls direct light relative to ambient fill, with a clear-weather boost at golden hour. |
| Shadow brightness/colour | `lighting.wgsl`, `DAY_AMBIENT`, `NIGHT_AMBIENT`, `sky_tint`, `facing_sky`, `shadow_contrast` | The sky dome tints the existing ambient palette by face direction. Higher contrast reduces daytime fill. |
| Warm bounced-light feel | `lighting.wgsl`, `indirect_warmth`, `warm_bounce` | Small sky-gated warm fill. This approximates indirect sunlight; it does not trace light between surfaces. |
| Night brightness | `lighting.wgsl`, `night_brightness` | Moonlight and ambient night fill. No orange sunlight is added at night. |
| Directional sky | `common.wgsl`, `overworld_sky_radiance()` and `golden_sky_glow()` | Clear, rainy, and night horizon and zenith palettes. The low-sun glow uses the same solar color as direct light. `sky.wgsl` mixes the model with the engine backdrop. |
| Highlights and exposure | `tonemap.wgsl`, `exposure`, `shoulder` | Fixed exposure, midtone contrast and hue-preserving Overworld highlights fitted to the display headroom. |

`golden_warmth` blends between neutral and golden sunlight. Set per-source colours in `[[lights]]` in `horizon_lighting/horizon-shaders.toml`. These RGB triplets use gamma-encoded values, which Horizon decodes before shading. Regular and wall torches use warm amber. Glowstone is amber, soul lights and sea lanterns are cyan, redstone torches are red, and amethyst and pearlescent froglights are lavender. The Atmosphere page's **Bloom** slider controls glow from bright emitters and highlights with their rendered colors.

**Lighting → Sunlight color** squares each Red, Green and Blue control before applying it in linear light. Outside sunset a channel at 0.5 passes 25% of that channel's solar contribution. Sunset preserves an amber base and sets minimum red and green contributions so the scene stays warm. The controls affect the solar glare, direct lighting and reflected sunlight. **Night brightness** scales moonlight. **Gloss and reflected light → Dry light response** controls glancing highlights and foliage backlighting from both lights. The default is 1.0. **Surface wetness** controls the rain coating.

Material-colored highlights on exposed solid block sides build between 5 and 10 blocks from the camera, peak from 10 to 18 blocks, and fade by 28 blocks. **Dry light response** also controls these highlights.

The torch material gives the flame a warm bright core and preserves the handle's texture color. The `glow` factor boosts the bright texels of emitters. `post/bloom_extract.wgsl` selects those texels before downsampling.

Terrain shading starts from the original texture and biome tint. Sunlight and skylight set the appearance of the foliage, and the rain coating darkens the pigment evenly across RGB.

## Volumetric light

**Atmosphere → Block light scattering** controls the visible glow around placed sources. The default is 0.65. Zero disables the airborne component while retaining custom material lighting. In `lighting.wgsl`, `block_surface_light()` uses the 3D light field to illuminate each material according to its texture color. `block_air_scatter()` integrates the bright core of the same field and fades the glow by 16 blocks from the camera. `apply_block_air_scatter()` retains the source hue and limits glow over dark materials. The engine's propagated block-light level provides approximate occlusion.

`field_radiance()` rolls off weak light-field samples to shorten the visible cast of block light on surfaces and in air. In the Nether and End, `shade_surface()` defines the ambient palette and `block_air_scatter()` reduces the volume strength. The engine block-light level at the receiver controls both effects. Low levels attenuate them strongly, and zero blocks both even when the camera is lit.

**Atmosphere → Clouds and cloud shadows** controls the shared sky layer and ground shade. **Volumetric clouds** switches between the thick layer and a cheaper plane. `cloud_column()` in `common.wgsl` shapes the separated clouds and the larger rain banks. `cloud_extinction()` controls how quickly light falls off through the layer. The clear-weather transmission floor keeps directional light on the ground. `solar_disk_and_glare()` in `sky.wgsl` sets the widths of the core and halo. The broad glare is part of the sky and **Bloom** adds a separate screen-space glow.

Edit `horizon_lighting/post/atmosphere.wgsl`:

- `volumetric_strength` sets airborne shaft brightness and defaults to 0.85. It has the most visible effect at low sun in clear weather. The underwater strength defaults to 0.70.
- `moon_shaft_strength` sets moonlit air shaft brightness and defaults to 1.20. Moon shafts use the night shadow map, fade with cloud cover, and require Shadows.
- `volumetric_samples`: integration quality; default 16 at half resolution. Lowering it saves samples and can reveal more noise/banding; it is not an intensity control.
- `density`: the amount of scattering per block, blended between midday and golden hour.
- `phase`: how strongly the glow concentrates toward the sun. Its constant term adds wider haze; its powered term adds a forward glow.
- `horizon_fade`: how close to the horizon shafts remain active. It fades them just above the horizon rather than extinguishing them early.
- `outdoors`: how much shaft strength remains when the camera is in a sheltered place.

These are shadow-map-sampled volumetrics. Shadows must be on. Weather, medium, dimension and status-effect guards remain active. `post/composite.wgsl` upsamples the result with depth rejection; edit intensity in the atmosphere pass rather than adding it twice in composition.

## Glossy surfaces and reflections

No extra textures are required. Default Minecraft colour textures supply the metal reflection colour. The pack classifies sprites in the manifest's `[[materials]]` rules:

| Material id | Finish | Tuning |
| --- | --- | --- |
| 0 (unmatched) | Rough when dry | Solar highlights are broader than on polished or wet blocks. Wet gloss is strongest on top faces. |
| 10 | Gold, iron, netherite, fresh copper | `surface_finish()` in `gloss.wgsl` gives each face 0.88 smoothness and 0.88 metalness. The top reflects nearby block light tinted by the metal's texture. |
| 20 | Polished stone, smooth stone, quartz, glazed terracotta, diamond/emerald blocks | 0.72 smoothness, dielectric F0 of 0.04. |
| 30 | Glass | 0.92 smoothness and direct sun highlights. |
| 40 | Ground-rooted grass, dry grass, ferns, flowers, bushes, saplings, crops, mushrooms, and 2-tall plant bottoms | Two-sided sunlight, backlighting, soft wet sheen, and root-anchored wind animation. |
| 41 | Grass blocks | Wet gloss on exposed faces, with gentler grading on green texels. Static geometry. |
| 42 | Leaves | Gentler grading on green texels, soft wet sheen, and 3D canopy wind rustling. |
| 43 | Upper halves of 2-tall plants (tall grass, large fern, tall flowers, dripleaf tops) | Same shading as 40 with seamless wind-weight continuity at the block boundary. |
| 44 | Vines, hanging moss, sugar cane, and bamboo | Same shading as 40 with continuous 3D wind waves across stacked blocks. |
| 45 / 46 | Seagrass, coral (45) and tall seagrass top, kelp (46) | Same shading as 40 with calm underwater current sway independent of surface rain. |
| 47 | Flat ground/wall foliage (glow lichen, leaf litter, lily pad, sea pickle) | Same shading as 40 with static geometry to avoid surface clipping. |

**Surface wetness** darkens exposed Overworld terrain and adds a sheen to exposed faces. The darkening builds early in rain on faces with enough skylight. Leaves and other foliage get a softer sheen. **Wet surfaces in clear weather** holds the coating at full weather strength. Wet highlights use **Surface gloss**, and wet scenery reflections also use **Reflected scenery**. Screen-space reflections need a visible object for a distinct reflected shape.

- `gloss.wgsl`, `gloss_strength` controls polished and wet highlights and scenery reflections. The default is 0.35. **Dry light response** controls highlights on uncoated rough blocks.
- `lighting.wgsl`, `surface_highlight()` uses a GGX lobe. The solar peak feeds bloom, with a 16% material tint and a minimum roughness for a finite highlight width.
- `post/reflections.wgsl`, `surface_reflections`: disable reflected scenery while keeping direct highlights.
- `reflection_steps`: quality/cost, default 16, range 8–24. `REFLECTION_REACH` is the maximum search distance in blocks, currently 24.
- `reflected_colour()`: roughness blur radius; polished stone gets a broader reflection than metal.
- `post/composite.wgsl`, `upsample_reflection()`: depth/normal/finish rejection, followed by each full-resolution pixel's Fresnel colour/strength.

Screen-space reflections see the current screen's visible surfaces. Edges fade, and in the Overworld misses use a subdued analytic sky fallback. In the Nether and End, misses contribute zero scenery radiance. Half-resolution sampling can soften small details.

## Clear water and waves

Edit `horizon_lighting/water.wgsl`:

- `WATER_ABSORPTION` and `AQUATIC_WATER_SCATTER`: per-channel depth absorption and sunlit aquatic blue volume tint.
- `water_clarity` controls depth absorption and aquatic volume tint; default is 1.6, while 4 disables added absorption.
- `water-normal.png` and `water_ripple_slope()`: three counter-scrolling directional wave layers at 0°, 90°, and 53.13° that fade with projected footprint.
- `water_speed` scales animation speed. Zero freezes the waves and cave water shimmer.
- `water_ripples`: the overall wave-normal strength; default 0.85.
- `WATER_AIR_IOR_RATIO` controls the bend used to compute refraction from the moving surface normal.
- `fresnel`: controls how much reflection replaces transmission at grazing angles.
- `glint`: the broad and small sun highlights on wave crests.

Sky-lit top faces read the opaque scene and combine refraction, aquatic depth absorption/scattering, reflections and highlights. Sheltered cave water blends the animated default water texture and subtle ripple shimmer on top, sloped, and falling faces so water sources and flows remain readable in dark caves. Side and bottom faces blend a translucent edge. Transparent objects behind the top face are limited by opaque-scene refraction.

Horizon supplies a single horizontal planar mirror for sufficiently flat Overworld water near the tracked elevation. Off-plane and screen-edge samples fall back to the analytical sky where skylight supports it. From underwater, the clear surface leaves the scene's engine fog and blended glass or ice intact.

## Foliage wind and dynamic lighting

- `horizon_lighting/vertex.wgsl`: **Atmosphere → Waving foliage** (`foliage_wind`) and **Wind strength** (`wind_strength`) control pure-arithmetic vertex wind animation with zero texture reads. Non-foliage vertices and foliage beyond 96 blocks return immediately. Clear weather uses a calm breeze (~1.8 rad/s) while rain/thunder smoothly crossfades into faster gusts (~4.2–6.5 rad/s) outdoors using dual constant-frequency phases (zero phase jump during rain transitions, seamless 3600s wrap). Caves stay sheltered via skylight (`input.light.y`), and shadows automatically match because Horizon shares `[vertex]` with the shadow pass.
- `horizon_lighting/common.wgsl` (`dynamic_surface_light`) & `horizon-shaders.toml` (`[[lights]]`): **Lighting → Dynamic lighting** (`dynamic_lights`) and **Dynamic light strength** (`dynamic_light_strength`) control lighting from held and dropped light items supplied by Horizon's client Dynamic Lights feature (`colored_light`). Items inherit the same per-source `[[lights]]` color table as placed blocks and illuminate terrain, entities, and water across the Overworld, Nether, and End.

## Fog ownership

`fog.wgsl` applies environmental terrain fog using the client's public fog colour/start/end values. The opaque background already includes fog when water samples it. The shader fogs water's new reflected color and attenuates water glints and solid-surface reflections by the visibility to the receiver. Mobs and block entities use the terrain's height haze in air. Underwater, `underwater_entity_colour()` compensates for the client's blue fog where it is thin enough to correct. The client still controls fully fogged entities.

**Atmosphere → Aerial perspective** controls Overworld haze on terrain, mobs, and block entities. The default is 0.5. The first 16 blocks stay clear, rain increases the haze, and the air gets thinner from y=64 to y=160. The shader takes the air color from the directional sky, with a soft warm contribution toward the low sun. Set this slider to zero to remove the height-dependent haze. **Experimental fog** has its own switch. Blindness and darkness fade the client fog back in. Other dimensions and immersed views keep their environmental fog. Underwater terrain and background use a faint neutral haze, and **Water clarity** controls transmission through the surface from above.

**Atmosphere → Experimental fog** is off by default. Enable it to use distance fog in Overworld air. **Fog start distance** sets the clear range in blocks, **Fog density** controls how quickly it thickens, and **Fog tint** offers Neutral, Warm and Cool. It applies once to visible geometry after reflections and bloom. Empty sky uses the sky shader.

**Water → Underwater sun rays** sets the intensity of the shadow-map-based volume. Zero skips underwater ray sampling. Shadows supply solid occlusion and locate the water interface. The effect strengthens along the refracted sun direction when the viewer sees the sunlit surface. The atmosphere pass shares the air shaft sample count. Underwater rays have their own strength and remain available when air shafts are disabled.

## Defaults and seeing edits

Every `override` with an in-game option has a matching default in `horizon_lighting/horizon-shaders.toml`. Change both together when changing the pack's defaults. A value already saved in the game's shader options may override the new default; use the in-game Reset control if necessary.

For a live development copy, place the `horizon_lighting/` source folder in a separate test game's `shaderpacks/` folder and select it. Horizon reloads saved changes. Avoid keeping multiple full packs with the same id in the active pack folder.

For the installed archive, validate/package from this project with `tools/check.ps1 -Package`, then install the resulting versioned archive. The update retains the same `horizon_lighting` id. Keep the prior archive outside the active pack folder if you want to switch back to the previous rendering.
