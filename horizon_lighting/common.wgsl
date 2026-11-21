// All palette values below are LINEAR RGB, not sRGB/hex display colours.
const golden_warmth: f32 = 1.0;

// The only player-facing option: 0 Lite, 1 Balanced, 2 High, 3 Ultra.
// Presets scale cost and fidelity only. The look (light strength, contrast, colour,
// gloss, haze, bloom and water character) is fixed and identical in every preset.
override quality_preset: u32 = 1u;
const PRESET_LITE: u32 = 0u;
const PRESET_BALANCED: u32 = 1u;
const PRESET_HIGH: u32 = 2u;
const PRESET_ULTRA: u32 = 3u;

override procedural_clouds: bool = true;
// Lite keeps the cheaper single cloud plane; Balanced and above march the volume.
override volumetric_clouds: bool = quality_preset >= PRESET_BALANCED;
override night_brightness: f32 = 0.10;
override volumetrics: bool = true;
// Airborne sun shafts: restrained and airy so foreground terrain and water stay crisp.
// Ultra raises reach, gain, and highlight headroom so sunward shafts stand out cleanly.
override volumetric_strength: f32 = select(1.30, 2.05, quality_preset >= PRESET_ULTRA);
override shaft_headroom: f32 = select(1.0, 2.8, quality_preset >= PRESET_ULTRA);
// Ultra integrates air light further along the view ray, inside reliable shadow-map
// coverage, so long beams reach across wide valleys and rivers.
override shaft_reach: f32 = select(select(68.0, 58.0, quality_preset == PRESET_LITE), 84.0,
    quality_preset >= PRESET_ULTRA);
override moon_shaft_strength: f32 = select(1.45, 1.85, quality_preset >= PRESET_ULTRA);

fn atmosphere_reach(underwater: bool) -> f32 {
    let coverage = select(select(0.72, 0.60, quality_preset == PRESET_LITE), 0.88,
        quality_preset >= PRESET_ULTRA);
    return select(
        min(frame.shadow_distance * coverage, shaft_reach),
        33.0,
        underwater,
    );
}
// Held and dropped dynamic lights share Horizon's MAX-propagated input.light.x with placed
// block lights and read their hue from input.colored_light (identical across all presets).
override dynamic_lights: bool = true;
override dynamic_light_strength: f32 = 1.0;
const NOON_SUN: vec3<f32> = vec3<f32>(1.0, 0.96, 0.86);
const AFTERNOON_SUN: vec3<f32> = vec3<f32>(1.0, 0.78, 0.44);
const SUNRISE_SUN: vec3<f32> = vec3<f32>(1.0, 0.60, 0.17);
const SUNSET_SUN: vec3<f32> = vec3<f32>(1.0, 0.44, 0.09);
const NEUTRAL_SUN: vec3<f32> = vec3<f32>(1.0, 0.98, 0.94);
const MOONLIGHT: vec3<f32> = vec3<f32>(0.80, 0.88, 1.0);
const UNDERWATER_VIEW_EXTINCTION: f32 = 0.032;
const AIR_LAYER_BASE: f32 = 64.0;
const AIR_LAYER_HEIGHT: f32 = 96.0;

fn air_density(normalized_height: f32) -> f32 {
    return mix(0.0045, 0.0085, frame.rain) * mix(1.0, 0.18, normalized_height);
}

fn air_sun_availability() -> f32 {
    let elevation = frame.sun_direction.y;
    let low_sun = smoothstep(0.005, 0.055, elevation) * (1.0 - smoothstep(0.35, 0.85, elevation));
    return low_sun * celestial_weather() * mix(1.0, select(0.08, 0.42, procedural_clouds), cloud_weather());
}

fn moonlight_presence() -> f32 {
    return (1.0 - smoothstep(-0.22, -0.04, frame.sun_direction.y))
        * smoothstep(0.01, 0.16, frame.moon_direction.y);
}

fn air_moon_availability() -> f32 {
    return moonlight_presence() * (4.2 * night_brightness) * clear_weather()
        * (1.0 - 0.88 * cloud_weather());
}

fn air_shaft_strength() -> f32 {
    if frame.sun_direction.y < 0.0 {
        return select(0.0, moon_shaft_strength, air_moon_availability() > 0.0);
    }
    return select(0.0, volumetric_strength, volumetrics && air_sun_availability() > 0.0);
}

fn celestial_direction() -> vec3<f32> {
    return select(frame.moon_direction, frame.sun_direction, frame.sun_direction.y >= 0.0);
}

fn moonlight_colour() -> vec3<f32> {
    return MOONLIGHT * (0.82 * night_brightness * moonlight_presence());
}

fn dynamic_light_hue(colour: vec3<f32>) -> vec3<f32> {
    let safe = max(colour, vec3<f32>(0.0));
    let peak = max(safe.r, max(safe.g, safe.b));
    if peak <= 0.0001 { return vec3<f32>(0.0); }
    var rgb = safe;
    // Horizon sums overlapping dynamic lights into colored_light and clamps each channel to 0..1.
    // Whenever warm emitters overlap, R clips at 1.0 first, then G, then B — drifting smoothly
    // through yellow-green toward white. Because no [[lights]] entry has R >= G >= B with G/R > 0.54
    // near full saturation (cyan, green, violet, and end-rod entries all have G > R or B > G),
    // one continuous blend restores warm torch amber across the entire R/G/B clip range with no bands.
    let r_clip = smoothstep(0.72, 0.96, rgb.r);
    if r_clip > 0.0 && rgb.r >= rgb.g * 0.95 && rgb.g >= rgb.b * 0.95 {
        let gr = rgb.g / max(rgb.r, 0.0001);
        let warm_clip = r_clip * smoothstep(0.54, 0.72, gr);
        let restored = vec3<f32>(rgb.r, min(rgb.g, rgb.r * 0.46), min(rgb.b, rgb.r * 0.085));
        rgb = mix(rgb, restored, warm_clip);
    }
    let out_peak = max(rgb.r, max(rgb.g, rgb.b));
    return rgb / max(out_peak, 0.0001);
}

fn uses_pack_lighting() -> bool {
    return frame.dimension == 0 || frame.dimension == -1 || frame.dimension == 1;
}

fn pack_underwater() -> bool {
    return frame.eye_in == 1u && (frame.dimension == 0 || frame.dimension == 1);
}

fn daylight() -> f32 {
    return smoothstep(-0.10, 0.14, frame.sun_direction.y);
}

fn twilight_daylight() -> f32 {
    return mix(0.20, 1.0, smoothstep(-0.035, 0.37, frame.sun_direction.y));
}

fn golden_hour() -> f32 {
    return 1.0 - smoothstep(0.32, 0.78, frame.sun_direction.y);
}

fn sun_presence() -> f32 {
    return smoothstep(-0.015, 0.045, frame.sun_direction.y);
}

fn clear_weather() -> f32 {
    return (1.0 - 0.65 * frame.rain) * (1.0 - 0.55 * frame.thunder);
}

fn celestial_weather() -> f32 {
    // With clouds enabled, most extinction comes from the local light path.
    return select(clear_weather(), mix(1.0, 0.74, cloud_weather()), procedural_clouds && frame.eye_in == 0u);
}

