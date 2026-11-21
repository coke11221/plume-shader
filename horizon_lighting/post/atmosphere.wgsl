// Shaft integration samples by preset: Lite 12, Balanced 20, High 28, Ultra 40.
override volumetric_samples: i32 = select(select(select(40, 28, quality_preset == PRESET_HIGH), 20,
    quality_preset == PRESET_BALANCED), 12, quality_preset == PRESET_LITE);
override underwater_shafts: f32 = 2.0;

// 4x4 ordered Bayer phase in (0, 1) so every 4x4 half-res block covers all 16
// stratified sub-steps exactly once, cancelling cleanly in the 5x5 upsample filter.
fn bayer4x4(pixel: vec2<f32>) -> f32 {
    let p = vec2<u32>(max(floor(pixel), vec2<f32>(0.0))) & vec2<u32>(3u);
    let x = p.x;
    let y = p.y;
    let index = (((x ^ y) & 1u) << 3u)
              | ((y & 1u) << 2u)
              | ((((x ^ y) >> 1u) & 1u) << 1u)
              | ((y >> 1u) & 1u);
    return (f32(index) + 0.5) * (1.0 / 16.0);
}

fn air_shadow_visibility(position: vec3<f32>) -> f32 {
    let clip = frame.shadow_view_proj * vec4<f32>(position, 1.0);
    let edge_fade = shadow_edge_fade(clip.xy);
    let uv = shadow_uv(clip.xy);
    if edge_fade >= 1.0 || clip.z <= 0.0 || clip.z >= 1.0
        || any(uv <= vec2<f32>(0.002)) || any(uv >= vec2<f32>(0.998)) {
        return 0.0; // Never assume light outside reliable map coverage.
    }
    return textureSampleCompareLevel(shadow_map, shadow_sampler, uv, clip.z - 0.00008) * (1.0 - edge_fade);
}

// Distance from the lit water entry point and the solid-shadow visibility.
fn underwater_light_path(position: vec3<f32>, depth_per_block: f32) -> vec2<f32> {
    let p = shadow_position(position);
    if any(p.xy <= vec2<f32>(0.002)) || any(p.xy >= vec2<f32>(0.998))
        || p.z <= 0.0 || p.z >= 1.0 {
        return vec2<f32>(0.0);
    }
    let solid_visibility = textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy, p.z - 0.00008);
    if solid_visibility <= 0.0 { return vec2<f32>(0.0); }
    let size = vec2<i32>(textureDimensions(shadow_map_translucent));
    let texel = min(vec2<i32>(p.xy * vec2<f32>(size)), size - 1);
    let surface_depth = textureLoad(shadow_map_translucent, texel, 0);
    if surface_depth >= p.z || textureLoad(shadow_color, texel, 0).a < 0.995 { return vec2<f32>(0.0); }

    let water_path = (p.z - surface_depth) / depth_per_block;
    let edge = max(abs(p.x * 2.0 - 1.0), abs(p.y * 2.0 - 1.0));
    return vec2<f32>(water_path, solid_visibility * (1.0 - smoothstep(0.82, 0.98, edge)));
}

fn underwater_sun_sample(position: vec3<f32>, depth_per_block: f32) -> f32 {
    let path = underwater_light_path(position, depth_per_block);
    if path.y <= 0.0 { return 0.0; }
    // Keep each concentration of light anchored to its point of entry into the water.
    let entry = (frame.camera_position + position + frame.light_direction * path.x).xz;
    let across = dot(entry, vec2<f32>(1.17, 0.53));
    let along = dot(entry, vec2<f32>(-0.42, 0.88));
    let time = frame.time;
    let wave = cos(across + 0.65 * sin(along - 0.54 * time) - 0.85 * time);
    let cross_wave = cos(along * 1.6 + 0.52 * time + 0.55 * sin(across));
    let focal = pow(clamp(0.5 + 0.34 * wave + 0.16 * cross_wave, 0.0, 1.0), 4.0);
    return path.y * (0.18 + 2.5 * focal) * exp(-0.055 * path.x) * smoothstep(0.01, 0.22, path.x);
}

