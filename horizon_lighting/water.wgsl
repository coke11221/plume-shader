// Sky-lit water uses its own directional wave normal map; cave water blends the animated default texture.
override reflections: bool = true;
override water_ripples: f32 = 1.0;
override water_speed: f32 = 2.0;
override water_clarity: f32 = 1.0;

const WATER_ABSORPTION: vec3<f32> = vec3<f32>(0.34, 0.095, 0.036);
const AQUATIC_WATER_SCATTER: vec3<f32> = vec3<f32>(0.016, 0.165, 0.33);
const WATER_SHEET_COLOUR: vec3<f32> = vec3<f32>(0.004, 0.011, 0.016);
const WATER_AIR_IOR_RATIO: f32 = 1.0 / 1.333;

fn water_normal_slope(uv: vec2<f32>) -> vec2<f32> {
    let normal = textureSampleLevel(water_normal, water_normal_sampler, uv, 0.0).xyz * 2.0 - 1.0;
    return normal.xy / max(normal.z, 0.001);
}

fn water_ripple_slope(position: vec2<f32>, seconds: f32, footprint: f32) -> vec2<f32> {
    if water_ripples <= 0.0 { return vec2<f32>(0.0); }
    let swell_scale = 0.0425;
    let broad_scale = 0.085;
    let detail_scale = 0.17;
    let cross_scale = detail_scale * 1.25;

    // Per-octave band-limiting: finer ripples fade out gently first while broader waves
    // and long-wavelength swells smoothly carry motion across wide lakes and oceans.
    let w_cross = 1.0 - smoothstep(0.040, 0.185, footprint * cross_scale);
    let w_detail = 1.0 - smoothstep(0.048, 0.215, footprint * detail_scale);
    let w_broad = 1.0 - smoothstep(0.055, 0.210, footprint * broad_scale);
    let w_swell = 1.0 - smoothstep(0.045, 0.122, footprint * swell_scale);
    if w_swell <= 0.0 && w_broad <= 0.0 && w_detail <= 0.0 && w_cross <= 0.0 {
        return vec2<f32>(0.0);
    }

    // Whole tile traversals keep all layers continuous across the hourly wrap while
    // matching equal-and-opposite world drift velocities across oblique angles.
    let phase = round(vec2<f32>(36.0, 12.0) * water_speed) * (seconds / 3600.0);
    var combined = vec2<f32>(0.0);

    if w_swell > 0.0 {
        let swell = water_normal_slope(vec2<f32>(position.y, position.x) * swell_scale
            + vec2<f32>(0.19, 0.53) + fract(vec2<f32>(phase.y, phase.x)));
        combined += swell.yx * (0.34 * w_swell);
    }
    if w_broad > 0.0 {
        let forward_broad = water_normal_slope(position * broad_scale - fract(2.0 * phase));
        combined += forward_broad * (0.56 * w_broad);
    }
    if w_detail > 0.0 {
        let forward_detail = water_normal_slope(vec2<f32>(position.y, position.x) * detail_scale
            + vec2<f32>(0.41, 0.73) - fract(4.0 * vec2<f32>(phase.y, phase.x)));
        combined += forward_detail.yx * (0.36 * w_detail);
    }
    if w_cross > 0.0 {
        let rotated = vec2<f32>(0.6 * position.x - 0.8 * position.y,
            0.8 * position.x + 0.6 * position.y);
        let cross_phase = vec2<f32>(3.0 * phase.x - 4.0 * phase.y, 4.0 * phase.x + 3.0 * phase.y);
        let cross_uv = rotated * cross_scale + vec2<f32>(0.37, 0.61) + fract(cross_phase);
        let cross_sample = water_normal_slope(cross_uv);
        let backward = vec2<f32>(0.6 * cross_sample.x + 0.8 * cross_sample.y,
            -0.8 * cross_sample.x + 0.6 * cross_sample.y);
        combined += backward * (0.56 * w_cross);
    }

    return combined * (0.64 * water_ripples);
}