fn underwater_haze() -> vec3<f32> {
    var sky = 0.0;
    if frame.dimension == 0 {
        sky = smoothstep(0.12, 0.82, frame.eye_light_smooth.y) * daylight()
            * mix(0.65, 1.0, clear_weather());
    }
    return mix(vec3<f32>(0.002, 0.003, 0.003), vec3<f32>(0.074, 0.095, 0.105), sky);
}

fn high_sun() -> f32 {
    return smoothstep(0.42, 0.87, frame.sun_direction.y);
}

fn sunrise_weight() -> f32 {
    // Horizon's Overworld sun rises in the east (+X).
    return smoothstep(-0.6, 0.6, frame.sun_direction.x);
}

fn sunset_weight() -> f32 {
    return (1.0 - sunrise_weight()) * (1.0 - smoothstep(0.20, 0.52, frame.sun_direction.y));
}

fn sun_palette() -> vec3<f32> {
    // Keep warm golden sunlight active all day except the brief peak around high noon.
    let away_from_noon = 1.0 - smoothstep(0.86, 0.955, frame.sun_direction.y);
    let daylight_hue = mix(NOON_SUN, AFTERNOON_SUN, away_from_noon);
    let low_sun = mix(SUNSET_SUN, SUNRISE_SUN, sunrise_weight());
    let warmth = mix(golden_warmth, 1.0, sunset_weight());
    return mix(NEUTRAL_SUN, mix(daylight_hue, low_sun, golden_hour()), warmth);
}

fn sunlight_tint() -> vec3<f32> {
    // Keep signature sunlight tint non-editable across all times of day.
    return vec3<f32>(1.0);
}

fn sun_colour() -> vec3<f32> {
    return sun_palette() * sunlight_tint();
}

fn twilight_sun_colour() -> vec3<f32> {
    let pink = 0.82 * (1.0 - smoothstep(0.018, 0.048, frame.sun_direction.y));
    return mix(sun_palette(), vec3<f32>(1.0, 0.245, 0.54), pink * golden_warmth)
        * sunlight_tint();
}

fn safe_direction(p: vec3<f32>) -> vec3<f32> {
    return p / max(length(p), 0.0001);
}

// Replace negative and NaN channels with 0 (any comparison with NaN is false).
fn sanitize_rgb(c: vec3<f32>) -> vec3<f32> {
    return select(vec3<f32>(0.0), c, c > vec3<f32>(0.0));
}

fn golden_sky_glow(direction: vec3<f32>) -> vec3<f32> {
    let height = frame.sun_direction.y;
    let twilight = smoothstep(-0.22, -0.015, height) * (1.0 - smoothstep(0.24, 0.62, height));
    let horizon = exp(-abs(direction.y) * 2.1);
    let facing = max(dot(safe_direction(vec3<f32>(direction.x, 0.0, direction.z)),
                         safe_direction(vec3<f32>(frame.sun_direction.x, 0.0, frame.sun_direction.z))), 0.0);
    let solar_core = smoothstep(0.93, 0.998, dot(direction, frame.sun_direction));
    // Keep the warm peach horizon and let golden scattering wrap gently around low-sun skies.
    let upper_sunset = smoothstep(0.12, 0.56, direction.y) * smoothstep(-0.075, 0.04, height);
    let warmth = mix(0.75 * solar_core, 1.0, 0.45 * upper_sunset);
    let glow = mix(twilight_sun_colour(), sun_colour(), warmth);
    return glow * twilight * horizon * (0.14 + 0.78 * pow(facing, 2.0))
        * mix(0.42, 1.0, twilight_daylight())
        * golden_warmth * clear_weather();
}

fn overworld_sky_dome(direction: vec3<f32>, halo: f32) -> vec3<f32> {
    let elevation = smoothstep(0.0, 0.85, direction.y);
    let clear = mix(vec3<f32>(0.44, 0.57, 0.70), vec3<f32>(0.09, 0.29, 0.74), elevation);
    let overcast = mix(vec3<f32>(0.115, 0.118, 0.124), vec3<f32>(0.072, 0.075, 0.080), elevation);
    let night = mix(vec3<f32>(0.012, 0.018, 0.037), vec3<f32>(0.004, 0.007, 0.023), elevation);
    let storm = overcast_weight();
    let overcast_night = mix(vec3<f32>(0.011, 0.012, 0.014), vec3<f32>(0.004, 0.005, 0.006), elevation);
    let twilight = golden_hour() * golden_warmth * (1.0 - elevation);
    // Limit cool skylight in the solar halo so it does not bleach the warm scattering.
    let warm_air = mix(vec3<f32>(1.0, 0.88, 0.76), vec3<f32>(1.0, 0.78, 0.30), halo);
    let clear_day = clear * mix(vec3<f32>(1.0), warm_air, twilight);
    let day = mix(clear_day, overcast, storm);
    return mix(mix(night, overcast_night, storm), day * twilight_daylight(), daylight());
}

fn overworld_sky_radiance(direction: vec3<f32>) -> vec3<f32> {
    let glow = golden_sky_glow(direction);
    return overworld_sky_dome(direction, clamp(glow.r, 0.0, 1.0)) + glow;
}

const CLOUD_SEA_LEVEL: f32 = 64.0;
const CLOUD_PLANET_RADIUS: f32 = 28000.0;
// Three distinct vertical cloud layers matching realistic multi-deck skies:
// Layer 1: Low cumulus (y = 225..335)
// Layer 2: Mid altocumulus (y = 400..468)
// Layer 3: High cirrus / cirrocumulus sheet (y = 625)
const CLOUD_L1_BASE: f32 = 225.0;
const CLOUD_L1_THICKNESS: f32 = 110.0;
const CLOUD_L2_BASE: f32 = 400.0;
const CLOUD_L2_THICKNESS: f32 = 68.0;
const CLOUD_L3_HEIGHT: f32 = 625.0;
const CLOUD_HEIGHT: f32 = 280.0;
const STORM_DECK_HEIGHT: f32 = 510.0;
const CLOUD_PERIOD: f32 = 4096.0;
const CLOUD_REACH: f32 = 7600.0;
// Volumetric cloud raymarch steps by preset: Balanced 10/4, High 12/6, Ultra 16/8.
// Lite uses volumetric_clouds = false (single cloud plane).
override CLOUD_SKY_STEPS: u32 = select(select(16u, 12u, quality_preset == PRESET_HIGH), 10u,
    quality_preset <= PRESET_BALANCED);
override CLOUD_L2_STEPS: u32 = select(select(8u, 6u, quality_preset == PRESET_HIGH), 4u,
    quality_preset <= PRESET_BALANCED);

struct CloudPalette {
    sun_rgb: vec3<f32>,
    moon_rgb: vec3<f32>,
    ambient_belly: vec3<f32>,
    ambient_top: vec3<f32>,
    cirrus_sun: vec3<f32>,
    cirrus_ambient: vec3<f32>,
    direct_phase: f32,
    multi_phase: f32,
    phase_silver: f32,
    facing: f32,
    sunlight: f32,
    moonlight: f32,
    storm_lighting: f32,
    dusk: f32,
}

fn cloud_weather() -> f32 {
    return clamp(max(frame.rain, frame.thunder), 0.0, 1.0);
}

fn overcast_weight() -> f32 {
    return smoothstep(0.04, 0.95, cloud_weather());
}

