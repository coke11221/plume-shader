override foliage_wind: bool = quality_preset >= PRESET_BALANCED;
override wind_strength: f32 = 1.0;

const WIND_TAU: f32 = 6.2831853;

// Integer cycles per hour guarantee exact continuity across Frame.time's 3600s wrap
// while keeping trig inputs bounded to [0, 2*pi) for full f32 precision.
fn wind_phase(cycles_per_hour: f32) -> f32 {
    return fract(fract(frame.time / 3600.0) * cycles_per_hour) * WIND_TAU;
}

fn vertex(input: VertexInput) -> vec3<f32> {
    let mat = input.material;
    // Fast path for >95% of terrain vertices (stone, dirt, wood, grass blocks, water, flat overlays).
    if !foliage_wind || wind_strength <= 0.0 || mat < 40u || mat == 41u || (mat > 46u && mat != 48u) {
        return input.position;
    }

    // Squared-distance cutoff avoids sqrt() and skips sub-pixel distant foliage.
    let dist_sq = dot(input.position, input.position);
    if dist_sq >= 9216.0 {
        return input.position;
    }
    let dist_fade = 1.0 - smoothstep(4096.0, 9216.0, dist_sq);
    let world = input.position + frame.camera_position;

    // Underwater aquatic plants (45 rooted seagrass/coral, 46 upper tall seagrass/kelp)
    // drift in slow water currents independent of surface weather or skylight.
    // Constant weight 1.0 on mat 46 matches mat 45's top (uv.y = 0) and keeps tall kelp stacks seamless.
    if mat == 45u || mat == 46u {
        let aquatic_w = select(1.0, clamp(1.0 - input.uv.y, 0.0, 1.0), mat == 45u);
        if aquatic_w <= 0.001 {
            return input.position;
        }
        let p_water = wind_phase(720.0); // ~1.26 rad/s gentle underwater current
        let wave_x = sin(p_water + world.x * 0.55 + world.y * 0.40 + world.z * 0.35);
        let wave_z = cos(p_water + world.z * 0.50 - world.x * 0.30 + world.y * 0.35);
        let scale = 0.055 * wind_strength * dist_fade * aquatic_w;
        return input.position + vec3<f32>(wave_x * scale, 0.0, wave_z * scale);
    }

    // Ground-rooted plants stay anchored at their base (uv.y = 1.0) so they never float.
    var weight = 1.0;
    if mat == 40u {
        weight = clamp(1.0 - input.uv.y, 0.0, 1.0);
        if weight <= 0.001 {
            return input.position;
        }
    } else if mat == 43u {
        // Upper half of two-block plants matches mat 40's top weight (1.0) at uv.y = 1.0
        // so tall grass, ferns and tall flowers never tear at the block boundary.
        weight = 1.0 + 0.60 * clamp(1.0 - input.uv.y, 0.0, 1.0);
    }

    // Shelter caves and interiors from surface wind and rain gusts using baked skylight.
    var outdoor = smoothstep(0.06, 0.72, input.light.y);
    var calm_exposure = mix(0.14, 1.0, outdoor);
    var rain_wind = 0.0;
    if frame.dimension == 0 {
        let storm = clamp(frame.rain + 0.35 * frame.thunder, 0.0, 1.0);
        rain_wind = storm * outdoor;
    } else if frame.dimension == -1 {
        // Gentle thermal drift for Nether roots and vines.
        calm_exposure = 0.45;
    } else {
        calm_exposure = 0.35;
    }

    // Dual-frequency harmonic crossfade varies wind speed cleanly between clear weather and rain
    // with zero phase jumps during weather transitions at any Frame.time.
    let p_calm = wind_phase(1032.0); // ~1.80 rad/s calm breeze
    let p_gust = wind_phase(430.0);  // ~0.75 rad/s slow rolling gust envelope
    let gust_coord = world.x * 0.14 - world.z * 0.11;
    let calm_gust = 0.72 + 0.28 * sin(p_gust + gust_coord);

    let calm_phase_x = p_calm + world.x * 0.65 + world.z * 0.35 + world.y * 0.25;
    let calm_phase_z = p_calm + world.z * 0.60 - world.x * 0.30 + 1.1;
    let calm_xz = vec2<f32>(sin(calm_phase_x) * 0.055, cos(calm_phase_z) * 0.038)
        * (calm_gust * calm_exposure);

    var sway_xz = calm_xz;
    var flutter_y = 0.0;
    if mat == 42u {
        flutter_y = sin(calm_phase_x + 0.7) * 0.016 * calm_gust * calm_exposure;
    }

    if rain_wind > 0.001 {
        let p_storm = wind_phase(2406.0);   // ~4.20 rad/s brisk rainy wind (~2.33x faster)
        let p_flutter = wind_phase(3724.0); // ~6.50 rad/s lively storm flutter
        let storm_gust = 0.65 + 0.35 * sin(p_gust * 2.0 + gust_coord * 1.6);
        let storm_px = p_storm + world.x * 0.85 + world.z * 0.45 + world.y * 0.35;
        let storm_pz = p_storm + world.z * 0.80 - world.x * 0.40 + 0.8;
        let flutter_p = p_flutter + world.x * 1.8 - world.z * 1.4;
        // Stronger directional lean aligned with cloud drift (+X, -Z) and wider vigorous gusting in rain.
        let storm_xz = vec2<f32>(
            0.075 + sin(storm_px) * 0.185 + sin(flutter_p) * 0.036,
            -0.052 + cos(storm_pz) * 0.145 + cos(flutter_p + 0.9) * 0.028
        ) * storm_gust;
        sway_xz = mix(calm_xz, storm_xz, rain_wind);
        if mat == 42u {
            let storm_y = (sin(storm_px + 0.7) * 0.048 + sin(flutter_p) * 0.018) * storm_gust;
            flutter_y = mix(flutter_y, storm_y, rain_wind);
        }
    }

    // Leaves (42) and hanging vines/bamboo stalks & leaves (44, 48) use slightly tighter amplitude
    // in calm weather and open up further during rain gusts, keeping stalks and leaves in lockstep.
    let multi_stalk = mat == 44u || mat == 48u;
    let base_kind_scale = select(1.0, select(0.58, 0.62, multi_stalk), mat == 42u || multi_stalk);
    let kind_scale = mix(base_kind_scale, min(base_kind_scale * 1.25, 1.0), rain_wind);
    let final_scale = wind_strength * dist_fade * weight * kind_scale;
    let disp_xz = sway_xz * final_scale;
    // Slight arc droop when blades bend, or subtle vertical leaf rustle.
    let disp_y = select(-0.42 * dot(disp_xz, disp_xz), flutter_y * wind_strength * dist_fade * kind_scale, mat == 42u);
    return input.position + vec3<f32>(disp_xz.x, disp_y, disp_xz.y);
}
