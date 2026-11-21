override contact_ao: bool = quality_preset >= PRESET_BALANCED;

fn contact_weight(offset: vec3<f32>, normal: vec3<f32>) -> f32 {
    let height = dot(offset, normal);
    return smoothstep(0.018, 0.13, height) * (1.0 - smoothstep(0.24, 0.72, length(offset)));
}

fn post(input: PostInput) -> vec4<f32> {
    let effects = max(frame.night_vision, max(frame.blindness, frame.darkness));
    if !contact_ao || frame.dimension != 0 || frame.eye_in != 0u || input.depth <= 0.0 || effects > 0.0 {
        return vec4<f32>(0.0, 0.0, 0.0, 1.0);
    }
    let position = view_position(input.uv, input.depth);
    let distance = length(position);
    let reach = 1.0 - smoothstep(16.0, 30.0, distance);
    if reach <= 0.0 { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }

    let size = vec2<f32>(textureDimensions(scene_depth));
    let receiver = surface_at(vec2<i32>(input.uv * size));
    if !receiver.present || !receives_contact_ao(receiver.data) {
        return vec4<f32>(0.0, 0.0, 0.0, 1.0);
    }

    // Two interleaved rings stay stable across frames and keep the footprint local.
    let taps = array<vec2<f32>, 8>(
        vec2<f32>(0.26, 0.0), vec2<f32>(-0.26, 0.0), vec2<f32>(0.0, 0.26), vec2<f32>(0.0, -0.26),
        vec2<f32>(0.58, 0.58), vec2<f32>(-0.58, 0.58), vec2<f32>(0.58, -0.58), vec2<f32>(-0.58, -0.58));
    let projection_rows = transpose(frame.projection);
    let lens = vec2<f32>(length(projection_rows[0].xyz), length(projection_rows[1].xyz));
    let step = 0.50 * lens / max(distance, 0.75);
    var contact = 0.0;
    var strongest_contact = 0.0;
    for (var i = 0u; i < 8u; i++) {
        let tap = vec2<i32>(clamp((input.uv + taps[i] * step) * size, vec2<f32>(0.0), size - 1.0));
        let depth = textureLoad(scene_depth, tap, 0);
        if depth <= 0.0 { continue; }
        let uv = (vec2<f32>(tap) + 0.5) / size;
        let weight = contact_weight(view_position(uv, depth) - position, receiver.normal);
        if weight > 0.0 && surface_at(tap).present {
            contact += weight;
            strongest_contact = max(strongest_contact, weight);
        }
    }
    // Keep close-range contact shading clean and natural without smudging block steps.
    let occlusion = min(max(contact * 0.18, strongest_contact * 0.24), 0.36);
    return vec4<f32>(occlusion * reach, distance, 0.0, 1.0);
}