fn cloud_coordinates(world_xz: vec2<f32>) -> vec2<f32> {
    // Two tiles per hour keeps cumulus drift gentle and continuous across Frame.time's wrap.
    let wind = vec2<f32>(2.0, -2.0) * fract(frame.time / 3600.0);
    return fract(world_xz / CLOUD_PERIOD + vec2<f32>(0.625, 0.575) - wind);
}

fn cloud_l2_coordinates(world_xz: vec2<f32>) -> vec2<f32> {
    // Independent mid-altitude drift vector wrapping seamlessly at 3600s.
    let wind = vec2<f32>(3.0, -1.0) * fract(frame.time / 3600.0);
    return fract(world_xz / CLOUD_PERIOD + vec2<f32>(0.61, 0.43) - wind);
}

fn cloud_l3_coordinates(world_xz: vec2<f32>) -> vec2<f32> {
    // Faster jet-stream drift for high-altitude cirrus at y = 625, wrapping cleanly at 3600s.
    let wind = vec2<f32>(4.0, -3.0) * fract(frame.time / 3600.0);
    return fract(world_xz / CLOUD_PERIOD + vec2<f32>(0.17, 0.73) - wind);
}

fn cloud_base_uv(u: vec2<f32>) -> vec2<f32> {
    // Integer rotation/scale matrices preserve exact wrapping at 3600s while removing grid alignment.
    return vec2<f32>(3.0 * u.x + u.y, -u.x + 3.0 * u.y);
}

fn cloud_detail_uv(u: vec2<f32>) -> vec2<f32> {
    return vec2<f32>(7.0 * u.x - 4.0 * u.y, 4.0 * u.x + 7.0 * u.y);
}

fn cloud_l2_base_uv(u: vec2<f32>) -> vec2<f32> {
    return vec2<f32>(5.0 * u.x - 2.0 * u.y, 2.0 * u.x + 5.0 * u.y);
}

fn cloud_l2_detail_uv(u: vec2<f32>) -> vec2<f32> {
    return vec2<f32>(11.0 * u.x + 5.0 * u.y, -5.0 * u.x + 11.0 * u.y);
}

fn cloud_macro_uv(u: vec2<f32>) -> vec2<f32> {
    // Slow cross-drift evolves weather fronts over time while wrapping seamlessly every hour.
    return u + vec2<f32>(0.0, 1.0) * fract(frame.time / 3600.0);
}

fn cloud_time_coverage() -> f32 {
    // Three smooth density cycles per hour (one per 20-minute Minecraft day), wrapping cleanly at 3600s.
    let phase = 18.849556 * fract(frame.time / 3600.0) + 0.65;
    return 0.5 + 0.5 * sin(phase);
}

fn cloud_macro_coverage(world_xz: vec2<f32>, weather: f32) -> f32 {
    let u = cloud_coordinates(world_xz);
    let macro_field = textureSampleLevel(cloud_noise, cloud_noise_sampler, cloud_macro_uv(u), 0.0).a;
    // Dynamic spatial & temporal cloud coverage instead of a fixed uniform field.
    let fair_base = mix(0.28, 0.54, cloud_time_coverage());
    let fair_cov = clamp(fair_base + (macro_field - 0.5) * 0.48, 0.14, 0.74);
    let storm_cov = clamp(0.88 + (macro_field - 0.5) * 0.12, 0.80, 0.96);
    return mix(fair_cov, storm_cov, smoothstep(0.06, 0.90, weather));
}

fn cloud_l2_macro_coverage(world_xz: vec2<f32>, weather: f32) -> f32 {
    let u = cloud_l2_coordinates(world_xz);
    let macro_field = textureSampleLevel(cloud_noise, cloud_noise_sampler, cloud_macro_uv(u), 0.0).a;
    let time_wave = 0.5 + 0.5 * sin(18.849556 * fract(frame.time / 3600.0) + 2.35);
    let fair_base = mix(0.20, 0.42, time_wave);
    let fair_cov = clamp(fair_base + (macro_field - 0.5) * 0.42, 0.10, 0.62);
    let storm_cov = clamp(0.84 + (macro_field - 0.5) * 0.14, 0.74, 0.94);
    return mix(fair_cov, storm_cov, smoothstep(0.10, 0.92, weather));
}

fn cloud_sphere_hit(h0: f32, ray_y: f32, target_h: f32) -> vec2<f32> {
    let r0 = CLOUD_PLANET_RADIUS + h0;
    let b = r0 * ray_y;
    let c = (h0 - target_h) * (2.0 * CLOUD_PLANET_RADIUS + h0 + target_h);
    let disc = b * b - c;
    if disc <= 0.0 { return vec2<f32>(-1.0, -1.0); }
    let root = sqrt(disc);
    return vec2<f32>(-b - root, -b + root);
}

fn cloud_curved_y(origin_y: f32, ray_y: f32, travel: f32) -> f32 {
    let h0 = origin_y - CLOUD_SEA_LEVEL;
    let r0 = CLOUD_PLANET_RADIUS + h0;
    let r = sqrt(max(r0 * r0 + 2.0 * r0 * ray_y * travel + travel * travel, 1.0));
    return CLOUD_SEA_LEVEL + (r - CLOUD_PLANET_RADIUS);
}

fn cloud_layer_interval(origin_y: f32, ray_y: f32, base_y: f32, thickness: f32) -> vec2<f32> {
    let h0 = origin_y - CLOUD_SEA_LEVEL;
    let h_base = base_y - CLOUD_SEA_LEVEL;
    let h_top = base_y + thickness - CLOUD_SEA_LEVEL;
    let base_hit = cloud_sphere_hit(h0, ray_y, h_base);
    let top_hit = cloud_sphere_hit(h0, ray_y, h_top);
    if h0 < h_base {
        if ray_y <= 0.002 || base_hit.y <= 0.0 { return vec2<f32>(0.0, 0.0); }
        let near = min(max(base_hit.y, 0.0), CLOUD_REACH);
        let far = min(max(top_hit.y, near), CLOUD_REACH);
        return vec2<f32>(near, far);
    }
    if h0 <= h_top {
        let exit_t = select(top_hit.y, base_hit.x, base_hit.x > 0.0 && base_hit.x < top_hit.y);
        return vec2<f32>(0.0, min(max(exit_t, 0.0), CLOUD_REACH));
    }
    if ray_y >= -0.002 || top_hit.x <= 0.0 { return vec2<f32>(0.0, 0.0); }
    let near = min(top_hit.x, CLOUD_REACH);
    let far_hit = select(top_hit.y, base_hit.x, base_hit.x > 0.0);
    return vec2<f32>(near, min(max(far_hit, near), CLOUD_REACH));
}

fn cloud_interval(origin_y: f32, ray_y: f32) -> vec2<f32> {
    return cloud_layer_interval(origin_y, ray_y, CLOUD_L1_BASE, CLOUD_L1_THICKNESS);
}

fn cloud_column_layer(u: vec2<f32>, coverage: f32, weather: f32, footprint: f32, is_l2: bool) -> vec4<f32> {
    let uv = select(cloud_base_uv(u), cloud_l2_base_uv(u), is_l2);
    let base_tex = textureSampleLevel(cloud_noise, cloud_noise_sampler, uv, 0.0);
    // Smooth low-frequency envelope band-limited to step footprint prevents any discrete slicing.
    let filter_w = smoothstep(18.0, 82.0, footprint);
    let base_shape = mix(base_tex.r, 0.50, filter_w * 0.62);
    let shaped = mix(base_shape, 0.50 + (base_shape - 0.50) * 0.45, weather);
    let edge_soft = mix(0.055, 0.19, filter_w) + 0.10 * weather;
    let threshold = 1.0 - coverage;
    let column = smoothstep(threshold - edge_soft, min(threshold + mix(0.32, 0.46, weather) + edge_soft, 1.0), shaped);
    return vec4<f32>(column, base_tex.g, base_tex.b, shaped);
}

