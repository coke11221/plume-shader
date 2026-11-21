override sunlight_strength: f32 = 1.0;
override shadow_contrast: f32 = 1.0;
override indirect_warmth: f32 = 1.0;
override block_volumetric_strength: f32 = 0.0;

const DAY_AMBIENT: vec3<f32> = vec3<f32>(0.24, 0.27, 0.32);
const NIGHT_AMBIENT: vec3<f32> = vec3<f32>(0.46, 0.58, 0.82);

fn block_light_access(block_level: f32) -> f32 {
    // Driven by Minecraft's MAX-propagated block light so placing multiple emitters
    // never widens the radius. Suppress the faint outer tail cleanly.
    let t = smoothstep(0.32, 0.95, block_level);
    return t * t;
}

fn field_radiance(sample: vec4<f32>) -> vec3<f32> {
    let reach = sample.a;
    let near_source = smoothstep(0.12, 0.72, reach);
    return sample.rgb * (reach * reach * reach * near_source);
}

fn block_surface_light(position: vec3<f32>, block_level: f32) -> vec3<f32> {
    let access = block_light_access(block_level);
    if access <= 0.0 { return vec3<f32>(0.0); }
    let sample = block_light_color(position);
    let sample_peak = max(sample.r, max(sample.g, sample.b));
    if sample.a <= 0.0 || sample_peak <= 0.0001 { return vec3<f32>(0.0); }
    // Softly bound the additive 3D light field so a single emitter reaches strong
    // brightness and placing 2+ emitters nearby stays bounded in brightness and radius.
    let bounded_peak = min(sample_peak, 1.0) + 0.16 * (1.0 - exp(-max(sample_peak - 1.0, 0.0)));
    let field_color = sample.rgb * (bounded_peak / sample_peak);
    let field_presence = 1.0 - exp(-sample.a * 4.2);
    // Concentrate intensity into a tight, bright pool governed by MAX block light.
    let core_curve = access * smoothstep(0.42, 0.95, block_level);
    let near_core = smoothstep(0.76, 0.94, block_level);
    let color_peak = max(field_color.r, max(field_color.g, field_color.b));
    let diffuse = mix(field_color, vec3<f32>(color_peak), 0.05 + 0.10 * near_core);
    let core_boost = select(1.0, 1.0 + 0.35 * near_core, frame.dimension == 0);
    return diffuse * (core_curve * field_presence * core_boost)
        * select(1.48, 0.84, frame.dimension == 1);
}

fn local_surface_light(position: vec3<f32>, block_level: f32, colored_light: vec3<f32>) -> vec3<f32> {
    let access = block_light_access(block_level);
    if access <= 0.0 { return vec3<f32>(0.0); }

    let sample = block_light_color(position);
    let sample_peak = max(sample.r, max(sample.g, sample.b));
    let has_placed = sample.a > 0.0 && sample_peak > 0.0001;

    let dyn_safe = max(colored_light, vec3<f32>(0.0));
    let dyn_peak = max(dyn_safe.r, max(dyn_safe.g, dyn_safe.b));
    let has_dynamic = dynamic_lights && dynamic_light_strength > 0.0 && dyn_peak > 0.015;
    if !has_placed && !has_dynamic { return vec3<f32>(0.0); }

    var placed_color = vec3<f32>(0.0);
    var placed_presence = 0.0;
    if has_placed {
        let bounded_peak = min(sample_peak, 1.0) + 0.16 * (1.0 - exp(-max(sample_peak - 1.0, 0.0)));
        placed_color = sample.rgb * (bounded_peak / sample_peak);
        placed_presence = 1.0 - exp(-sample.a * 4.2);
    }

    var field_color = placed_color;
    var field_presence = placed_presence;
    if has_dynamic {
        let dyn_hue = dynamic_light_hue(dyn_safe);
        let dyn_presence = smoothstep(0.015, 0.12, dyn_peak) * min(dynamic_light_strength, 1.0);
        if !has_placed {
            field_color = dyn_hue;
            field_presence = dyn_presence;
        } else {
            // Blend placed and dynamic hues cleanly; if dynamic light saturated all 3 channels
            // while a placed light is nearby, prefer the unclipped 3D placed color field.
            let dyn_clipped = smoothstep(0.90, 0.99, min(dyn_safe.r, min(dyn_safe.g, dyn_safe.b)));
            let dyn_w = dyn_peak * (1.0 - 0.75 * dyn_clipped);
            let mix_t = dyn_w / max(sample.a + dyn_w, 0.0001);
            let placed_peak = max(placed_color.r, max(placed_color.g, placed_color.b));
            field_color = mix(placed_color, dyn_hue * max(placed_peak, 1.0), mix_t);
            field_presence = max(placed_presence, dyn_presence);
        }
    }

    // Intensity and radius are governed strictly by Horizon's MAX-propagated block_level,
    // which already combines placed, held, and dropped light sources without additive stacking.
    let core_curve = access * smoothstep(0.42, 0.95, block_level);
    let near_core = smoothstep(0.76, 0.94, block_level);
    let color_peak = max(field_color.r, max(field_color.g, field_color.b));
    let diffuse = mix(field_color, vec3<f32>(color_peak), 0.05 + 0.10 * near_core);
    let core_boost = select(1.0, 1.0 + 0.35 * near_core, frame.dimension == 0);
    return diffuse * (core_curve * field_presence * core_boost)
        * select(1.48, 0.84, frame.dimension == 1);
}