fn underwater_sun_scatter(direction: vec3<f32>, distance: f32, jitter: f32, effects: f32) -> vec3<f32> {
    let step_length = min(distance, 33.0) / f32(volumetric_samples);
    let depth_per_block = max(abs((frame.shadow_view_proj * vec4<f32>(frame.light_direction, 0.0)).z), 0.00001);
    var integrated = 0.0;
    for (var i = 0; i < volumetric_samples; i++) {
        let travel = (f32(i) + jitter) * step_length;
        let visibility = underwater_sun_sample(direction * travel, depth_per_block);
        integrated += visibility * exp(-UNDERWATER_VIEW_EXTINCTION * travel) * 0.036 * step_length;
    }
    // The apparent sun moves toward the vertical when seen through the air-water interface.
    let refracted_sun = -refract(-frame.sun_direction, vec3<f32>(0.0, 1.0, 0.0), 1.0 / 1.333);
    let alignment = clamp(dot(direction, refracted_sun), 0.0, 1.0);
    let phase = 0.26 + 0.85 * pow(alignment, 5.0) + 2.1 * pow(alignment, 20.0);
    var direct = 0.0;
    if alignment > 0.90 && direction.y > 0.0 {
        let camera_path = underwater_light_path(vec3<f32>(0.0), depth_per_block);
        let depth_to_surface = camera_path.x * frame.light_direction.y;
        let travel_to_surface = depth_to_surface / direction.y;
        // Resolve the forward glow only if the view ray reaches the sunlit interface.
        let visible_exit = smoothstep(travel_to_surface, travel_to_surface + 0.5, distance);
        let exit_visibility = air_shadow_visibility(direction * (travel_to_surface + 0.10));
        let halo = 0.14 * pow(alignment, 38.0) + 0.30 * pow(alignment, 210.0);
        direct = halo * exp(-0.09 * travel_to_surface) * min(camera_path.y, exit_visibility) * visible_exit;
    }
    let light = mix(sun_colour(), vec3<f32>(1.0, 0.98, 0.90), 0.75);
    return light * (integrated * phase + direct) * underwater_shafts * clear_weather() * effects
        * smoothstep(0.055, 0.28, frame.sun_direction.y);
}

fn integrate_air_light(origin: vec3<f32>, ray: vec3<f32>, distance: f32,
                       samples: i32, jitter: f32) -> f32 {
    let body = celestial_direction();
    let available = select(air_moon_availability(), air_sun_availability(), frame.sun_direction.y >= 0.0);
    if available <= 0.0 || distance <= 0.0 { return 0.0; }
    let step_length = distance / f32(samples);
    // Follow the cloud field along the path with two lookups. Solid occluders
    // still get an independent shadow-map lookup at every integration step.
    let near_light = cloud_light_transmission(origin + ray * (0.25 * distance), body);
    let far_light = cloud_light_transmission(origin + ray * (0.75 * distance), body);
    var transmission = 1.0;
    var scattering = 0.0;
    for (var i = 0; i < samples; i++) {
        let segment = f32(i);
        let sample_position = origin + ray * ((segment + jitter) * step_length);
        let mid_height = frame.camera_position.y + origin.y + ray.y * ((segment + 0.5) * step_length);
        let height_above = max(mid_height - AIR_LAYER_BASE, 0.0);
        // Valley-hugging air density: stronger through river valleys and forest trunks,
        // thinning cleanly above the canopy so tall treetops and sky stay unobstructed.
        let valley_density = mix(0.0058, 0.0095, frame.rain) * (0.14 + 0.86 * exp(-height_above / 34.0));
        let extinction = exp(-valley_density * step_length);
        let cloud_light = mix(near_light, far_light, clamp((segment + jitter) * 2.0 / f32(samples) - 0.5, 0.0, 1.0));
        scattering += transmission * (1.0 - extinction) * air_shadow_visibility(sample_position) * cloud_light;
        transmission *= extinction;
    }
    return scattering * available;
}