fn cloud_column(world_xz: vec2<f32>, weather: f32, footprint: f32) -> f32 {
    let u = cloud_coordinates(world_xz);
    let coverage = cloud_macro_coverage(world_xz, weather);
    return cloud_column_layer(u, coverage, weather, footprint, false).x;
}

fn cloud_density_coherent(world_xz: vec2<f32>, height_y: f32, base_y: f32, thickness: f32,
                          coverage: f32, weather: f32, footprint: f32, travel: f32,
                          coherent_billow: f32, detail_weight: f32, is_l2: bool) -> f32 {
    let h = (height_y - base_y) / thickness;
    if h <= 0.0 || h >= 1.0 { return 0.0; }
    let u = select(cloud_coordinates(world_xz), cloud_l2_coordinates(world_xz), is_l2);
    let col_data = cloud_column_layer(u, coverage, weather, footprint, is_l2);
    let column = col_data.x;
    if column <= 0.001 { return 0.0; }

    // Smooth single-volume vertical envelope (no hard ledges that alias across oblique rays).
    let base_grad = smoothstep(0.0, mix(0.28, 0.34, weather), h);
    let macro_dome = mix(0.30, 0.96, pow(max(column, 0.0001), 0.58));
    let rough_top = 1.0 - smoothstep(macro_dome * 0.22, macro_dome, h);
    let rough_density = column * base_grad * rough_top;
    if rough_density <= 0.002 { return 0.0; }
    if detail_weight <= 0.01 { return rough_density; }

    let dist_detail = detail_weight * (1.0 - smoothstep(1800.0, 5600.0, travel));
    if dist_detail <= 0.01 { return rough_density; }

    // Coherent cauliflower billow detail anchored smoothly to the ray's cloud intersection:
    // carves crisp, fluffy, non-blocky tufts without ever introducing horizontal stacked slices.
    let sculpted_top_h = clamp(macro_dome * mix(0.76, 1.08, coherent_billow), 0.20, 0.99);
    let sculpted_top = 1.0 - smoothstep(sculpted_top_h * 0.20, sculpted_top_h, h);
    let sculpted = column * base_grad * mix(rough_top, sculpted_top, dist_detail * (1.0 - 0.65 * weather));

    let erode_strength = mix(0.56, 0.16, weather) * dist_detail * (1.0 - sculpted * 0.50);
    let eroder = (1.0 - coherent_billow) * erode_strength;
    let eroded = clamp((sculpted - eroder) / max(1.0 - eroder * 0.80, 0.22), 0.0, 1.0);
    return mix(eroded, smoothstep(0.02, 0.68, eroded) * eroded, (1.0 - weather) * 0.22);
}

fn cloud_density(point: vec3<f32>, weather: f32, footprint: f32) -> f32 {
    let coverage = cloud_macro_coverage(point.xz, weather);
    let u = cloud_coordinates(point.xz);
    let d_tex = textureSampleLevel(cloud_noise, cloud_noise_sampler, cloud_detail_uv(u), 0.0);
    let billow = mix(d_tex.g, d_tex.b, 0.36);
    return cloud_density_coherent(point.xz, point.y, CLOUD_L1_BASE, CLOUD_L1_THICKNESS,
        coverage, weather, footprint, 0.0, billow, 1.0, false);
}

fn cloud_distance_fade(travel: f32) -> f32 {
    return 1.0 - smoothstep(4200.0, CLOUD_REACH, travel);
}

fn cloud_horizon_weight(entry: f32) -> f32 {
    return 1.0 - smoothstep(3800.0, CLOUD_REACH, entry);
}

fn cloud_layer_view_weight(origin_y: f32, ray_y: f32, entry: f32, base_y: f32, thickness: f32, weather: f32) -> f32 {
    let outside = max(base_y - origin_y, origin_y - (base_y + thickness));
    let angle_fade = mix(1.0, smoothstep(0.010, 0.058, abs(ray_y)), smoothstep(0.0, 42.0, outside));
    let fair = cloud_horizon_weight(entry) * angle_fade;
    let storm = (1.0 - smoothstep(2400.0, 6800.0, entry)) * angle_fade;
    return mix(fair, storm, smoothstep(0.30, 0.90, weather));
}

fn cloud_view_weight(origin_y: f32, ray_y: f32, entry: f32, weather: f32) -> f32 {
    return cloud_layer_view_weight(origin_y, ray_y, entry, CLOUD_L1_BASE, CLOUD_L1_THICKNESS, weather);
}

fn storm_deck_opacity(origin: vec3<f32>, ray: vec3<f32>, weather: f32) -> f32 {
    let strength = smoothstep(0.08, 1.0, weather);
    if strength <= 0.0 { return 0.0; }
    let h0 = origin.y - CLOUD_SEA_LEVEL;
    let h_deck = STORM_DECK_HEIGHT - CLOUD_SEA_LEVEL;
    let ahead = select(h0 - h_deck, h_deck - h0, ray.y >= 0.0);
    let crossing = smoothstep(-28.0, 28.0, ahead) * smoothstep(0.010, 0.080, abs(ray.y));
    if crossing <= 0.0 { return 0.0; }
    let hit = cloud_sphere_hit(h0, ray.y, h_deck);
    let travel = min(max(select(hit.x, hit.y, h0 < h_deck), 0.0), CLOUD_REACH);
    if travel <= 0.0 { return 0.0; }
    let u = cloud_coordinates(origin.xz + ray.xz * travel);
    let layer = textureSampleLevel(cloud_noise, cloud_noise_sampler, cloud_macro_uv(u) * 2.0, 0.0).r;
    let thickness = mix(0.46, layer, cloud_horizon_weight(travel));
    return strength * crossing * mix(0.26, 0.70, smoothstep(0.18, 0.82, thickness));
}

fn blend_storm_deck(base: vec3<f32>, ray: vec3<f32>, opacity: f32) -> vec3<f32> {
    let thickness = smoothstep(0.18, 0.70, opacity);
    let sun_y = frame.sun_direction.y;
    let dusk = smoothstep(-0.16, -0.02, sun_y) * (1.0 - smoothstep(0.05, 0.22, sun_y));
    let day_sheet = mix(vec3<f32>(0.245, 0.252, 0.265), vec3<f32>(0.115, 0.120, 0.130), thickness);
    let dusk_sheet = mix(vec3<f32>(0.22, 0.14, 0.26), vec3<f32>(0.095, 0.068, 0.125), thickness);
    let sheet_day = mix(day_sheet, dusk_sheet, 0.50 * dusk);
    let sheet_night = vec3<f32>(0.009, 0.011, 0.015);
    let facing = max(dot(ray, frame.sun_direction), 0.0);
    let sun_luma = dot(sun_colour(), vec3<f32>(0.2126, 0.7152, 0.0722));
    let overcast_sun = mix(vec3<f32>(sun_luma), sun_colour(), 0.22) * vec3<f32>(1.0, 0.99, 0.97);
    let glow = overcast_sun * (0.24 * pow(facing, 8.0) + 0.48 * pow(facing, 36.0))
        * (1.0 - 0.55 * thickness) * sun_presence();
    let sheet = mix(sheet_night, sheet_day * twilight_daylight(), daylight()) + glow;
    return mix(base, sheet, opacity);
}