fn water_texel(uv: vec2<f32>) -> vec2<i32> {
    let size = vec2<i32>(textureDimensions(opaque_color));
    return clamp(vec2<i32>(uv * vec2<f32>(size)), vec2<i32>(0), size - 1);
}

fn water_plane_distance(direction: vec3<f32>, position: vec3<f32>, normal: vec3<f32>) -> f32 {
    let denominator = dot(direction, normal);
    if abs(denominator) < 0.0001 { return length(position); }
    return max(dot(position, normal) / denominator, 0.0);
}

fn water_background_is_foreground(background: vec3<f32>, position: vec3<f32>, normal: vec3<f32>) -> bool {
    return dot(background - position, normal) > 0.015;
}

fn water_column(behind: vec3<f32>, position: vec3<f32>, normal: vec3<f32>) -> f32 {
    let interface_distance = water_plane_distance(safe_direction(behind), position, normal);
    return clamp(length(behind) - interface_distance, 0.0, 32.0);
}

fn water_environment(fallback: vec3<f32>, mirror: vec3<f32>, mirror_weight: f32,
                     world: vec3<f32>, direction: vec3<f32>) -> vec3<f32> {
    let base = mix(fallback, mirror, mirror_weight);
    if !procedural_clouds || frame.dimension != 0 || direction.y <= 0.0 {
        return base;
    }
    var strength = 1.0 - mirror_weight;
    if mirror_weight > 0.0 {
        // API 0.2 exposes only mirror color. Treat colors near the native sky-to-fog
        // gradient as sky and retain the mirror's terrain outside that narrow band.
        let sky = sqrt(max(frame.sky_color, vec3<f32>(0.0)));
        let fog = sqrt(max(frame.fog_color, vec3<f32>(0.0)));
        let sample = sqrt(max(mirror, vec3<f32>(0.0)));
        let gradient = fog - sky;
        let blend = clamp(dot(sample - sky, gradient) / max(dot(gradient, gradient), 0.00001), 0.0, 1.0);
        let error = length(sample - mix(sky, fog, blend));
        strength += mirror_weight * (1.0 - smoothstep(0.014, 0.042, error));
    }
    let cloud_steps = select(select(6u, 5u, quality_preset == PRESET_HIGH), 4u,
        quality_preset <= PRESET_BALANCED);
    return clouded_environment(base, world, direction, strength, cloud_steps);
}

fn water_depth_tint(background: vec3<f32>, thickness: f32, sky_access: f32,
                    water_shadow: f32, position: vec3<f32>) -> vec3<f32> {
    let absorption = max(1.0 / water_clarity - 0.25, 0.0);
    let optical_depth = thickness * absorption;
    var colour = background * exp(-WATER_ABSORPTION * optical_depth);
    if optical_depth > 0.0 && sky_access > 0.0 {
        let scatter_amount = (1.0 - exp(-0.22 * optical_depth)) * sky_access;
        let sun_shade = mix(0.45, 1.0, water_shadow);
        let aquatic_day = (0.32 + 0.68 * sun_shade * clear_weather())
            * sun_colour() * twilight_daylight() * daylight();
        let aquatic_night = vec3<f32>(0.18, 0.28, 0.42) * max(night_brightness, 0.10);
        let aquatic_light = mix(aquatic_night, aquatic_day, daylight());
        let volume_colour = AQUATIC_WATER_SCATTER * aquatic_light;
        colour = mix(colour, volume_colour, scatter_amount * 0.82 * surface_visibility(position));
    }
    return colour;
}

fn water_local_light(input: MaterialInput) -> vec3<f32> {
    return local_surface_light(input.position, input.light.x, input.colored_light);
}

