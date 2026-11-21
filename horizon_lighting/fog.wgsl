override custom_fog: bool = false;
override custom_fog_start: f32 = 24.0;
override custom_fog_density: f32 = 0.012;
override custom_fog_tint: u32 = 0u;
override aerial_perspective: f32 = 0.28;

const AIR_CLEAR_RANGE: f32 = 16.0;
const AIR_BLEND_RANGE: f32 = 80.0;

// Integral of clamp(height, 0, 1), in layer-relative coordinates.
fn air_height_integral(height: f32) -> f32 {
    let ramp = clamp(height, 0.0, 1.0);
    return 0.5 * ramp * ramp + max(height - 1.0, 0.0);
}

fn aerial_opacity(position: vec3<f32>) -> f32 {
    if aerial_perspective <= 0.0 || frame.dimension != 0 || frame.eye_in != 0u {
        return 0.0;
    }
    let effects = clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
    let sky_access = smoothstep(0.20, 0.85, frame.eye_light_smooth.y);
    if sky_access <= 0.0 || effects >= 1.0 { return 0.0; }
    let distance = length(position);
    if distance <= AIR_CLEAR_RANGE { return 0.0; }
    let start_height = (frame.camera_position.y + position.y * (AIR_CLEAR_RANGE / distance)
        - AIR_LAYER_BASE) / AIR_LAYER_HEIGHT;
    let end_height = (frame.camera_position.y + position.y - AIR_LAYER_BASE) / AIR_LAYER_HEIGHT;
    let rise = end_height - start_height;
    var average_height = clamp((start_height + end_height) * 0.5, 0.0, 1.0);
    if abs(rise) > 0.001 && min(start_height, end_height) < 1.0
        && max(start_height, end_height) > 0.0
        && (min(start_height, end_height) < 0.0 || max(start_height, end_height) > 1.0) {
        average_height = (air_height_integral(end_height) - air_height_integral(start_height)) / rise;
    }
    let density = air_density(average_height);
    let path = (distance - AIR_CLEAR_RANGE) * smoothstep(AIR_CLEAR_RANGE, AIR_BLEND_RANGE, distance);
    // Slightly denser cool mist at night for an atmospheric hazy night landscape.
    let night_mist = (1.0 - daylight()) * moonlight_presence();
    let optical_depth = density * path * aerial_perspective * mix(1.0, 1.38, night_mist) * sky_access;
    return (1.0 - exp(-optical_depth)) * (1.0 - effects);
}

fn aerial_radiance(position: vec3<f32>) -> vec3<f32> {
    let direction = safe_direction(position);
    let horizon = vec3<f32>(direction.x, clamp(direction.y, 0.0, 0.14), direction.z);
    let warm_day = 1.0 - smoothstep(0.86, 0.955, frame.sun_direction.y);
    let sunward = pow(max(dot(direction, frame.sun_direction), 0.0), 5.0)
        * sun_presence() * clear_weather() * warm_day;
    let glow = golden_sky_glow(horizon);
    // Keep distant aerial haze airy and translucent rather than a heavy orange fog wall.
    let dome = overworld_sky_dome(horizon, clamp(glow.r * 0.45, 0.0, 1.0));
    let sunlight = sun_colour();
    let sun_luma = dot(sunlight, vec3<f32>(0.2126, 0.7152, 0.0722));
    let airy_sun = mix(vec3<f32>(sun_luma), sunlight, 0.58);
    // Moody cool silver-white hazy mist at night, brightening softly toward the moon
    // while preserving dark night contrast and crisp silhouettes.
    let night_mist = (1.0 - daylight()) * moonlight_presence() * clear_weather();
    let moonward = pow(max(dot(direction, frame.moon_direction), 0.0), 4.0);
    let night_target = vec3<f32>(0.0085, 0.0105, 0.0145) + MOONLIGHT * (0.010 * moonward);
    let base_radiance = mix(dome, night_target, night_mist * 0.85);
    return base_radiance + glow * 0.36 + airy_sun * (0.24 * sunward * twilight_daylight());
}

fn apply_aerial_perspective(colour: vec3<f32>, position: vec3<f32>) -> vec3<f32> {
    let opacity = aerial_opacity(position);
    if opacity <= 0.0 { return colour; }
    return mix(colour, aerial_radiance(position), opacity);
}

fn apply_custom_fog(colour: vec3<f32>, distance: f32) -> vec3<f32> {
    if !custom_fog || frame.dimension != 0 || frame.eye_in != 0u || distance <= custom_fog_start {
        return colour;
    }
    let visible = 1.0 - clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
    let opacity = (1.0 - exp(-custom_fog_density * (distance - custom_fog_start))) * visible;
    var tint = vec3<f32>(0.25, 0.25, 0.25);
    if custom_fog_tint == 1u { tint = vec3<f32>(0.30, 0.25, 0.19); }
    if custom_fog_tint == 2u { tint = vec3<f32>(0.20, 0.25, 0.31); }
    let daylight_level = mix(0.09, 1.0, daylight());
    let sky_access = mix(0.30, 1.0, smoothstep(0.05, 0.80, frame.eye_light_smooth.y));
    return mix(colour, tint * (daylight_level * sky_access), opacity);
}

// Pack-owned fog preserves the water background's haze and lets Overworld air use aerial perspective.
fn surface_fog_factor(position: vec3<f32>) -> f32 {
    let fog = vanilla_fog(position);
    let effects = clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
    return select(fog, fog * effects, frame.dimension == 0 && frame.eye_in == 0u);
}

// Attenuate light added after the surface's air colour has already been resolved.
fn surface_visibility(position: vec3<f32>) -> f32 {
    return (1.0 - surface_fog_factor(position)) * (1.0 - aerial_opacity(position));
}

fn surface_fog(colour: vec3<f32>, position: vec3<f32>) -> vec3<f32> {
    let effects = clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
    var medium = colour;
    if pack_underwater() {
        let transmission = exp(-UNDERWATER_VIEW_EXTINCTION * length(position));
        medium = mix(underwater_haze(), colour, transmission);
        if effects <= 0.0 { return medium; }
    } else {
        medium = apply_aerial_perspective(colour, position);
    }
    let fog = surface_fog_factor(position);
    if fog <= 0.0 { return medium; }
    // Match vanilla's gamma-space fog blend while the pack otherwise works in linear light.
    let base = select(medium, colour, pack_underwater());
    let gamma = pow(max(base, vec3<f32>(0.0)), vec3<f32>(1.0 / 2.2));
    let fog_gamma = pow(max(frame.fog_color, vec3<f32>(0.0)), vec3<f32>(1.0 / 2.2));
    let vanilla = pow(mix(gamma, fog_gamma, fog), vec3<f32>(2.2));
    return select(vanilla, mix(medium, vanilla, effects), pack_underwater());
}