fn cloud_extinction(weather: f32) -> f32 {
    return mix(0.042, 0.028, weather);
}

fn cloud_transmittance(depth: f32, weather: f32) -> f32 {
    let solid = exp(-depth);
    let diffuse = 1.0 / (1.0 + depth * (1.0 + 0.24 * depth));
    return mix(solid, diffuse, 0.65 * smoothstep(0.28, 0.92, weather));
}

fn cloud_plane_opacity(world_origin: vec3<f32>, direction: vec3<f32>, weather: f32) -> f32 {
    let interval = cloud_interval(world_origin.y, direction.y);
    if interval.y <= interval.x { return 0.0; }
    let travel = 0.5 * (interval.x + interval.y);
    let col = cloud_column(world_origin.xz + direction.xz * travel, weather, 0.0);
    let opacity = 1.0 - exp(-col * mix(1.85, 3.10, weather));
    return opacity * cloud_horizon_weight(travel) * smoothstep(0.008, 0.06, abs(direction.y));
}

fn hg_phase(cos_theta: f32, g: f32) -> f32 {
    // Normalized so isotropic scattering averages 1.0 across the sphere.
    let g2 = g * g;
    let denom = max(1.0 + g2 - 2.0 * g * cos_theta, 0.004);
    return (1.0 - g2) / (denom * sqrt(denom));
}

fn cloud_twilight_weight() -> f32 {
    let sun_y = frame.sun_direction.y;
    return smoothstep(-0.16, -0.02, sun_y) * (1.0 - smoothstep(0.06, 0.22, sun_y));
}

fn cloud_deep_dusk_weight() -> f32 {
    let sun_y = frame.sun_direction.y;
    return smoothstep(-0.18, -0.05, sun_y) * (1.0 - smoothstep(0.0, 0.085, sun_y));
}

fn cloud_sun_tint(facing: f32) -> vec3<f32> {
    let dusk = cloud_twilight_weight();
    let deep = cloud_deep_dusk_weight();
    let rose = smoothstep(0.24, 0.86, facing) * (1.0 - 0.58 * smoothstep(0.95, 1.0, facing));
    let warm_to_rose = mix(sun_colour(), twilight_sun_colour(), clamp(rose + 0.55 * deep, 0.0, 1.0));
    let magenta_violet = vec3<f32>(0.94, 0.26, 0.76);
    return mix(warm_to_rose, magenta_violet, 0.62 * deep * (0.35 + 0.65 * (1.0 - smoothstep(0.92, 1.0, facing))))
        * mix(vec3<f32>(1.0), vec3<f32>(1.04, 0.94, 1.06), 0.35 * dusk);
}

fn cloud_fill_tint(facing: f32, weather: f32) -> vec3<f32> {
    let warm_day = 1.0 - smoothstep(0.86, 0.955, frame.sun_direction.y);
    let dusk = cloud_twilight_weight();
    let warmth = max(golden_hour(), 0.35 * warm_day) * golden_warmth * sun_presence() * (1.0 - weather)
        * (0.16 + 0.84 * facing * facing) * (1.0 - 0.55 * dusk);
    let warm_tint = mix(vec3<f32>(1.0), vec3<f32>(1.08, 0.82, 0.52), warmth);
    let violet_tint = mix(vec3<f32>(1.0), vec3<f32>(1.10, 0.72, 1.24), dusk * (1.0 - 0.65 * weather));
    return warm_tint * violet_tint;
}

fn build_cloud_palette(direction: vec3<f32>, weather: f32) -> CloudPalette {
    let day = daylight();
    let low_sun = golden_hour();
    let dusk = cloud_twilight_weight();
    let deep_dusk = cloud_deep_dusk_weight();
    let sun_y = frame.sun_direction.y;
    let sunlight = smoothstep(-0.14, 0.055, sun_y) * mix(0.48, 1.0, twilight_daylight());
    let moonlight = moonlight_presence() * (0.45 + 0.55 * night_brightness) * (1.0 - 0.75 * weather);
    let cos_sun = dot(direction, frame.sun_direction);
    let facing = max(cos_sun, 0.0);

    let phase_silver = min(hg_phase(cos_sun, mix(0.74, 0.58, weather)), 5.4);
    let phase_forward = hg_phase(cos_sun, 0.30);
    let phase_back = hg_phase(cos_sun, -0.22);
    let direct_phase = mix(0.66 * phase_forward + 0.34 * phase_silver,
        0.55 * phase_silver + 0.45 * phase_forward, weather);
    let multi_phase = 0.62 * phase_forward + 0.38 * phase_back;

    // Direct sunlight: crisp white midday, creamy warm peach-gold sunset, rose-magenta dusk.
    let midday_white = vec3<f32>(1.0, 0.992, 0.980);
    let sunset_cream = mix(vec3<f32>(1.0, 0.86, 0.68), cloud_sun_tint(facing), 0.76);
    let fair_sun_rgb = mix(midday_white, sunset_cream, clamp(0.14 + 0.86 * low_sun, 0.0, 1.0));
    let sun_luma = dot(fair_sun_rgb, vec3<f32>(0.2126, 0.7152, 0.0722));
    let overcast_sun_rgb = mix(vec3<f32>(sun_luma) * vec3<f32>(0.98, 0.99, 1.02), fair_sun_rgb, 0.16);
    let sun_rgb = mix(fair_sun_rgb, overcast_sun_rgb, weather) * sunlight * mix(0.88, 0.42, weather);
    let moon_rgb = MOONLIGHT * (0.18 * moonlight) * (0.35 + 0.65 * max(dot(direction, frame.moon_direction), 0.0));

    // Ambient sky-bounce palette: airy cool sky-blue midday, dusty mauve sunset, purple/violet dusk.
    let midday_belly = vec3<f32>(0.165, 0.230, 0.345);
    let midday_top = vec3<f32>(0.44, 0.58, 0.78);
    let sunset_belly = vec3<f32>(0.21, 0.15, 0.29);
    let sunset_top = vec3<f32>(0.48, 0.33, 0.48);
    let dusk_belly = vec3<f32>(0.14, 0.058, 0.31);
    let dusk_top = vec3<f32>(0.38, 0.13, 0.47);

    var fair_belly = mix(midday_belly, sunset_belly, 0.78 * low_sun * golden_warmth);
    var fair_top = mix(midday_top, sunset_top, 0.68 * low_sun * golden_warmth);
    fair_belly = mix(fair_belly, dusk_belly, clamp(0.58 * dusk + 0.42 * deep_dusk, 0.0, 1.0));
    fair_top = mix(fair_top, dusk_top, clamp(0.64 * dusk + 0.36 * deep_dusk, 0.0, 1.0));

    let sunward_bounce = cloud_sun_tint(facing) * (0.14 + 0.28 * dusk) * low_sun * pow(facing, 1.8) * (1.0 - weather);
    fair_belly += sunward_bounce;

    let storm_haze = exp(-4.5 * abs(direction.y));
    let storm_belly = mix(vec3<f32>(0.175, 0.182, 0.195), vec3<f32>(0.235, 0.242, 0.255), storm_haze);
    let storm_top = mix(vec3<f32>(0.275, 0.285, 0.300), vec3<f32>(0.300, 0.310, 0.325), storm_haze);
    let storm_dusk = mix(vec3<f32>(1.0), vec3<f32>(1.00, 0.74, 1.12), 0.50 * dusk);

    let day_belly = mix(fair_belly, storm_belly * storm_dusk, weather) * twilight_daylight();
    let day_top = mix(fair_top, storm_top * storm_dusk, weather) * twilight_daylight();
    let night_belly = vec3<f32>(0.012, 0.017, 0.032) + vec3<f32>(0.018, 0.009, 0.038) * deep_dusk;
    let night_top = vec3<f32>(0.024, 0.034, 0.060) + vec3<f32>(0.044, 0.018, 0.066) * deep_dusk;

    // High-altitude y=625 cirrus stays sunlit deeper into twilight with vivid gold -> magenta -> violet hues.
    let cirrus_sunlight = smoothstep(-0.18, 0.03, sun_y) * mix(0.55, 1.0, twilight_daylight());
    let cirrus_tint = mix(midday_white, mix(sunset_cream, vec3<f32>(1.0, 0.32, 0.68), 0.72 * deep_dusk),
        clamp(0.18 + 0.82 * low_sun + 0.50 * dusk, 0.0, 1.0));
    let cirrus_sun = cirrus_tint * cirrus_sunlight * (0.72 + 0.55 * direct_phase);
    let cirrus_ambient = mix(night_top, mix(midday_top * 0.65, dusk_top * 0.85, dusk) * twilight_daylight(), day);

    return CloudPalette(
        sun_rgb,
        moon_rgb,
        mix(night_belly, day_belly, day),
        mix(night_top, day_top, day),
        cirrus_sun,
        cirrus_ambient,
        direct_phase,
        multi_phase,
        phase_silver,
        facing,
        sunlight,
        moonlight,
        smoothstep(0.55, 0.96, weather),
        dusk,
    );
}