fn block_air_scatter(position: vec3<f32>, block_level: f32) -> vec3<f32> {
    if block_volumetric_strength <= 0.0 || frame.eye_in != 0u { return vec3<f32>(0.0); }
    let effects = clamp(max(frame.night_vision, max(frame.blindness, frame.darkness)), 0.0, 1.0);
    let receiver_light = block_light_access(block_level);
    if receiver_light <= 0.0 || effects >= 1.0 { return vec3<f32>(0.0); }

    // Integrate the camera-to-surface segment through the spatial light field.
    let distance = length(position);
    // The sky stage has no light field. Taper out on distant receivers to soften the skyline.
    let receiver_fade = 1.0 - smoothstep(6.0, 16.0, distance);
    if receiver_fade <= 0.0 { return vec3<f32>(0.0); }
    let step_length = distance / 8.0;
    let step_vector = safe_direction(position) * step_length;
    let step_transmission = exp(-0.045 * step_length);
    var transmission = 1.0;
    var scatter = vec3<f32>(0.0);
    var peak_reach = 0.0;
    for (var i = 0u; i < 8u; i++) {
        let local = block_light_color(step_vector * (f32(i) + 0.5));
        let core = smoothstep(0.66, 0.94, local.a);
        scatter += field_radiance(local) * (core * transmission);
        peak_reach = max(peak_reach, local.a);
        transmission *= step_transmission;
    }
    scatter *= 1.0 - step_transmission;
    // Keep the glow brighter through a source's core and compress accumulated haze on long rays.
    let core_strength = smoothstep(0.78, 0.95, peak_reach);
    let shoulder = mix(0.035, 0.095, core_strength);
    let peak = max(scatter.r, max(scatter.g, scatter.b));
    let dimension_strength = select(1.0, select(0.76, 0.58, frame.dimension == 1), frame.dimension != 0);
    return scatter / (1.0 + peak / shoulder) * mix(1.0, 1.65, core_strength)
        * block_volumetric_strength * dimension_strength * receiver_light * receiver_fade * (1.0 - effects);
}

fn apply_block_air_scatter(lit: vec3<f32>, position: vec3<f32>, block_level: f32) -> vec3<f32> {
    let scatter = block_air_scatter(position, block_level);
    let luminance = vec3<f32>(0.2126, 0.7152, 0.0722);
    // Keep the airborne glow tied to the emitter's color with a soft neutral component.
    let haze = mix(vec3<f32>(dot(scatter, luminance)), scatter, 0.42);
    let peak = max(haze.r, max(haze.g, haze.b));
    let lit_luma = dot(max(lit, vec3<f32>(0.0)), luminance);
    // Keep the floor gentle so dark textures stay readable, and suppress haze on bright sunlit surfaces.
    let bright_suppression = 1.0 - smoothstep(0.18, 0.62, lit_luma);
    let allowance = (0.0025 + 0.14 * lit_luma) * bright_suppression;
    return lit + haze * min(1.0, allowance / max(peak, 0.0001));
}

