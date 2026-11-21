override surface_reflections: bool = quality_preset >= PRESET_BALANCED;
override reflection_steps: i32 = select(select(24, 18, quality_preset == PRESET_HIGH), 12,
    quality_preset <= PRESET_BALANCED);

const REFLECTION_REACH: f32 = 24.0;

fn reflection_uv(position: vec3<f32>) -> vec3<f32> {
    let clip = frame.projection * frame.view * vec4<f32>(position, 1.0);
    if clip.w <= 0.001 { return vec3<f32>(-1.0); }
    return vec3<f32>(clip.x / clip.w * 0.5 + 0.5, 0.5 - clip.y / clip.w * 0.5, clip.z / clip.w);
}

fn reflection_pixel(uv: vec2<f32>) -> vec2<i32> {
    let size = vec2<i32>(textureDimensions(scene_depth));
    return clamp(vec2<i32>(uv * vec2<f32>(size)), vec2<i32>(0), size - 1);
}

fn reflected_colour(uv: vec2<f32>, roughness: f32, travel: f32) -> vec3<f32> {
    let texel = 1.0 / vec2<f32>(textureDimensions(scene_color));
    let radius = texel * roughness * min(travel, 12.0) * 1.5;
    var c = textureSampleLevel(scene_color, linear_sampler, uv, 0.0).rgb * 0.4;
    c += textureSampleLevel(scene_color, linear_sampler, uv + vec2<f32>(radius.x, 0.0), 0.0).rgb * 0.15;
    c += textureSampleLevel(scene_color, linear_sampler, uv - vec2<f32>(radius.x, 0.0), 0.0).rgb * 0.15;
    c += textureSampleLevel(scene_color, linear_sampler, uv + vec2<f32>(0.0, radius.y), 0.0).rgb * 0.15;
    c += textureSampleLevel(scene_color, linear_sampler, uv - vec2<f32>(0.0, radius.y), 0.0).rgb * 0.15;
    return c;
}

fn post(input: PostInput) -> vec4<f32> {
    if !surface_reflections || gloss_strength <= 0.0 || !uses_pack_lighting()
        || frame.eye_in != 0u || max(frame.night_vision, max(frame.blindness, frame.darkness)) > 0.01 {
        return vec4<f32>(0.0, 0.0, 0.0, 1.0);
    }
    let surface = surface_at(reflection_pixel(input.uv));
    if !surface.present || surface.smoothness <= 0.0 || input.depth <= 0.0 {
        return vec4<f32>(0.0, 0.0, 0.0, 1.0);
    }
    let position = view_position(input.uv, input.depth);
    let view = safe_direction(-position);
    let direction = reflect(-view, surface.normal);
    let origin = position + surface.normal * 0.045;
    let world = frame.camera_position + origin;
    var seen = vec3<f32>(0.0);
    if frame.dimension == 0 {
        if surface.data < 0.0 {
            // The material already checked skylight. Broad ground bounce still reaches wet sides.
            let sky = smoothstep(-0.10, 0.08, direction.y);
            let ambient = clouded_environment(overworld_sky_radiance(direction), world, direction, 1.0, 4u);
            seen = ambient * mix(0.32, 0.8, sky);
        } else {
            let base = textureSampleLevel(scene_color, linear_sampler, input.uv, 0.0).rgb;
            // Dry polished surfaces have no sky visibility flag; approximate it from scene light.
            let sky_access = clamp(max(base.r, max(base.g, base.b)) * 3.0, 0.0, 1.0);
            let ambient = clouded_environment(environment_sky(direction), world, direction, 1.0, 4u);
            seen = ambient * sky_access * smoothstep(-0.08, 0.35, direction.y);
        }
    }
    var previous_travel = 0.08;
    var previous_delta = -1.0;
    for (var i = 0; i < reflection_steps; i++) {
        let fraction = f32(i + 1) / f32(reflection_steps);
        let travel = 0.12 + REFLECTION_REACH * fraction * fraction;
        let ray = origin + direction * travel;
        let projected = reflection_uv(ray);
        if projected.z <= 0.0 || projected.z > 1.0
            || any(projected.xy <= vec2<f32>(0.002)) || any(projected.xy >= vec2<f32>(0.998)) { break; }
        let depth = depth_at(projected.xy);
        if depth <= 0.0 { previous_delta = -1.0; previous_travel = travel; continue; }
        let scene = view_position(projected.xy, depth);
        let delta = (frame.view * vec4<f32>(scene - ray, 0.0)).z;
        let separation = length(projected.xy - input.uv);
        if delta > 0.0 && previous_delta <= 0.0
            && separation > 2.0 / min(frame.resolution.x, frame.resolution.y) {
            // Refine the front-to-back crossing; never turn an arbitrary occluder into a hit.
            var low = previous_travel;
            var high = travel;
            var hit_uv = projected.xy;
            for (var refine = 0; refine < 4; refine++) {
                let mid = (low + high) * 0.5;
                let point = origin + direction * mid;
                let uv = reflection_uv(point).xy;
                let d = depth_at(uv);
                let gap = (frame.view * vec4<f32>(view_position(uv, max(d, 0.000001)) - point, 0.0)).z;
                if d > 0.0 && gap > 0.0 { high = mid; hit_uv = uv; } else { low = mid; }
            }
            let hit_point = origin + direction * high;
            let hit_projection = reflection_uv(hit_point);
            let hit_depth = depth_at(hit_projection.xy);
            let hit_scene = view_position(hit_projection.xy, max(hit_depth, 0.000001));
            let residual = (frame.view * vec4<f32>(hit_scene - hit_point, 0.0)).z;
            if hit_depth <= 0.0 || hit_projection.z <= 0.0 || hit_projection.z > 1.0
                || any(hit_projection.xy <= vec2<f32>(0.002)) || any(hit_projection.xy >= vec2<f32>(0.998))
                || residual < 0.0 || residual > 0.15 + high * 0.025
                || length(hit_projection.xy - input.uv) <= 2.0 / min(frame.resolution.x, frame.resolution.y) {
                previous_delta = delta; previous_travel = travel; continue;
            }
            hit_uv = hit_projection.xy;
            let edge = min(min(hit_uv.x, 1.0 - hit_uv.x), min(hit_uv.y, 1.0 - hit_uv.y));
            let confidence = smoothstep(0.015, 0.09, edge) * (1.0 - smoothstep(18.0, REFLECTION_REACH, travel));
            seen = mix(seen, reflected_colour(hit_uv, 1.0 - surface.smoothness, travel), confidence);
            break;
        }
        previous_delta = delta;
        previous_travel = travel;
    }
    // Store radiance only. Full-resolution composition applies each receiver's F0,
    // avoiding holes where neighbouring texture texels have different metal colours.
    return vec4<f32>(max(seen, vec3<f32>(0.0)), 1.0);
}