fn cloud_march_layer(world_origin: vec3<f32>, direction: vec3<f32>, weather: f32,
                     base_y: f32, thickness: f32, steps: u32, full_detail: bool,
                     is_l2: bool, pal: CloudPalette) -> vec4<f32> {
    let interval = cloud_layer_interval(world_origin.y, direction.y, base_y, thickness);
    let near = interval.x;
    let far = interval.y;
    let horizon = cloud_layer_view_weight(world_origin.y, direction.y, near, base_y, thickness, weather);
    if far <= near || horizon <= 0.0 { return vec4<f32>(0.0); }

    let mid_travel = 0.5 * (near + far);
    let mid_xz = world_origin.xz + direction.xz * mid_travel;
    let coverage = select(cloud_macro_coverage(mid_xz, weather), cloud_l2_macro_coverage(mid_xz, weather), is_l2);

    // Sample crisp cauliflower detail & directional bump ONCE per ray at the continuous mid-shell:
    // gives sharp, tactile, 3D-lit puffs with ZERO horizontal raymarch slicing and ~2x fewer texture reads.
    var coherent_billow = 0.65;
    var puff_bump = 0.0;
    let detail_weight = select(0.0, 1.0, full_detail);
    if full_detail {
        let u_mid = select(cloud_coordinates(mid_xz), cloud_l2_coordinates(mid_xz), is_l2);
        let d_uv = select(cloud_detail_uv(u_mid), cloud_l2_detail_uv(u_mid), is_l2);
        let d_tex = textureSampleLevel(cloud_noise, cloud_noise_sampler, d_uv, 0.0);
        coherent_billow = mix(d_tex.g, d_tex.b, 0.36);
        let sun_shift = frame.sun_direction.xz * select(0.016, 0.014, is_l2);
        let d_sun = textureSampleLevel(cloud_noise, cloud_noise_sampler, d_uv + sun_shift, 0.0);
        let sun_billow = mix(d_sun.g, d_sun.b, 0.36);
        puff_bump = clamp(sun_billow - coherent_billow, -0.45, 0.45) * (1.0 - 0.72 * weather);
    }

    let step_length = (far - near) / f32(steps);
    let footprint = step_length * length(direction.xz);
    let extinction = cloud_extinction(weather) * select(1.0, 0.62, is_l2);
    let scatter_sun = pal.sunlight > 0.001;
    let sun_y = frame.sun_direction.y;
    let probe_dir = safe_direction(vec3<f32>(frame.sun_direction.x, max(sun_y, 0.09), frame.sun_direction.z));
    let probe_a = probe_dir * select(mix(36.0, 60.0, weather), mix(26.0, 44.0, weather), is_l2);
    let light_ext = select(mix(3.15, 1.45, weather), mix(2.25, 1.20, weather), is_l2);

    var transmission = 1.0;
    var depth = 0.0;
    var accum_light = vec3<f32>(0.0);

    for (var i = 0u; i < steps; i++) {
        let travel = near + (f32(i) + 0.5) * step_length;
        let sample_xz = world_origin.xz + direction.xz * travel;
        let sample_y = cloud_curved_y(world_origin.y, direction.y, travel);
        let density = cloud_density_coherent(sample_xz, sample_y, base_y, thickness,
            coverage, weather, footprint, travel, coherent_billow, detail_weight, is_l2);
        if density > 0.001 {
            let fade = cloud_distance_fade(travel);
            let optical_depth = density * step_length * extinction * fade;
            let step_trans = exp(-optical_depth);
            let absorbed = 1.0 - step_trans;
            let h = clamp((sample_y - base_y) / thickness, 0.0, 1.0);

            // Height-graded ambient: cool/violet shaded undersides, luminous sky-lit upper domes.
            let height_ao = mix(select(0.48, 0.62, is_l2), 1.0, smoothstep(0.0, 0.80, h));
            let inner_ao = mix(1.0, 0.72, density * (1.0 - h));
            var step_radiance = mix(pal.ambient_belly, pal.ambient_top, smoothstep(0.06, 0.86, h)) * height_ao * inner_ao;

            if scatter_sun {
                // Smooth 3D volumetric sun probe + coherent cauliflower bump relief (zero slices).
                let s1 = cloud_density_coherent(sample_xz + probe_a.xz, sample_y + probe_a.y,
                    base_y, thickness, coverage, weather, footprint * 1.6, travel,
                    coherent_billow, 0.0, is_l2);
                let light_tau = max(density * mix(0.85, 0.28, weather) + s1 * light_ext + puff_bump * 1.85, 0.0);
                let powder = 1.0 - 0.42 * exp(-density * 3.8) * (1.0 - 0.82 * pal.facing) * (1.0 - pal.storm_lighting);
                let ms0 = exp(-light_tau) * pal.direct_phase;
                let ms1 = 0.36 * exp(-0.34 * light_tau) * pal.multi_phase;
                let ms2 = 0.14 * exp(-0.11 * light_tau);
                let fair_energy = (ms0 + ms1 + ms2) * powder;
                let storm_energy = 0.24 + 0.58 * exp(-0.42 * light_tau) * (0.26 + 0.56 * pal.phase_silver);
                step_radiance += pal.sun_rgb * mix(fair_energy, storm_energy, pal.storm_lighting);
            }
            if pal.moonlight > 0.001 {
                step_radiance += pal.moon_rgb * (0.45 + 0.55 * h);
            }

            accum_light += transmission * absorbed * step_radiance;
            transmission *= step_trans;
            depth += optical_depth;
            if (weather < 0.1 && transmission < 0.015) || depth >= 14.0 { break; }
        }
    }

    let opacity = 1.0 - cloud_transmittance(depth, weather);
    let norm = opacity / max(1.0 - transmission, 0.0001);
    let radiance = accum_light * norm;
    let aerial = exp(-max(near - 1600.0, 0.0) * mix(0.00016, 0.00024, weather));
    let final_weight = horizon * mix(0.36, 1.0, aerial);
    return vec4<f32>(radiance, opacity) * final_weight;
}

