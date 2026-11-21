// Custom translucent rain streaks and atmospheric snow lit by the pack's sky and local light.
fn weather(input: WeatherInput) -> vec4<f32> {
    if input.color.a <= 0.001 {
        return vec4<f32>(0.0);
    }
    if !uses_pack_lighting() {
        return input.color;
    }

    let dist = length(input.position);
    let view = safe_direction(input.position);
    let sky_level = clamp(input.light.y, 0.0, 1.0);
    let sky_access = sky_level * sky_level;
    let block_level = clamp(input.light.x, 0.0, 1.0);
    let block_access = block_level * block_level;

    // Sample the pack's overcast/twilight sky and celestial lighting so precipitation matches the world.
    let sky_sample = overworld_sky_radiance(vec3<f32>(view.x, max(view.y, 0.12), view.z));
    let sun_lit = sun_colour() * sun_presence() * twilight_daylight() * mix(0.28, 0.72, clear_weather());
    let moon_lit = moonlight_colour() * (1.0 - sun_presence());
    let sky_env = (sky_sample * 1.15 + sun_lit * 0.45 + moon_lit * 1.35) * sky_access;
    // Warm amber catch-light near torches, lanterns, and lit windows.
    let block_env = vec3<f32>(1.05, 0.68, 0.32) * (block_access * 0.72);
    let floor_env = vec3<f32>(0.015, 0.018, 0.024) * (0.65 + 0.55 * frame.brightness);
    let env_light = sky_env + block_env + floor_env;

    let effects = clamp(max(frame.night_vision, max(frame.blindness, frame.darkness)), 0.0, 1.0);

    if input.snow {
        // Keep snowflakes soft, clean, and lit by sky, sunset, moonlight, and nearby torches.
        let flake_luma = max(dot(input.color.rgb, vec3<f32>(0.2126, 0.7152, 0.0722)), 0.001);
        let snow_rgb = mix(env_light * 1.25, input.color.rgb, effects);
        let near_fade = smoothstep(0.45, 1.4, dist);
        let alpha = clamp(input.color.a * 0.85 * near_fade * smoothstep(0.02, 0.25, flake_luma), 0.0, 0.88);
        return vec4<f32>(max(snow_rgb, vec3<f32>(0.0)), alpha);
    }

    // Rain: strip vanilla's saturated blue tint and render translucent, silver-clear water streaks.
    let streak_detail = clamp(dot(input.color.rgb, vec3<f32>(0.25, 0.45, 0.30)) * 2.2, 0.35, 1.15);
    let env_luma = dot(env_light, vec3<f32>(0.2126, 0.7152, 0.0722));
    // Mostly neutral translucent water with a subtle tint from the sky, sun, and nearby block light.
    let neutral_water = mix(vec3<f32>(env_luma), env_light, 0.32) * vec3<f32>(0.96, 0.98, 1.01);
    // Subtle specular glint when looking toward the sun or moon through rain.
    let forward = max(dot(view, celestial_direction()), 0.0);
    let glint = pow(forward, 6.0) * (sun_lit * 0.35 + moon_lit * 0.55) * sky_access;
    let rain_rgb = mix((neutral_water + glint) * (0.90 + 0.30 * streak_detail), input.color.rgb, effects);

    // Keep rain airy and transparent: soften streaks right in front of the camera and far away.
    let near_fade = smoothstep(0.65, 2.1, dist);
    let far_fade = mix(1.0, 0.55, smoothstep(18.0, 42.0, dist));
    let alpha = clamp(input.color.a * 0.36 * streak_detail * near_fade * far_fade, 0.0, 0.38);
    return vec4<f32>(max(rain_rgb, vec3<f32>(0.0)), alpha);
}