fn post(input: PostInput) -> vec4<f32> {
    let underwater = frame.eye_in == 1u;
    let enabled = select(air_shaft_strength() > 0.0,
        underwater_shafts > 0.0 && frame.sun_direction.y > 0.001, underwater);
    if !enabled || !shadows || frame.has_shadow == 0u
        || frame.dimension != 0 || frame.eye_in > 1u {
        return vec4<f32>(0.0, 0.0, 0.0, 1.0);
    }
    let sample_depth = max(input.depth, 0.00001);
    let point = view_position(input.uv, sample_depth);
    let reach = atmosphere_reach(underwater);
    // Stable 4x4 ordered dither: cancels cleanly across 4x4 neighborhoods with zero frame noise.
    let jitter = bayer4x4(input.pixel);
    let effects = 1.0 - clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
    if underwater {
        let distance = select(min(length(point), reach), reach, input.depth == 0.0);
        return vec4<f32>(underwater_sun_scatter(safe_direction(point), distance, jitter, effects), 1.0);
    }
    let eye = frame.projection_inverse[2];
    let origin = (frame.view_inverse * vec4<f32>(eye.xyz / eye.w, 1.0)).xyz;
    let ray = point - origin;
    let distance = select(min(length(ray), reach), reach, input.depth == 0.0);
    let direction = safe_direction(ray);
    let is_day = frame.sun_direction.y >= 0.0;
    let integrated = integrate_air_light(origin, direction, distance, volumetric_samples, jitter);
    let cos_theta = dot(direction, celestial_direction());
    // Daytime: dual-lobe Mie phase keeps off-axis terrain crisp while lighting sunward shafts.
    // Nighttime: hazy mist floor + strong forward moon lobe for intense cool-white shafts and a hazy night vibe.
    let wide_mie = min(hg_phase(cos_theta, 0.48), 3.0);
    let tight_mie = min(hg_phase(cos_theta, 0.80), 8.0);
    let day_phase = (0.16 * wide_mie + 0.24 * tight_mie) * smoothstep(-0.05, 0.62, cos_theta);
    let night_phase = (0.12 * wide_mie + 0.62 * tight_mie) * smoothstep(-0.08, 0.58, cos_theta);
    let phase = select(night_phase, day_phase, is_day);
    // Keep immediate close-up foreground clear while letting diagonal rays reach across midground water.
    let near_clear = select(smoothstep(1.5, 10.0, distance), smoothstep(2.0, 12.0, distance), is_day);
    let outdoors = mix(0.23, 1.0, smoothstep(0.08, 0.75, frame.eye_light_smooth.y));
    let sky_fill = overworld_sky_radiance(vec3<f32>(0.0, 0.36, 0.0));
    let sky_tint = sky_fill / max(max(sky_fill.r, max(sky_fill.g, sky_fill.b)), 0.01);
    let raw_sun = sun_colour();
    let sun_luma = dot(raw_sun, vec3<f32>(0.2126, 0.7152, 0.0722));
    let low_sun = golden_hour();
    // Keep warm golden shafts at sunrise/sunset and shift toward airy pale cream-gold at higher sun.
    let chroma = mix(0.54, 0.88, low_sun);
    let sunlight = mix(vec3<f32>(sun_luma), raw_sun, chroma) * mix(0.55, 1.0, twilight_daylight());
    // Normal cool silver-white moonlight for luminous nighttime shafts.
    let moonlight = vec3<f32>(0.86, 0.91, 1.0);
    let light = select(moonlight, sunlight, is_day);
    let sky_mix = select(0.05, mix(0.20, 0.06, low_sun), is_day);
    let gain = select(2.60, 2.85, is_day);
    let scatter = mix(light, sky_tint, sky_mix) * integrated * phase * gain * near_clear * outdoors * effects;
    // Ordinary post targets force alpha to 1. Store scattering in RGB only.
    return vec4<f32>(scatter, 1.0);
}