fn cloud_cirrus_layer(world_origin: vec3<f32>, direction: vec3<f32>, weather: f32, pal: CloudPalette) -> vec4<f32> {
    // Layer 3 (y = 625): ultra-cheap single-intersection wispy cirrus & high cirrocumulus.
    let fair = 1.0 - smoothstep(0.15, 0.85, weather);
    if fair <= 0.001 { return vec4<f32>(0.0); }
    let h0 = world_origin.y - CLOUD_SEA_LEVEL;
    let h3 = CLOUD_L3_HEIGHT - CLOUD_SEA_LEVEL;
    let looking_up = direction.y > 0.004;
    let looking_down = direction.y < -0.004;
    if (h0 < h3 && !looking_up) || (h0 >= h3 && !looking_down) { return vec4<f32>(0.0); }
    let hit = cloud_sphere_hit(h0, direction.y, h3);
    let travel = select(hit.x, hit.y, h0 < h3);
    if travel <= 0.0 || travel >= CLOUD_REACH * 1.15 { return vec4<f32>(0.0); }

    let angle_fade = smoothstep(0.010, 0.075, abs(direction.y));
    let dist_fade = 1.0 - smoothstep(4200.0, CLOUD_REACH * 1.15, travel);
    let weight = fair * angle_fade * dist_fade;
    if weight <= 0.001 { return vec4<f32>(0.0); }

    let pos_xz = world_origin.xz + direction.xz * travel;
    let u = cloud_l3_coordinates(pos_xz);
    // Anisotropic rotated UV stretches cirrus into graceful sweeping filaments & fine high puffs.
    let cirrus_uv = vec2<f32>(4.0 * u.x + 2.0 * u.y, -2.0 * u.x + 4.0 * u.y);
    let wisp_uv = vec2<f32>(9.0 * u.x - 3.0 * u.y, 3.0 * u.x + 9.0 * u.y);
    let t1 = textureSampleLevel(cloud_noise, cloud_noise_sampler, cirrus_uv, 0.0);
    let t2 = textureSampleLevel(cloud_noise, cloud_noise_sampler, wisp_uv + (t1.bg - 0.5) * 0.08, 0.0);

    // Sweeping macro patches keep cirrus delicate and localized instead of filling the whole zenith.
    let patch_mask = smoothstep(0.32, 0.78, t1.a);
    let streak = t1.b * 0.62 + t2.b * 0.38;
    let tuft = t2.g;
    let combined = mix(streak, streak * 0.72 + tuft * 0.28, 0.45);
    let density = smoothstep(0.46, 0.82, combined) * patch_mask;
    if density <= 0.002 { return vec4<f32>(0.0); }

    // Single directional offset tap gives crisp sunlit ridge relief on high cirrus filaments.
    let sun_shift = frame.sun_direction.xz * 0.018;
    let lit_sample = textureSampleLevel(cloud_noise, cloud_noise_sampler, cirrus_uv + sun_shift, 0.0).b;
    let self_shade = exp(-max(lit_sample - t1.b * 0.5, 0.0) * 1.6);

    let alpha = clamp(density * 0.58 * weight, 0.0, 0.72);
    let radiance = (pal.cirrus_ambient + pal.cirrus_sun * (0.42 + 0.58 * self_shade) + pal.moon_rgb * 0.6) * alpha;
    return vec4<f32>(radiance, alpha);
}

fn cloud_volume(world_origin: vec3<f32>, direction: vec3<f32>, weather: f32, steps: u32) -> vec4<f32> {
    let pal = build_cloud_palette(direction, weather);
    let full = steps > 6u;
    let l1_steps = steps;
    let l2_steps = select(0u, CLOUD_L2_STEPS, full);

    var accum_rgb = vec3<f32>(0.0);
    var trans = 1.0;

    if direction.y >= 0.0 {
        // Ascending front-to-back order (L1 y=225 -> L2 y=400 -> L3 y=625) with early-out.
        let l1 = cloud_march_layer(world_origin, direction, weather,
            CLOUD_L1_BASE, CLOUD_L1_THICKNESS, l1_steps, full, false, pal);
        if l1.a > 0.001 {
            accum_rgb += trans * l1.rgb;
            trans *= (1.0 - l1.a);
        }
        if l2_steps > 0u && trans > 0.025 {
            let l2 = cloud_march_layer(world_origin, direction, weather,
                CLOUD_L2_BASE, CLOUD_L2_THICKNESS, l2_steps, full, true, pal);
            if l2.a > 0.001 {
                accum_rgb += trans * l2.rgb;
                trans *= (1.0 - l2.a);
            }
        }
        if trans > 0.025 {
            let l3 = cloud_cirrus_layer(world_origin, direction, weather, pal);
            if l3.a > 0.001 {
                accum_rgb += trans * l3.rgb;
                trans *= (1.0 - l3.a);
            }
        }
    } else {
        // Descending front-to-back order when flying above the clouds (L3 -> L2 -> L1).
        let l3 = cloud_cirrus_layer(world_origin, direction, weather, pal);
        if l3.a > 0.001 {
            accum_rgb += trans * l3.rgb;
            trans *= (1.0 - l3.a);
        }
        if l2_steps > 0u && trans > 0.025 {
            let l2 = cloud_march_layer(world_origin, direction, weather,
                CLOUD_L2_BASE, CLOUD_L2_THICKNESS, l2_steps, full, true, pal);
            if l2.a > 0.001 {
                accum_rgb += trans * l2.rgb;
                trans *= (1.0 - l2.a);
            }
        }
        if trans > 0.025 {
            let l1 = cloud_march_layer(world_origin, direction, weather,
                CLOUD_L1_BASE, CLOUD_L1_THICKNESS, l1_steps, full, false, pal);
            if l1.a > 0.001 {
                accum_rgb += trans * l1.rgb;
                trans *= (1.0 - l1.a);
            }
        }
    }

    return vec4<f32>(accum_rgb, 1.0 - trans);
}