fn solar_radiance() -> vec3<f32> {
    let clear = celestial_weather();
    let sunset = sunset_weight();
    let warm_day = 1.0 - smoothstep(0.86, 0.955, frame.sun_direction.y);
    let hue = mix(NEUTRAL_SUN, sun_palette(), max(clear, sunset));
    let low_sun_energy = mix(0.50, 1.0, smoothstep(-0.015, 0.12, frame.sun_direction.y));
    return hue * sunlight_strength * low_sun_energy
        * (1.0 + 0.08 * warm_day * clear + 0.42 * golden_hour() * clear + 0.12 * sunset);
}

fn leaf_light_incidence(angle: f32) -> f32 {
    let front = max(angle, 0.0);
    return max(front, (0.54 + 0.36 * abs(angle)) * (0.85 + 0.15 * front));
}

fn shade_surface(position: vec3<f32>, normal: vec3<f32>, sky_light: f32,
                 albedo: vec3<f32>, emission: f32, local: vec3<f32>, grass: bool,
                 green_receiver: bool, noon_fill: f32) -> vec3<f32> {
    return shade_surface_with_celestial_response(position, normal, sky_light, albedo, emission, local,
        grass, false, green_receiver, false, noon_fill, vec2<f32>(0.0), vec4<f32>(0.0)).rgb;
}

