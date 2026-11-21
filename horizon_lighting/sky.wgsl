struct CloudViewRay {
    origin: vec3<f32>,
    direction: vec3<f32>,
}

fn cloud_view_ray(unbobbed: vec3<f32>) -> CloudViewRay {
    // Horizon sends an unbobbed direction to the sky stage. Frame.projection also
    // includes the world pose. Recover the lens scale from its rotated row lengths.
    let rows = transpose(frame.projection);
    let lens = vec2<f32>(length(rows[0].xyz), length(rows[1].xyz));
    let eye_h = frame.projection_inverse[2];
    if min(lens.x, lens.y) <= 0.0001 || abs(eye_h.w) <= 0.0001 {
        return CloudViewRay(frame.camera_position, unbobbed);
    }
    let view_ray = (frame.view * vec4<f32>(unbobbed, 0.0)).xyz;
    let ndc = view_ray.xy * lens / max(-view_ray.z, 0.0001);
    let eye = eye_h.xyz / eye_h.w;
    let far = frame.projection_inverse * vec4<f32>(ndc, 0.0, 1.0);
    let direction = frame.view_inverse * vec4<f32>(far.xyz - eye * far.w, 0.0);
    let origin = (frame.view_inverse * vec4<f32>(eye, 1.0)).xyz + frame.camera_position;
    return CloudViewRay(origin, safe_direction(direction.xyz));
}

fn sky(input: SkyInput) -> vec4<f32> {
    if frame.dimension != 0 || frame.eye_in != 0u { return input.color; }
    let engine_sky = input.color.rgb;
    let sky_model = overworld_sky_radiance(input.direction);
    let effects = clamp(max(frame.darkness, frame.blindness), 0.0, 1.0);
    let twilight = smoothstep(-0.20, -0.08, frame.sun_direction.y) * (1.0 - twilight_daylight());
    let model_weight = mix(mix(0.30, 0.72, daylight()), 1.0, max(twilight, overcast_weight())) * (1.0 - effects);
    let cloud_ray = cloud_view_ray(input.direction);
    let analytic = mix(engine_sky * (1.0 - twilight * (1.0 - effects)), sky_model, model_weight)
        + solar_disk_and_glare(cloud_ray.direction) * (1.0 - effects);
    if !procedural_clouds || effects >= 1.0 { return vec4<f32>(analytic, input.color.a); }
    return vec4<f32>(clouded_sky(analytic, cloud_ray.origin, cloud_ray.direction, 1.0 - effects), input.color.a);
}

fn solar_disk_and_glare(direction: vec3<f32>) -> vec3<f32> {
    let horizon = smoothstep(-0.017, 0.028, frame.sun_direction.y);
    let alignment = dot(direction, frame.sun_direction);
    if alignment < 0.88 || horizon <= 0.0 { return vec3<f32>(0.0); }
    // A smooth angular profile carries the bright core into the surrounding glare.
    let radius_squared = max(2.0 * (1.0 - alignment), 0.0);
    let core = 12.0 * exp(-1000.0 * radius_squared);
    let fringe = 3.2 * exp(-180.0 * radius_squared);
    let halo = 0.85 * exp(-40.0 * radius_squared) * smoothstep(0.88, 0.95, alignment);
    let warm = sun_colour();
    let core_colour = mix(vec3<f32>(1.0), warm, 0.58);
    let halo_colour = mix(warm, twilight_sun_colour(), 0.35);
    return (core_colour * core + warm * fringe + halo_colour * halo)
        * horizon * mix(0.28, 1.0, twilight_daylight());
}