fn clouded_environment(base: vec3<f32>, world_origin: vec3<f32>, direction: vec3<f32>,
                       strength: f32, steps: u32) -> vec3<f32> {
    if !procedural_clouds || frame.dimension != 0 || frame.eye_in != 0u || strength <= 0.0 {
        return base;
    }
    let weather = cloud_weather();
    let deck_opacity = storm_deck_opacity(world_origin, direction, weather) * strength;
    let deck_in_front = direction.y < 0.0 && world_origin.y > STORM_DECK_HEIGHT;
    var colour = base;
    if deck_opacity > 0.0 && !deck_in_front {
        colour = blend_storm_deck(colour, direction, deck_opacity);
    }
    if volumetric_clouds {
        let cloud = cloud_volume(world_origin, direction, weather, steps);
        // Smooth atmospheric horizon haze so distant multi-layer clouds melt naturally into the sky.
        let ref_near = select(
            cloud_layer_interval(world_origin.y, direction.y, CLOUD_L1_BASE, CLOUD_L1_THICKNESS).x,
            cloud_layer_interval(world_origin.y, direction.y, CLOUD_L2_BASE, CLOUD_L2_THICKNESS).x,
            world_origin.y > CLOUD_L1_BASE + CLOUD_L1_THICKNESS
        );
        let haze = 1.0 - exp(-max(ref_near - 1200.0, 0.0) * mix(0.00024, 0.00028, weather));
        let sky_mist = overworld_sky_radiance(vec3<f32>(direction.x, max(direction.y, 0.02), direction.z));
        let misted_cloud = mix(cloud.rgb, sky_mist * cloud.a, haze * 0.62);
        colour = colour * (1.0 - cloud.a * strength) + misted_cloud * strength;
    } else {
        let opacity = cloud_plane_opacity(world_origin, direction, weather);
        if opacity > 0.0 {
            let toward_sun = max(dot(direction, frame.sun_direction), 0.0);
            let dusk = cloud_twilight_weight();
            let sunlit = mix(vec3<f32>(0.76, 0.80, 0.86), vec3<f32>(0.54, 0.30, 0.58), 0.65 * dusk)
                * cloud_fill_tint(toward_sun, weather);
            let sunlight = cloud_sun_tint(toward_sun) * (0.24 + 0.52 * golden_hour())
                * pow(toward_sun, 3.0) * mix(0.32, 1.0, 1.0 - weather);
            let overcast = vec3<f32>(0.18, 0.186, 0.196);
            let night = vec3<f32>(0.018, 0.024, 0.042);
            let cloud = mix(night, mix(sunlit, overcast, weather) * twilight_daylight(), daylight())
                + sunlight * smoothstep(-0.14, 0.06, frame.sun_direction.y) * mix(0.42, 1.0, twilight_daylight());
            colour = mix(colour, cloud, opacity * strength);
        }
    }
    if deck_opacity > 0.0 && deck_in_front {
        colour = blend_storm_deck(colour, direction, deck_opacity);
    }
    return colour;
}

fn clouded_sky(base: vec3<f32>, world_origin: vec3<f32>, direction: vec3<f32>, strength: f32) -> vec3<f32> {
    return clouded_environment(base, world_origin, direction, strength, CLOUD_SKY_STEPS);
}

fn cloud_layer_transmission(world: vec3<f32>, direction: vec3<f32>, weather: f32,
                            base_y: f32, thickness: f32, steps: u32, use_detail: bool, is_l2: bool) -> f32 {
    let interval = cloud_layer_interval(world.y, direction.y, base_y, thickness);
    let near = interval.x;
    let far = interval.y;
    let horizon = cloud_layer_view_weight(world.y, direction.y, near, base_y, thickness, weather);
    if far <= near || horizon <= 0.0 { return 1.0; }
    let mid_xz = world.xz + direction.xz * (0.5 * (near + far));
    let coverage = select(cloud_macro_coverage(mid_xz, weather), cloud_l2_macro_coverage(mid_xz, weather), is_l2);
    var coherent_billow = 0.65;
    let detail_weight = select(0.0, 1.0, use_detail);
    if use_detail {
        let u_mid = select(cloud_coordinates(mid_xz), cloud_l2_coordinates(mid_xz), is_l2);
        let d_tex = textureSampleLevel(cloud_noise, cloud_noise_sampler,
            select(cloud_detail_uv(u_mid), cloud_l2_detail_uv(u_mid), is_l2), 0.0);
        coherent_billow = mix(d_tex.g, d_tex.b, 0.36);
    }
    let step_length = (far - near) / f32(steps);
    let footprint = step_length * length(direction.xz);
    let extinction = step_length * cloud_extinction(weather) * select(1.0, 0.62, is_l2);
    var depth = 0.0;
    for (var sample = 0u; sample < steps; sample++) {
        let travel = near + (f32(sample) + 0.5) * step_length;
        let sample_xz = world.xz + direction.xz * travel;
        let sample_y = cloud_curved_y(world.y, direction.y, travel);
        depth += cloud_density_coherent(sample_xz, sample_y, base_y, thickness,
            coverage, weather, footprint, travel, coherent_billow, detail_weight, is_l2)
            * cloud_distance_fade(travel) * extinction;
        if depth >= 14.0 { break; }
    }
    let aerial = exp(-max(near - 1600.0, 0.0) * mix(0.00016, 0.00024, weather));
    let final_weight = horizon * mix(0.36, 1.0, aerial);
    return mix(1.0, cloud_transmittance(depth, weather), final_weight);
}

fn cloud_light_transmission(position: vec3<f32>, direction: vec3<f32>) -> f32 {
    if !procedural_clouds || frame.dimension != 0 || frame.eye_in != 0u
        || direction.y <= 0.0 {
        return 1.0;
    }
    let world = frame.camera_position + position;
    let weather = cloud_weather();
    let deck_transmission = 1.0 - storm_deck_opacity(world, direction, weather);
    // A clear-day cloud still passes directional sunlight. The solid shadow map
    // separately decides which receivers the attenuated light can reach.
    let daylight_floor = 0.64 * sun_presence() * (1.0 - smoothstep(0.0, 0.44, weather));
    if !volumetric_clouds {
        return deck_transmission * mix(1.0 - cloud_plane_opacity(world, direction, weather), 1.0, daylight_floor);
    }
    let rain_mode = weather > 0.25;
    let l1_steps = select(4u, CLOUD_SKY_STEPS, rain_mode);
    var transmission = cloud_layer_transmission(world, direction, weather,
        CLOUD_L1_BASE, CLOUD_L1_THICKNESS, l1_steps, rain_mode, false);
    if rain_mode && transmission > 0.025 {
        transmission *= cloud_layer_transmission(world, direction, weather,
            CLOUD_L2_BASE, CLOUD_L2_THICKNESS, CLOUD_L2_STEPS, true, true);
    }
    return deck_transmission * mix(1.0, transmission, 1.0 - daylight_floor);
}

fn position_from_depth(uv: vec2<f32>, depth: f32) -> vec3<f32> {
    let p = frame.projection_inverse * vec4<f32>(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0, depth, 1.0);
    let denominator = select(-1.0, 1.0, p.w >= 0.0) * max(abs(p.w), 0.000001);
    return (frame.view_inverse * vec4<f32>(p.xyz / denominator, 1.0)).xyz;
}

fn environment_sky(direction: vec3<f32>) -> vec3<f32> {
    if frame.dimension != 0 { return vec3<f32>(0.0); }
    let sky = frame.sky_color * mix(vec3<f32>(0.58, 0.73, 1.0), vec3<f32>(0.9, 0.95, 1.0),
        clamp(direction.y, 0.0, 1.0));
    let exposure = mix(1.0, twilight_daylight(), smoothstep(-0.18, -0.05, frame.sun_direction.y));
    return mix(sky * exposure, overworld_sky_dome(direction, 0.0), overcast_weight())
        + golden_sky_glow(direction);
}