fn shade_surface_with_celestial_response(position: vec3<f32>, normal: vec3<f32>, sky_light: f32,
                                         albedo: vec3<f32>, emission: f32, local: vec3<f32>, grass: bool,
                                         leaves: bool, green_receiver: bool, solid: bool, noon_fill: f32,
                                         response: vec2<f32>, highlight: vec4<f32>) -> vec4<f32> {
    if frame.dimension != 0 {
        let ambient = select(vec3<f32>(0.046, 0.024, 0.018), vec3<f32>(0.022, 0.027, 0.043),
            frame.dimension == 1);
        let floor_light = ambient * (0.80 + 0.45 * frame.brightness);
        let emissive = select(0.0, mix(1.10, 1.75, smoothstep(0.45, 0.95, emission)), emission > 0.0);
        return vec4<f32>(albedo * max(floor_light + local, vec3<f32>(emissive)), 0.0);
    }
    let day = daylight();
    let sky_level = clamp(sky_light, 0.0, 1.0);
    let sky = sky_level * sky_level;
    let clear = clear_weather();
    let day_ambient = mix(DAY_AMBIENT, vec3<f32>(0.28, 0.31, 0.36), noon_fill * clear);
    let up = vec3<f32>(0.0, 1.0, 0.0);
    // Sample toward the open hemisphere, with darker fill on downward faces.
    // Thin grass uses the same upward bias on both sides of its cutout.
    let fill_normal = select(normal, up, grass);
    let visibility = shadow_visibility(position, fill_normal);
    let light_angle = dot(normal, frame.light_direction);
    let lambert = max(light_angle, 0.0);
    let sun = sun_presence();
    let daytime_sun = smoothstep(0.30, 0.68, frame.sun_direction.y);
    let sunset = sunset_weight() * sun;
    let moon = (1.0 - sun) * moonlight_presence() * f32(night_brightness > 0.0);
    let low_sun = golden_hour();
    let low_moon = 1.0 - smoothstep(0.34, 0.74, frame.moon_direction.y);
    let open_sky = smoothstep(0.32, 0.80, sky_level) * f32(frame.eye_in == 0u);
    let leaf_exposure = select(0.0, open_sky, leaves);
    let side = select(0.0, 1.0 - smoothstep(0.20, 0.86, abs(normal.y)), solid);
    let side_axis = smoothstep(0.95, 0.995, max(abs(normal.x), abs(normal.z)));
    // Exposed block sides share the light reaching the top face, without lighting walls facing away from the sun.
    let side_light = sun * mix(0.12, 1.0, low_sun) + moon * mix(0.40, 1.0, low_moon);
    let side_facing = smoothstep(select(-0.22, -0.60, leaves), select(-0.02, 0.0, leaves), light_angle);
    let top_light_mix = side * open_sky * side_axis * visibility * side_light * clear * side_facing;
    // Horizon decodes the baked gamma-space face factors with exponent 2.2.
    let side_unshade = mix(1.0 / pow(0.8, 2.2), 1.0 / pow(0.6, 2.2), abs(normal.x));
    // Recover open-sky diffuse light on solid sides already darkened by the vertex tint.
    let side_skylight = side * side_axis * f32(!leaves) * daytime_sun
        * smoothstep(0.48, 0.88, open_sky * sky_level);
    let ambient_side_mix = max(top_light_mix, side_skylight);
    // Keep vertical walls darker than upward-facing open ground outside high noon.
    let side_bounce = 1.0 + select(0.08, 0.68, noon_fill > 0.5) * side_skylight;
    let sky_normal = mix(fill_normal, up, top_light_mix);
    let fill_direction = vec3<f32>(sky_normal.x, 0.26 + 0.74 * max(sky_normal.y, 0.0), sky_normal.z);
    // Diffuse skylight samples the dome without the directional solar halo.
    let dome = overworld_sky_dome(fill_direction, 0.0);
    let dome_luminance = dot(dome, vec3<f32>(0.2126, 0.7152, 0.0722));
    let clamped_dome = clamp(dome / max(dome_luminance, 0.004), vec3<f32>(0.55), vec3<f32>(1.45));
    let sky_tint = mix(vec3<f32>(1.0), clamped_dome, mix(0.32, 0.20, low_sun * sun));
    let facing_sky = select(0.86 + 0.28 * clamp(sky_normal.y, -1.0, 0.0),
        0.86 + 0.14 * sky_normal.y, sky_normal.y >= 0.0);
    let foliage = grass || green_receiver;
    let sky_level_fill = select(0.48, 1.42, foliage) * (sky_level - sky);
    let sky_energy_fill = select(0.15, 0.40, foliage) * sky;
    let crown_fill = leaf_exposure * sky * (0.30 + 0.16 * max(sky_normal.y, 0.0));
    let shade_access = open_sky * smoothstep(0.50, 0.90, sky_level) * (1.0 - visibility);
    // Only lift harsh cast shadows when direct sun can actually reach open ground;
    // in rain/overcast this must fade to zero so shadows never render brighter than lit ground.
    let shaded_fill = select(select(0.06, 0.10, noon_fill > 0.5), 0.32, foliage || leaves)
        * sky * shade_access * sun * (1.0 - overcast_weight());
    // Recover some diffuse light lost to the squared skylight response under leaves.
    let day_access = sky + open_sky * (sky_level_fill + sky_energy_fill) * facing_sky + crown_fill + shaded_fill;
    let ambient = mix(NIGHT_AMBIENT * (night_brightness * 0.18 * sky),
                      day_ambient * (day_access / shadow_contrast) * twilight_daylight(), day) * sky_tint * facing_sky
        * mix(1.0, side_unshade, ambient_side_mix) * side_bounce;
    // Lift grazing sunrise and sunset light gently on exposed tops without over-saturating flat ground.
    let low_sun_wrap = (1.0 - smoothstep(0.20, 0.56, frame.sun_direction.y)) * sun;
    let warm_day = (1.0 - smoothstep(0.86, 0.955, frame.sun_direction.y)) * sun;
    let low_sun_fill_strength = max(sunset, 0.80 * low_sun_wrap);
    let sunset_fill = 0.52 * low_sun_fill_strength * max(normal.y, 0.0) * sqrt(lambert) * (1.0 - lambert);
    // The sky fill above provides the light on faces in shade.
    var diffuse = (lambert + sunset_fill) * visibility;
    if grass {
        // Thin blades receive light from both sides.
        let overhead = smoothstep(0.15, 0.80, frame.sun_direction.y);
        let two_sided = 0.40 + 0.45 * abs(light_angle);
        diffuse = mix(two_sided, 0.94, 0.70 * overhead) * visibility;
    }
    if leaves {
        // A leaf sprite represents many thin leaves with different orientations.
        // Reuse the face's shadow and cloud visibility for the diffuse light.
        let leaf_weight = leaf_exposure * max(smoothstep(0.0, 0.10, frame.sun_direction.y), moon);
        let leaf_gain = visibility * (1.08 + 0.16 * mix(low_sun, low_moon, moon));
        let face_light = leaf_light_incidence(light_angle) * leaf_gain;
        let crown_light = leaf_light_incidence(frame.light_direction.y) * leaf_gain;
        diffuse = mix(diffuse, max(diffuse, face_light), leaf_weight);
        diffuse = mix(diffuse, crown_light * side_unshade, top_light_mix);
    } else if top_light_mix > 0.0 {
        let overhead = max(frame.light_direction.y, 0.0);
        let top_wrap = 0.52 * low_sun_fill_strength * sqrt(overhead) * (1.0 - overhead) * (1.0 - lambert);
        let top_light = (overhead + top_wrap) * visibility;
        diffuse = mix(diffuse, max(diffuse, top_light * side_unshade), top_light_mix);
    }
    let solar = solar_radiance();
    let tint = sunlight_tint();
    let plant_neutral = (0.64 - 0.08 * low_sun * golden_warmth) * mix(1.0, 0.55, daytime_sun);
    // Balance red vs green on green foliage while preserving the warm low-blue golden sunlight spectrum.
    let foliage_solar = vec3<f32>(mix(solar.r, solar.g, plant_neutral),
        mix(solar.g, solar.r, 0.12 * plant_neutral), solar.b);
    var sun_spectrum = select(solar, foliage_solar, green_receiver);
    if leaves && green_receiver && side > 0.0 {
        // Keep deep amber from overwhelming the green pigment on a leaf's side.
        let pigment_ratio = albedo.r / max(albedo.g, 0.001);
        let red_limit = mix(1.38, 1.04, smoothstep(0.45, 0.83, pigment_ratio));
        let excess_red = max(sun_spectrum.r - red_limit * sun_spectrum.g, 0.0) * side;
        // Trade excess red for green at equal diffuse luminance before the user's RGB tint.
        let green_gain = excess_red * (0.2126 / 0.7152) * pigment_ratio;
        sun_spectrum = vec3<f32>(sun_spectrum.r - excess_red, sun_spectrum.g + green_gain, sun_spectrum.b);
    }
    let sunlight = sun_spectrum * tint;
    let moonlight = moonlight_colour() * (1.0 - sun);
    // The grazing lobe supplies its own falloff. Fade it at the lighting terminator.
    let dry_glint = response.x * (1.0 - highlight.a);
    let glint = dry_glint * min(6.0 * lambert, 1.0);
    let through = response.y * max(-light_angle, 0.0);
    // Keep side highlights strictly independent of camera distance.
    let side_glint = select(0.0, dry_glint * top_light_mix, side > 0.0 && dry_glint > 0.0);
    let dry_sun = smoothstep(0.0, 0.075, frame.sun_direction.y);
    let weather_light = celestial_weather();
    let surface_visibility = visibility * sky * weather_light;
    var foliage_glow = 0.0;
    if response.y > 0.0 && dry_sun > 0.0 {
        let sightline = safe_direction(position);
        let alignment = smoothstep(0.48, 0.92, dot(sightline, frame.sun_direction));
        // Light can pass through thin leaves and blades from either side.
        let incidence = abs(dot(normal, frame.sun_direction));
        foliage_glow = response.y * alignment * (0.38 + 0.62 * incidence)
            * dry_sun * surface_visibility;
    }
    let has_dry_light = (glint + through + side_glint) * surface_visibility * max(dry_sun, moon) > 0.0;
    // Skylight prevents direct light where the map cannot resolve a roof or cave.
    var cloud = 1.0;
    let has_highlight = surface_visibility > 0.0 && any(highlight.rgb > vec3<f32>(0.0));
    if diffuse * sky > 0.0 || has_dry_light || has_highlight || foliage_glow > 0.0 {
        cloud = cloud_light_transmission(position, celestial_direction());
    }
    let direct_exposure = diffuse * sky * weather_light * cloud;
    var sky_pigment = albedo;
    var highlight_weight = 0.0;
    let luma_weights = vec3<f32>(0.2126, 0.7152, 0.0722);
    if green_receiver {
        let green_excess = (albedo.g - max(albedo.r, albedo.b)) / max(albedo.g, 0.001);
        // Bring out muted biome pigments across warm daylight and protect already vivid greens.
        let boost = 0.20 * max(daytime_sun, 0.65 * sun) * open_sky * mix(0.55, 1.0, clear)
            * smoothstep(0.08, 0.33, green_excess) * (1.0 - smoothstep(0.54, 0.78, green_excess));
        let luma = dot(albedo, luma_weights);
        let chroma = vec3<f32>(0.55 * albedo.r, albedo.g - luma, albedo.b - luma);
        sky_pigment = max(albedo + boost * chroma, vec3<f32>(0.0));
        highlight_weight = 0.10 * smoothstep(0.42, 0.72, green_excess) * daytime_sun
            * smoothstep(0.62, 0.98, direct_exposure * visibility);
    }
    let sun_pigment = sky_pigment * sun_spectrum;
    let sun_diffuse = mix(sun_pigment, vec3<f32>(dot(sun_pigment, luma_weights)), highlight_weight);
    let direct = (albedo * moonlight + sun_diffuse * tint * sun) * direct_exposure;
    let floor_light = 0.008 + 0.008 * frame.brightness;
    let sunlit_warm_fill = max(sunset, max(0.65 * low_sun_wrap, 0.35 * warm_day)) * visibility * cloud * open_sky
        * (0.35 + 0.65 * max(max(normal.y, 0.0), lambert));
    // Warm the ambient sky fill in open golden-hour shade so shadows and foliage
    // share the warm sunrise/sunset mood instead of turning cold grey-blue.
    let shade_warm_fill = select(0.85, 0.28, green_receiver) * low_sun_wrap * open_sky * clear;
    let warm_fill = max(sunlit_warm_fill, shade_warm_fill);
    // Reserve cooler fill for shade while avoiding blue cast or grey wash on warm terrain faces.
    let sunlit = daytime_sun * open_sky * smoothstep(0.32, 1.05, direct_exposure * sunlight_strength);
    let sky_fill = mix(ambient, vec3<f32>(dot(ambient, luma_weights)),
        max(mix(0.32, 0.65, noon_fill) * sunlit, mix(0.22, 0.57, noon_fill) * side_skylight));
    let fill_tint = mix(vec3<f32>(1.14, 0.96, 0.66), vec3<f32>(1.18, 0.94, 0.56), sunset);
    let surface_ambient = sky_fill * mix(vec3<f32>(1.0), fill_tint, warm_fill);
    // Artistic diffuse bounce approximation, bounded by skylight; no global illumination pass.
    let sp = sun_palette();
    let bounce_hue = select(sp, vec3<f32>(mix(sp.r, sp.g, 0.45), sp.g, sp.b), green_receiver);
    let bounce_amount = select(0.095 + 0.145 * low_sun + 0.14 * low_sun_wrap,
        0.065 + 0.095 * low_sun + 0.12 * low_sun_wrap, green_receiver);
    // Use weather attenuation (not the visibility-gated `cloud` variable) so bounced warmth
    // never defaults to clear-sky 1.0 inside rain/overcast shadows while dimming lit ground.
    let warm_bounce = bounce_hue * tint * bounce_amount * indirect_warmth
        * sun * sky * weather_light * mix(0.22, 1.0, clear_weather()) * twilight_daylight();
    let emissive = select(0.0, mix(1.25, 2.25, smoothstep(0.45, 0.95, emission)), emission > 0.0);
    // Limit block/dynamic light stacking where environmental sunlight is already bright
    // (especially warm sunrise/sunset on yellow or warm blocks) while keeping night and caves vivid.
    let env_irradiance = surface_ambient + warm_bounce
        + (moonlight + sun_spectrum * tint * sun) * direct_exposure;
    let env_luma = dot(env_irradiance, luma_weights);
    let env_peak = max(env_irradiance.r, max(env_irradiance.g, env_irradiance.b));
    let env_lit = sky_pigment * (surface_ambient + warm_bounce) + direct;
    let env_lit_peak = max(env_lit.r, max(env_lit.g, env_lit.b));
    let warm_sun_active = max(low_sun, sunset) * sun;
    let env_adapt = 1.0 / (1.0 + 1.85 * env_luma + (0.85 + 0.65 * warm_sun_active) * env_peak);
    let surface_headroom = mix(0.14, 1.0, 1.0 - smoothstep(0.16, 0.56, env_lit_peak));
    var local_lit = albedo * (local * env_adapt * surface_headroom);
    let local_peak = max(local_lit.r, max(local_lit.g, local_lit.b));
    let warm_sky = warm_sun_active * open_sky;
    let local_knee = mix(0.42, 0.22, warm_sky);
    let local_cap = mix(0.92, 0.44, warm_sky);
    if local_peak > local_knee {
        let room = local_cap - local_knee;
        let compressed = local_knee + room * (1.0 - exp((local_knee - local_peak) / room));
        local_lit *= compressed / local_peak;
    }
    let diffuse_lit = env_lit + albedo * vec3<f32>(floor_light) + local_lit;
    var lit = max(diffuse_lit, albedo * emissive);
    var solar_peak = 0.0;
    if has_highlight {
        let reflection = highlight.rgb * (solar * tint * sun + moonlight) * (surface_visibility * cloud);
        lit += reflection;
        solar_peak = select(0.0, max(reflection.r, max(reflection.g, reflection.b)), highlight.a > 0.0);
    }
    if has_dry_light {
        let view = safe_direction(-position);
        let half_vector = safe_direction(view + frame.light_direction);
        let cosine = max(dot(normal, half_vector), 0.0);
        let squared = cosine * cosine;
        let lobe = squared * squared;
        let grazing = 1.0 - clamp(dot(view, half_vector), 0.0, 1.0);
        let grazing_squared = grazing * grazing;
        let grazing_strength = select(1.0, 0.0, side > 0.0);
        let pigment_peak = max(albedo.r, max(albedo.g, albedo.b));
        let luminance_weights = vec3<f32>(0.2126, 0.7152, 0.0722);
        let solar_luma = dot(solar, luminance_weights);
        let dry_solar_tint = tint * dry_sun;
        let pigment = albedo / max(pigment_peak, 0.001);
        var reflected_light = vec3<f32>(0.0);
        var reflected = vec3<f32>(0.0);
        if leaves {
            // Leaves keep a shimmering pale grazing return along the sunward crown.
            let peak = lobe * lobe * (mix(0.55, 0.14, side) + 6.7 * grazing_squared * grazing_squared * grazing_strength);
            let texture_detail = 0.27 + 0.80 * pigment_peak;
            reflected_light = mix(solar, vec3<f32>(solar_luma), 0.84) * dry_solar_tint + moonlight;
            let broad = mix(0.36, 0.10, side) * lobe;
            reflected = reflected_light * (glint * (broad + peak) * texture_detail);
        } else {
            // Rough solid terrain catches a luminous, warm golden grazing sheen driven by
            // pixel texture brightness and micro-relief, avoiding a flat polished glaze.
            let warm_solar = mix(solar, vec3<f32>(solar_luma), 0.30);
            let top_tint = mix(vec3<f32>(1.0), pigment, 0.32);
            reflected_light = warm_solar * top_tint * dry_solar_tint + moonlight * mix(vec3<f32>(1.0), pigment, 0.35);
            let tex_mask = smoothstep(0.03, 0.45, pigment_peak);
            let tex_detail = tex_mask * (0.14 + 1.55 * pigment_peak);
            let velvet_lobe = squared * (mix(0.32, 0.04, side) + 1.15 * grazing_squared * grazing_strength)
                + lobe * (mix(0.34, 0.35, side) + mix(0.0, 0.95 * lobe, side) + 2.85 * grazing_squared * grazing * grazing_strength);
            reflected = reflected_light * (glint * velvet_lobe * tex_detail);
        }
        if side > 0.0 {
            // Keep solid block side return clean and true to natural pigment; preserve vivid leaf chroma.
            let base_pigment = select(pigment, mix(pigment, pigment * pigment, 0.18), leaves);
            let chroma = base_pigment / max(dot(base_pigment, luminance_weights), select(0.24, 0.20, leaves));
            let side_solar = select(mix(solar, vec3<f32>(solar_luma), 0.35), vec3<f32>(solar_luma), leaves);
            let pigment_return = mix(vec3<f32>(1.0), chroma, select(0.45, 0.94, leaves))
                * (side_solar * dry_solar_tint + moonlight);
            reflected_light = mix(reflected_light, pigment_return, side);
        }
        var side_reflection = vec3<f32>(0.0);
        if side_glint > 0.0 {
            // Clean, distance-independent directional highlight on exposed block sides.
            let alignment = clamp(0.78 * cosine + 0.52 * max(half_vector.y, 0.0), 0.0, 1.0);
            let alignment_squared = alignment * alignment;
            let texture_mask = mix(0.25, 1.0, smoothstep(0.06, 0.50, pigment_peak * side_unshade));
            let side_scale = select(0.55, 1.45, leaves);
            let intensity = side_scale * side_glint * alignment_squared * alignment_squared * texture_mask;
            side_reflection = reflected_light * intensity;
        }
        let forward = max(dot(-view, frame.light_direction), 0.0);
        let scattered = through * (0.34 + 0.66 * forward * forward);
        let transmission = (sunlight * dry_sun + moonlight) * albedo * scattered;
        lit += (reflected + side_reflection + transmission) * (surface_visibility * cloud);
    }
    let foliage_peak = max(solar.r * tint.r, max(solar.g * tint.g, solar.b * tint.b));
    return vec4<f32>(lit, solar_peak + foliage_glow * cloud * foliage_peak);
}