fn cave_water_texture(input: MaterialInput, world: vec3<f32>, vertical: bool) -> vec3<f32> {
    let tex_peak = max(input.albedo.r, max(input.albedo.g, input.albedo.b));
    // Isolate the bright ripple/flow lines in the default water texture without blue biome tint.
    let line_mask = smoothstep(0.42, 0.80, tex_peak);
    if line_mask <= 0.0 { return vec3<f32>(0.0); }
    let local = water_local_light(input);
    let light = vec3<f32>(0.23) + vec3<f32>(0.25) * input.light.x + local * 0.85;
    let flow_coord = select(world.xz * 0.24 + vec2<f32>(0.0, frame.time * 0.35 * water_speed),
        vec2<f32>(world.x + world.z, world.y * 0.70 + frame.time * 1.15 * water_speed) * 0.32,
        vertical);
    let ripple = water_normal_slope(flow_coord);
    let shimmer = 0.75 + 0.55 * clamp(ripple.x + ripple.y + 0.40, 0.0, 1.0);
    return vec3<f32>(0.94, 0.96, 0.98) * (line_mask * light * shimmer);
}

fn shade_water(input: MaterialInput) -> Surface {
    let geometric = input.normal;
    let view = safe_direction(-input.position);
    let facing = clamp(dot(view, geometric), 0.0, 1.0);
    var sky_access = 0.0;
    if frame.dimension == 0 {
        sky_access = smoothstep(0.28, 0.92, input.light.y);
    }
    let cave = 1.0 - sky_access;
    let world = input.position + frame.camera_position;
    if input.face != 1u {
        let grazing = pow(1.0 - facing, 2.0);
        var opacity = mix(0.28, 0.16, sky_access) + 0.22 * grazing;
        let local = min(water_local_light(input) * 0.12, vec3<f32>(0.08));
        var sheet = WATER_SHEET_COLOUR * mix(1.0, 2.4, sky_access) + local * (0.32 + 0.68 * grazing);
        if cave > 0.0 && input.face != 0u {
            let cave_lines = cave_water_texture(input, world, true);
            let line_strength = max(cave_lines.r, max(cave_lines.g, cave_lines.b));
            sheet += cave_lines * cave;
            opacity = min(opacity + line_strength * cave * 1.2, 0.82);
        }
        let coverage = select(opacity, 0.4 * opacity, input.face == 0u);
        return Surface(vec4<f32>(surface_fog(sheet, input.position), coverage));
    }
    if frame.eye_in != 0u || geometric.y <= 0.0 {
        // Immersion fog is already in the scene. Leave previously blended surfaces intact.
        return Surface(vec4<f32>(0.0));
    }

    let original_uv = input.screen;
    let original_texel = water_texel(original_uv);
    let distance = length(input.position);
    // Use an anisotropic-aware projected footprint so oblique lake views keep smooth multi-scale waves
    // far past the shore, tapering gently into flat distant water without an abrupt cutoff.
    let focal_pixels = max(frame.resolution.y * abs(frame.projection[1].y) * 0.5, 1.0);
    let footprint = distance / (focal_pixels * pow(max(facing, 0.04), 0.52));
    let dist_fade = exp(-max(distance - 18.0, 0.0) * 0.008) * (1.0 - smoothstep(130.0, 260.0, distance));
    let grazing_damp = mix(0.45, 1.0, smoothstep(0.015, 0.18, facing));
    let slope = water_ripple_slope(world.xz, frame.time, footprint)
        * mix(0.75, 1.0 + 0.3 * frame.rain, sky_access)
        * dist_fade * grazing_damp;
    let normal = safe_direction(geometric + vec3<f32>(slope.x, 0.0, slope.y) * geometric.y);
    let edge = min(min(original_uv.x, 1.0 - original_uv.x), min(original_uv.y, 1.0 - original_uv.y));
    let screen_fade = smoothstep(0.002, 0.06, edge);
    let depth = textureLoad(opaque_depth, original_texel, 0);
    var refracted_texel = original_texel;
    var thickness = 0.0;
    if depth > 0.0 {
        thickness = water_column(position_from_depth(original_uv, depth), input.position, geometric);
        let flat_ray = refract(-view, geometric, WATER_AIR_IOR_RATIO);
        let wave_ray = refract(-view, normal, WATER_AIR_IOR_RATIO);
        let view_offset = (frame.view * vec4<f32>(wave_ray - flat_ray, 0.0)).xy;
        let refracted_uv = original_uv + view_offset * vec2<f32>(0.070, -0.070)
            * smoothstep(0.0, 3.0, thickness) * screen_fade;
        let candidate = water_texel(refracted_uv);
        let refracted_depth = textureLoad(opaque_depth, candidate, 0);
        if refracted_depth > 0.0 {
            let behind = position_from_depth(refracted_uv, refracted_depth);
            if !water_background_is_foreground(behind, input.position, geometric) {
                refracted_texel = candidate;
                thickness = water_column(behind, input.position, geometric);
            }
        }
    }
    let water_shadow = select(1.0, shadow_visibility(input.position, geometric), sky_access > 0.0);
    var colour = water_depth_tint(textureLoad(opaque_color, refracted_texel, 0).rgb,
        thickness, sky_access, water_shadow, input.position);
    // A sheltered interface keeps its dark clear look while lighting up the animated water lines
    // so cave sources and flowing streams remain readable without a blue fill.
    let sheltered_reflection = 0.12 + 0.30 * pow(1.0 - clamp(dot(view, normal), 0.0, 1.0), 1.7);
    if sky_access < 1.0 {
        let reflected_local = min(water_local_light(input) * 0.075, vec3<f32>(0.036));
        let background_peak = max(colour.r, max(colour.g, colour.b));
        let dark_interface = (1.0 - smoothstep(0.008, 0.07, background_peak)) * (0.24 + sheltered_reflection);
        colour = mix(colour, colour * (1.0 - sheltered_reflection)
            + reflected_local * (0.45 + sheltered_reflection) + WATER_SHEET_COLOUR * dark_interface, cave);
        let flow_slope = smoothstep(0.99, 0.85, geometric.y);
        let cave_lines = cave_water_texture(input, world, flow_slope > 0.25);
        let crest = 0.88 + 0.38 * clamp(slope.x + slope.y, -0.35, 0.75);
        colour += cave_lines * (cave * crest * (1.0 + 0.45 * flow_slope));
    }
    if sky_access <= 0.0 { return Surface(vec4<f32>(colour, 1.0)); }

    let reflected_direction = reflect(-view, normal);
    let above_horizon = smoothstep(-0.10, 0.14, reflected_direction.y);
    let plane_match = (1.0 - smoothstep(0.08, 0.35, abs(world.y - frame.water_plane)))
        * smoothstep(0.94, 0.995, geometric.y);
    let mirror_weight = select(0.0, plane_match, reflections && frame.has_reflection == 1u);
    var mirrored = vec3<f32>(0.0);
    if mirror_weight > 0.0 {
        let ripple_uv = (frame.view * vec4<f32>(normal - geometric, 0.0)).xy;
        let mirror_uv = clamp(original_uv + ripple_uv * vec2<f32>(0.075, -0.075) * screen_fade,
            vec2<f32>(0.001), vec2<f32>(0.999));
        mirrored = textureSampleLevel(reflection, reflection_sampler, mirror_uv, 0.0).rgb;
    }
    let seen = water_environment(environment_sky(reflected_direction), mirrored, mirror_weight,
        world, reflected_direction);
    let fresnel = 0.0204 + 0.9796 * pow(1.0 - clamp(dot(view, normal), 0.0, 1.0), 5.0);
    let reflected_visibility = sky_access * mix(above_horizon, 1.0, mirror_weight);
    colour = mix(colour, surface_fog(seen, input.position), fresnel * reflected_visibility);
    let alignment = max(dot(reflected_direction, frame.light_direction), 0.0);
    let glint = 0.28 * pow(alignment, 48.0) + 0.95 * pow(alignment, 256.0);
    let light_colour = mix(moonlight_colour(),
        sun_colour() * sunlight_strength, sun_presence());
    colour += light_colour * glint * celestial_weather() * sky_access * max(dot(normal, frame.light_direction), 0.0)
        * water_shadow * surface_visibility(input.position)
        * cloud_light_transmission(input.position, celestial_direction());
    // Background/refraction is already included. Alpha 1 avoids blending it twice.
    return Surface(vec4<f32>(max(colour, vec3<f32>(0.0)), 1.0));
}