fn surface_highlight(position: vec3<f32>, normal: vec3<f32>, smoothness: f32,
                     f0: vec3<f32>, albedo: vec3<f32>, strength: vec2<f32>) -> vec4<f32> {
    let hdr_sun = frame.sun_direction.y > 0.0 && strength.x > 0.0;
    if frame.dimension != 0 || (!hdr_sun && strength.y <= 0.0) { return vec4<f32>(0.0); }
    let light = select(frame.light_direction, frame.sun_direction, hdr_sun);
    let view = safe_direction(-position);
    let nl = dot(normal, light);
    let nv = dot(normal, view);
    if nl <= 0.0 || nv <= 0.0 { return vec4<f32>(0.0); }
    var solar_spot = 0.0;
    if hdr_sun {
        // Taper away from the mirror ray in angle and across the plane of the face.
        // The fixed world-space falloff keeps the affected area from growing with distance.
        let toward_sun = smoothstep(0.25, 0.65, dot(-view, light));
        let mirror = reflect(-light, normal);
        let angle = max(1.0 - dot(mirror, view), 0.0) / mix(0.00062, 0.00017, smoothness);
        if toward_sun <= 0.0 || angle >= 7.0 { return vec4<f32>(0.0); }
        let radius = mix(0.42, 0.22, smoothness);
        let to_face = max(dot(-position, normal) / nl, 0.0);
        let offset = (position + mirror * to_face) / radius;
        solar_spot = toward_sun * exp(-max(angle, 0.5 * dot(offset, offset)));
        if solar_spot < 0.001 { return vec4<f32>(0.0); }
    }
    let half_vector = safe_direction(view + light);
    let nh = max(dot(normal, half_vector), 0.0);
    let vh = max(dot(view, half_vector), 0.0);
    // A finite-width solar highlight avoids subpixel fireflies on flat block faces.
    let roughness = max(1.0 - smoothness, 0.16);
    let a2 = pow(roughness, 4.0);
    let denominator = nh * nh * (a2 - 1.0) + 1.0;
    let k = pow(roughness + 1.0, 2.0) / 8.0;
    let geometry = (nv / (nv * (1.0 - k) + k)) * (nl / (nl * (1.0 - k) + k));
    let fresnel = fresnel_schlick(f0, vh);
    if !hdr_sun {
        let distribution = a2 / max(3.14159265 * denominator * denominator, 0.000001);
        let specular = min(distribution * geometry / max(4.0 * nv, 0.001), 8.0);
        return vec4<f32>(fresnel * (specular * strength.y), 0.0);
    }
    // Normalize the GGX peak so rough blocks can bloom without flattening polished highlights.
    let peak = a2 / denominator;
    let lobe = peak * peak * peak * geometry / max(nv, 0.18) * smoothstep(0.0, 0.09, nl) * strength.x;
    let reflectance = dot(fresnel, vec3<f32>(0.2126, 0.7152, 0.0722));
    let material_peak = max(albedo.r, max(albedo.g, albedo.b));
    let pigment = albedo / max(material_peak, 0.001);
    let colour = mix(vec3<f32>(1.0), pigment, 0.16);
    // Transfer the legacy dry sheen to the solar reflection around its mirror peak.
    let dry_fade = solar_spot * sun_presence();
    let gain = lobe * reflectance / (reflectance + 0.04);
    let polished = smoothstep(0.50, 0.80, smoothness);
    let shoulder = mix(0.75, 0.88, polished);
    let texture_detail = mix(0.86, 1.0, smoothstep(0.025, 0.24, material_peak));
    let intensity = gain / (1.0 + gain / shoulder) * mix(texture_detail, 1.0, polished);
    return vec4<f32>(colour * (intensity * solar_spot), dry_fade);
}

fn respect_effects(lit: vec3<f32>, base: vec3<f32>, vanilla_light: vec3<f32>) -> vec3<f32> {
    // Engine lightmap carries potion/status effects. Fade back to it while active.
    let effect = max(frame.night_vision, max(frame.blindness, frame.darkness));
    return mix(lit, base * vanilla_light, clamp(effect, 0.0, 1.0));
}
