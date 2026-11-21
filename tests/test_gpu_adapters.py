"""Execute production WGSL adapters on a GPU, isolating the lighting integrator.

Independent expectations follow the API's vanilla entity formula and unchanged
texture/tint transfer. Optional: pip install wgpu, or use .tools/pythonlibs.
"""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools" / "pythonlibs"))
AVAILABLE = importlib.util.find_spec("wgpu") is not None
if AVAILABLE:
    import wgpu
    AVAILABLE = hasattr(wgpu, "gpu")

FRAME = """
struct Frame {
    dimension: i32, camera_position: vec3<f32>, time: f32, water_plane: f32,
    has_reflection: u32, eye_in: u32, light_direction: vec3<f32>,
    sun_direction: vec3<f32>, moon_direction: vec3<f32>, rain: f32, thunder: f32,
    night_vision: f32, blindness: f32, darkness: f32,
    view: mat4x4<f32>, projection_inverse: mat4x4<f32>, view_inverse: mat4x4<f32>,
    sky_color: vec3<f32>, fog_color: vec3<f32>,
    fog_environment: vec2<f32>, fog_render: vec2<f32>, render_distance: f32, brightness: f32,
    resolution: vec2<f32>, projection: mat4x4<f32>, eye_light_smooth: vec2<f32>, headroom: f32,
    shadow_view_proj: mat4x4<f32>, has_shadow: u32, shadow_distance: f32,
    shadow_resolution: f32, shadow_center_texel: f32, shadow_distortion: f32,
}
var<private> frame: Frame;
fn vanilla_fog(position: vec3<f32>) -> f32 {
    let d = vec2<f32>(length(position), max(length(position.xz), abs(position.y)));
    let start = vec2<f32>(frame.fog_environment.x, frame.fog_render.x);
    let end = vec2<f32>(frame.fog_environment.y, frame.fog_render.y);
    let ramp = select((d - start) / (end - start), vec2<f32>(1.0), d >= end);
    let f = select(ramp, vec2<f32>(0.0), d <= start);
    return max(f.x, f.y);
}
@group(0) @binding(0) var<storage, read_write> output: array<vec4<f32>>;
@group(0) @binding(1) var reflection: texture_2d<f32>;
@group(0) @binding(2) var reflection_sampler: sampler;
@group(0) @binding(3) var opaque_color: texture_2d<f32>;
@group(0) @binding(4) var opaque_depth: texture_depth_2d;
@group(0) @binding(5) var water_normal: texture_2d<f32>;
@group(0) @binding(6) var water_normal_sampler: sampler;
@group(0) @binding(7) var cloud_noise: texture_2d<f32>;
@group(0) @binding(8) var cloud_noise_sampler: sampler;
struct Surface { color: vec4<f32> }
var<private> shadow: f32;
fn shadow_visibility(p: vec3<f32>, n: vec3<f32>) -> f32 { return shadow; }
var<private> test_light_field: vec4<f32>;
var<private> test_light_sphere: bool;
fn block_light_color(p: vec3<f32>) -> vec4<f32> {
    if test_light_sphere {
        let falloff = max(1.0 - distance(p, vec3<f32>(0.0, 0.0, -5.0)) / 14.0, 0.0);
        return vec4<f32>(test_light_field.rgb, falloff * falloff);
    }
    return test_light_field;
}
var<private> test_surface_smoothness: f32;
var<private> test_surface_data: f32;
var<private> test_surface_normal: vec3<f32>;
fn set_surface(n: vec3<f32>, s: f32, data: f32) {
    test_surface_normal = n;
    test_surface_smoothness = s;
    test_surface_data = data;
}
var<private> test_block_bump_grad: vec2<f32>;
var<private> test_block_pbr: bool;
fn block_pbr_maps() -> bool { return test_block_pbr; }
fn block_texture_size() -> vec2<f32> { return vec2<f32>(256.0, 256.0); }
fn block_texture_level(uv: vec2<f32>, lod: f32) -> vec4<f32> {
    let slope = clamp(0.25 + dot(uv, test_block_bump_grad), 0.02, 0.95);
    return vec4<f32>(vec3<f32>(slope * slope), 1.0);
}
"""
UNLIT = """
// The adapter tests isolate albedo transfer from lighting integration.
fn apply_block_air_scatter(lit: vec3<f32>, p: vec3<f32>, level: f32) -> vec3<f32> { return lit; }
fn block_surface_light(p: vec3<f32>, level: f32) -> vec3<f32> { return vec3<f32>(0.0); }
fn local_surface_light(p: vec3<f32>, level: f32, colored: vec3<f32>) -> vec3<f32> { return vec3<f32>(0.0); }
fn shade_surface(p: vec3<f32>, n: vec3<f32>, sky_light: f32,
                 albedo: vec3<f32>, emission: f32, local: vec3<f32>, grass: bool,
                 green_receiver: bool, noon_fill: f32) -> vec3<f32> { return albedo; }
fn shade_surface_with_celestial_response(p: vec3<f32>, n: vec3<f32>, sky_light: f32,
                                         albedo: vec3<f32>, emission: f32, local: vec3<f32>, grass: bool,
                                         leaves: bool, green_receiver: bool, solid: bool, noon_fill: f32,
                                         response: vec2<f32>, highlight: vec4<f32>) -> vec4<f32> { return vec4<f32>(albedo, 0.0); }
fn surface_highlight(p: vec3<f32>, n: vec3<f32>, s: f32, f0: vec3<f32>, albedo: vec3<f32>, strength: vec2<f32>) -> vec4<f32> { return vec4<f32>(0.0); }
const sunlight_strength: f32 = 1.0;
"""
ENTITY_INPUT = """
struct EntityInput {
    albedo: vec4<f32>, tint: vec4<f32>, overlay: vec4<f32>, lightmap: vec3<f32>,
    shade: f32, position: vec3<f32>, normal: vec3<f32>, light: vec2<f32>,
    full_light: bool, colored_light: vec3<f32>, light_source_tier: u32,
}
"""
MATERIAL_INPUT = """
struct MaterialInput {
    albedo: vec4<f32>, tint: vec4<f32>, shade: f32, ao: f32, light: vec2<f32>, lightmap: vec3<f32>,
    position: vec3<f32>, normal: vec3<f32>, emission: f32,
    colored_light: vec3<f32>, fluid: u32, translucent: bool, face: u32,
    screen: vec2<f32>,
    tangent: vec4<f32>, material: u32, tags: u32, uv: vec2<f32>,
    shaded_tint: vec4<f32>,
}
"""
VERTEX_INPUT = """
struct VertexInput {
    position: vec3<f32>, uv: vec2<f32>, material: u32, light: vec2<f32>,
    tint: vec4<f32>, shade: f32, ao: f32, face: u32, fluid: u32,
    shaded_tint: vec4<f32>,
}
"""
WEATHER_INPUT = """
struct WeatherInput {
    color: vec4<f32>, light: vec2<f32>, position: vec3<f32>, snow: bool,
}
"""


def production_function(filename, name):
    source = (ROOT / "horizon_lighting" / filename).read_text("utf-8")
    start = source.index("fn " + name + "(")
    end = source.index("{", start)
    depth = 1
    while depth:
        end += 1
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
    return source[start:end + 1]


def load_rgba_png(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = 0
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bits, color_type, *_ = struct.unpack(">2I5B", chunk)
            assert bits == 8 and color_type == 6
        elif kind == b"IDAT":
            idat.extend(chunk)
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = bytearray(width * height * 4)
    for y in range(height):
        row_start = y * (stride + 1)
        assert raw[row_start] == 0
        out[y * stride:(y + 1) * stride] = raw[row_start + 1:row_start + 1 + stride]
    return width, height, bytes(out)


@unittest.skipUnless(AVAILABLE, "optional wgpu runtime not installed")
class GpuAdapterRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wgpu
        cls.wgpu = wgpu
        cls.adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        cls.device = cls.adapter.request_device_sync()
        cw, ch, cbytes = load_rgba_png(ROOT / "horizon_lighting" / "cloud-noise.png")
        cls.cloud_tex = cls.device.create_texture(
            size=(cw, ch, 1), format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
        cls.device.queue.write_texture(
            {"texture": cls.cloud_tex}, cbytes,
            {"bytes_per_row": cw * 4, "rows_per_image": ch}, (cw, ch, 1))
        cls.cloud_sampler = cls.device.create_sampler(
            address_mode_u="repeat", address_mode_v="repeat",
            mag_filter="linear", min_filter="linear")
        cls.results = []

    @classmethod
    def tearDownClass(cls):
        report = {"adapter": dict(cls.adapter.info), "cases": cls.results,
                  "scope": "production WGSL adapters, procedural optics and finish/F0 helpers; not full SSR integration or in-game visual tuning"}
        (ROOT / "validation").mkdir(exist_ok=True)
        (ROOT / "validation" / "gpu-adapters.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")

    def execute(self, source, body, constants=None):
        wgpu, device = self.wgpu, self.device
        code = FRAME + source + "\n@compute @workgroup_size(1) fn main() {\nframe.fog_environment = vec2<f32>(1024.0, 1024.0); frame.fog_render = vec2<f32>(1024.0, 1024.0); shadow = 1.0;\n" + body + "\n}"
        module = device.create_shader_module(code=code)
        layout = device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": "storage"}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE,
             "texture": {"sample_type": "float", "view_dimension": "2d", "multisampled": False}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE,
             "sampler": {"type": "filtering"}},
            {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE,
             "texture": {"sample_type": "float", "view_dimension": "2d", "multisampled": False}},
            {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE,
             "texture": {"sample_type": "depth", "view_dimension": "2d", "multisampled": False}},
            {"binding": 5, "visibility": wgpu.ShaderStage.COMPUTE,
             "texture": {"sample_type": "float", "view_dimension": "2d", "multisampled": False}},
            {"binding": 6, "visibility": wgpu.ShaderStage.COMPUTE,
             "sampler": {"type": "filtering"}},
            {"binding": 7, "visibility": wgpu.ShaderStage.COMPUTE,
             "texture": {"sample_type": "float", "view_dimension": "2d", "multisampled": False}},
            {"binding": 8, "visibility": wgpu.ShaderStage.COMPUTE,
             "sampler": {"type": "filtering"}},
        ])
        pipeline = device.create_compute_pipeline(
            layout=device.create_pipeline_layout(bind_group_layouts=[layout]),
            compute={"module": module, "entry_point": "main", "constants": constants or {}})
        buffer = device.create_buffer(size=16, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
        texture = device.create_texture(size=(1, 1, 1), format="rgba8unorm", usage=wgpu.TextureUsage.TEXTURE_BINDING)
        background = device.create_texture(size=(1, 1, 1), format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
        device.queue.write_texture({"texture": background}, bytes((70, 100, 115, 255)),
                                   {"bytes_per_row": 4, "rows_per_image": 1}, (1, 1, 1))
        depth = device.create_texture(size=(1, 1, 1), format="depth32float",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.RENDER_ATTACHMENT)
        normals = device.create_texture(size=(2, 2, 1), format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
        device.queue.write_texture({"texture": normals}, bytes((
            102, 115, 252, 255, 153, 115, 252, 255,
            102, 140, 252, 255, 153, 140, 252, 255,
        )), {"bytes_per_row": 8, "rows_per_image": 2}, (2, 2, 1))
        normal_sampler = device.create_sampler(address_mode_u="repeat", address_mode_v="repeat",
            mag_filter="linear", min_filter="linear")
        group = device.create_bind_group(layout=layout, entries=[
            {"binding": 0, "resource": {"buffer": buffer, "offset": 0, "size": 16}},
            {"binding": 1, "resource": texture.create_view()},
            {"binding": 2, "resource": device.create_sampler(mag_filter="linear", min_filter="linear")},
            {"binding": 3, "resource": background.create_view()},
            {"binding": 4, "resource": depth.create_view()},
            {"binding": 5, "resource": normals.create_view()},
            {"binding": 6, "resource": normal_sampler},
            {"binding": 7, "resource": self.cloud_tex.create_view()},
            {"binding": 8, "resource": self.cloud_sampler},
        ])
        encoder = device.create_command_encoder()
        compute = encoder.begin_compute_pass()
        compute.set_pipeline(pipeline)
        compute.set_bind_group(0, group)
        compute.dispatch_workgroups(1)
        compute.end()
        device.queue.submit([encoder.finish()])
        value = struct.unpack("4f", device.queue.read_buffer(buffer))
        self.results.append({"test": self.id(), "value": value})
        return value

    def test_entity_vanilla_fallbacks_preserve_shade_and_overlay(self):
        source = UNLIT + ENTITY_INPUT + (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "fog.wgsl").read_text("utf-8")
        source += production_function("lighting.wgsl", "respect_effects")
        source += (ROOT / "horizon_lighting" / "entity.wgsl").read_text("utf-8")
        # Custom dimension, End with an active effect, and Overworld night vision.
        for dimension, effect, overlay_alpha in [(2, 0.0, 0.5), (1, 1.0, 0.5), (0, 1.0, 0.0)]:
            with self.subTest(dimension=dimension, effect=effect):
                value = self.execute(source, f"""
                    frame.dimension = {dimension}; frame.night_vision = {effect};
                    var input: EntityInput;
                    input.albedo = vec4<f32>(0.5, 0.4, 0.3, 1.0);
                    input.tint = vec4<f32>(1.0); input.shade = 0.25;
                    input.lightmap = vec3<f32>(1.0);
                    input.overlay = vec4<f32>(0.8, 0.1, 0.05, {overlay_alpha});
                    output[0] = entity(input).color;
                """)
                expected = [((c * 0.25) ** (1 / 2.2) * (1 - overlay_alpha)
                             + o ** (1 / 2.2) * overlay_alpha) ** 2.2
                            for c, o in zip((0.5, 0.4, 0.3), (0.8, 0.1, 0.05))]
                for actual, target in zip(value[:3], expected):
                    self.assertAlmostEqual(actual, target, delta=0.00002)

    def test_dimension_palette_and_local_field_are_shared_by_terrain_and_entities(self):
        source = MATERIAL_INPUT + ENTITY_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material", "entity"))
        body = """
            frame.dimension = DIMENSION;
            frame.fog_environment = vec2<f32>(8.0, 1024.0);
            frame.fog_render = vec2<f32>(8.0, 1024.0);
            var ground: MaterialInput;
            ground.albedo = vec4<f32>(0.6, 0.6, 0.6, 1.0);
            ground.shaded_tint = vec4<f32>(1.0);
            ground.position.z = -4.0;
            ground.lightmap = vec3<f32>(0.4);
            var mob: EntityInput;
            mob.albedo = ground.albedo;
            mob.tint = ground.shaded_tint;
            mob.position = ground.position;
            mob.lightmap = ground.lightmap;
            mob.shade = 1.0;
            let ambient = shade_material(ground).color.rgb;
            ground.light.x = 0.7;
            mob.light.x = ground.light.x;
            test_light_field = vec4<f32>(1.0, 0.32, 0.10, 0.9);
            let lit = shade_material(ground).color.rgb;
            let entity_lit = entity(mob).color.rgb;
            output[0] = vec4<f32>(ambient.r - ambient.b, lit.r - ambient.r,
                lit.r - entity_lit.r, entity_lit.r);
        """
        options = {"block_volumetric_strength": 0.0}
        nether = self.execute(source, body.replace("DIMENSION", "-1"), options)
        end = self.execute(source, body.replace("DIMENSION", "1"), options)
        custom = self.execute(source, body.replace("DIMENSION", "2"), options)
        self.assertGreater(nether[0], 0.01)
        self.assertLess(end[0], -0.008)
        self.assertGreater(nether[1], end[1])
        self.assertGreater(end[1], 0.1)
        for sample in (nether, end, custom):
            self.assertAlmostEqual(sample[2], 0.0, delta=0.00002)
        self.assertAlmostEqual(custom[1], 0.0, delta=0.00002)
        self.assertAlmostEqual(custom[3], 0.24, delta=0.00002)

    def test_material_tint_does_not_change_when_normal_flips(self):
        source = UNLIT + MATERIAL_INPUT + (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "gloss.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "fog.wgsl").read_text("utf-8")
        source += production_function("lighting.wgsl", "respect_effects")
        water_file = ROOT / "horizon_lighting" / "water.wgsl"
        if water_file.exists():
            source += water_file.read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "material.wgsl").read_text("utf-8")
        for normal in [(0, 1, 0), (0, -1, 0), (0.70710678, 0, 0.70710678)]:
            with self.subTest(normal=normal):
                value = self.execute(source, f"""
                    frame.dimension = 0; frame.eye_in = 1u;
                    var input: MaterialInput;
                    input.albedo = vec4<f32>(0.4, 0.3, 0.2, 0.6);
                    input.shaded_tint = vec4<f32>(1.0); input.lightmap = vec3<f32>(1.0);
                    input.normal = vec3<f32>({normal[0]}, {normal[1]}, {normal[2]});
                    input.fluid = 0u; input.translucent = false;
                    output[0] = shade_material(input).color;
                """)
                for actual, target in zip(value, (0.4, 0.3, 0.2, 0.6)):
                    self.assertAlmostEqual(actual, target, delta=0.00002)

    def test_grass_shade_stays_readable_on_both_noon_faces(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        value = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.4, 0.916515, 0.0);
            frame.light_direction = frame.sun_direction;
            shadow = 0.0;
            var grass: MaterialInput;
            grass.material = 40u;
            grass.albedo = vec4<f32>(0.5, 0.5, 0.5, 1.0);
            grass.shaded_tint = vec4<f32>(1.0);
            grass.light.y = 1.0;
            grass.normal = vec3<f32>(1.0, 0.0, 0.0);
            let front = shade_material(grass).color.g;
            grass.normal = -grass.normal;
            let back = shade_material(grass).color.g;
            shadow = 1.0;
            let sunlit = shade_material(grass).color.g;
            shadow = 0.0;
            grass.light.y = 0.0;
            let cave = shade_material(grass).color.g;
            output[0] = vec4<f32>(front, back, cave, sunlit);
        """)
        self.assertGreater(min(value[:2]), 0.13)
        self.assertAlmostEqual(value[0], value[1], delta=0.00002)
        self.assertLess(value[2], 0.01)
        self.assertLess(value[0], value[3] * 0.48)

    def test_torch_tip_renders_warm_while_its_handle_keeps_texture_color(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        value = self.execute(source, """
            var torch: MaterialInput;
            torch.material = 50u;
            torch.shaded_tint = vec4<f32>(1.0);
            torch.emission = 14.0 / 15.0;
            torch.albedo = vec4<f32>(1.0, 0.72, 0.12, 1.0);
            let tip = shade_material(torch).color;
            torch.albedo = vec4<f32>(0.35, 0.2, 0.08, 1.0);
            let handle = shade_material(torch).color;
            output[0] = vec4<f32>(tip.rgb, handle.g);
        """)
        self.assertAlmostEqual(value[1] / value[0], 0.68, delta=0.00002)
        self.assertAlmostEqual(value[2] / value[0], 0.30, delta=0.00002)
        self.assertGreater(value[0], 1.7)
        self.assertAlmostEqual(value[3], 0.2, delta=0.00002)

    def test_lava_emits_bright_golden_hot_texels(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        red, green, blue, cooler_green = self.execute(source, """
            var lava: MaterialInput;
            lava.fluid = 2u;
            lava.emission = 1.0;
            lava.shaded_tint = vec4<f32>(1.0);
            lava.albedo = vec4<f32>(0.95, 0.50, 0.04, 1.0);
            let hot = material(lava).color.rgb;
            lava.albedo.g = 0.10;
            let cool = material(lava).color.g;
            output[0] = vec4<f32>(hot, cool);
        """)
        self.assertGreater(green, 1.5)
        self.assertTrue(0.40 < green / red < 0.80)
        self.assertLess(blue, green * 0.40)
        self.assertGreater(green, 3.0 * cooler_green)

    def test_dynamic_torch_color_reaches_overworld_terrain(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        red, green, blue, ambient = self.execute(source, """
            frame.sun_direction.y = -1.0;
            var stone: MaterialInput;
            stone.albedo = vec4<f32>(0.50, 0.50, 0.50, 1.0);
            stone.shaded_tint = vec4<f32>(1.0);
            stone.normal.y = 1.0;
            stone.position = vec3<f32>(0.0, -1.2, -5.0);
            let ambient = material(stone).color.r;
            // Horizon populates MAX-propagated light.x alongside colored_light for held & dropped lights.
            stone.light.x = 0.85;
            stone.colored_light = vec3<f32>(0.78, 0.35, 0.065);
            let lit = material(stone).color.rgb;
            output[0] = vec4<f32>(lit, ambient);
        """)
        self.assertGreater(red - ambient, 0.12)
        self.assertGreater(red, 1.6 * green)
        self.assertGreater(green, 2.0 * blue)
        # Outside the MAX block-light pool (light.x <= 0.32), even clipped colored_light stays strictly off.
        outside, _, _, _ = self.execute(source, """
            let outside = local_surface_light(vec3<f32>(0.0, -1.0, -6.5), 0.25, vec3<f32>(1.0, 1.0, 1.0)).r;
            output[0] = vec4<f32>(outside, 0.0, 0.0, 1.0);
        """)
        self.assertEqual(outside, 0.0)

    def test_metal_gets_local_reflections_only_on_top(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            test_light_field = vec4<f32>(1.0, 0.22, 0.05, 1.0);
            frame.sun_direction.y = -1.0;
            var metal: MaterialInput;
            metal.material = 10u;
            metal.albedo = vec4<f32>(0.6, 0.6, 0.6, 1.0);
            metal.shaded_tint = vec4<f32>(1.0);
            metal.light.x = 1.0;
            metal.normal = vec3<f32>(0.0, 1.0, 0.0);
            metal.position = -metal.normal * 4.0;
            let top = shade_material(metal).color.r;
            metal.normal = vec3<f32>(1.0, 0.0, 0.0);
            metal.position = -metal.normal * 4.0;
            let side = shade_material(metal).color.r;
            metal.normal = vec3<f32>(0.0, -1.0, 0.0);
            metal.position = -metal.normal * 4.0;
            let bottom = shade_material(metal).color.r;
            let edge = field_radiance(vec4<f32>(1.0, 0.22, 0.05, 0.25));
            output[0] = vec4<f32>(top, side, bottom, edge.r);
        """
        lit = self.execute(source, body, {"block_volumetric_strength": 0.0})
        diffuse = self.execute(source, body, {"block_volumetric_strength": 0.0, "gloss_strength": 0.0})
        self.assertGreater(lit[0], diffuse[0] + 0.01)
        self.assertAlmostEqual(lit[1], diffuse[1], places=5)
        self.assertAlmostEqual(lit[2], diffuse[2], places=5)
        self.assertLess(lit[3], 0.004)

    def test_block_light_field_controls_in_air_scattering(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        body = """
            test_light_field = vec4<f32>(1.0, 0.42, 0.08, 0.90);
            let short_ray = block_air_scatter(vec3<f32>(0.0, 0.0, -2.0), 1.0);
            let long_ray = block_air_scatter(vec3<f32>(0.0, 0.0, -8.0), 1.0);
            let far = block_air_scatter(vec3<f32>(0.0, 0.0, -30.0), 1.0);
            output[0] = vec4<f32>(far.r, long_ray.r - short_ray.r, long_ray.g, long_ray.b);
        """
        enabled = self.execute(source, body, {"block_volumetric_strength": 0.65})
        disabled = self.execute(source, body, {"block_volumetric_strength": 0.0})
        self.assertAlmostEqual(enabled[0], 0.0, delta=0.00002)
        self.assertGreater(enabled[1], 0.01)
        self.assertGreater(enabled[2], enabled[3])
        self.assertGreater(enabled[3], 0.0)
        self.assertEqual(disabled, (0.0, 0.0, 0.0, 0.0))

    def test_faint_propagated_block_light_rejects_tint_and_glow(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        surface, fog, lit_surface, lit_fog = self.execute(source, """
            test_light_field = vec4<f32>(1.0, 0.42, 0.08, 0.90);
            frame.eye_light_smooth.x = 1.0;
            let receiver = vec3<f32>(0.0, 0.0, -5.0);
            output[0] = vec4<f32>(block_surface_light(receiver, 1.0 / 15.0).r,
                block_air_scatter(receiver, 1.0 / 15.0).r,
                block_surface_light(receiver, 0.65).r, block_air_scatter(receiver, 0.65).r);
        """, {"block_volumetric_strength": 0.65})
        self.assertEqual(surface, 0.0)
        self.assertEqual(fog, 0.0)
        self.assertGreater(lit_surface, 0.1)
        self.assertGreater(lit_fog, 0.01)

    def test_signature_warm_sunlight_tint_stays_fixed_on_neutral_terrain(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        red, green, blue, afternoon_red = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.90, 0.435, 0.0));
            frame.light_direction = frame.sun_direction;
            shadow = 1.0;
            let black = vec3<f32>(0.0);
            let lit = shade_surface(black, frame.sun_direction, 1.0,
                vec3<f32>(0.5), 0.0, black, false, false, 1.0);
            frame.sun_direction = normalize(vec3<f32>(0.50, 0.866, 0.0));
            frame.light_direction = frame.sun_direction;
            let afternoon = shade_surface(black, frame.sun_direction, 1.0,
                vec3<f32>(0.5), 0.0, black, false, false, 1.0);
            output[0] = vec4<f32>(lit, afternoon.r / max(afternoon.b, 0.001));
        """, {"procedural_clouds": False})
        self.assertGreater(red, green * 1.30)
        self.assertGreater(green, blue * 1.45)
        self.assertGreater(afternoon_red, 1.08)

    def test_fire_glow_concentrates_around_the_source(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        value = self.execute(source, """
            test_light_sphere = true;
            test_light_field = vec4<f32>(1.0, 0.22, 0.05, 1.0);
            let center = block_air_scatter(vec3<f32>(0.0, 0.0, -8.0), 1.0).r;
            let edge = block_air_scatter(vec3<f32>(4.0, 0.0, -8.0), 1.0).r;
            let outside = block_air_scatter(vec3<f32>(6.0, 0.0, -8.0), 1.0).r;
            output[0] = vec4<f32>(center, edge, outside, 1.0);
        """, {"block_volumetric_strength": 0.65})
        self.assertGreater(value[0], 0.03)
        self.assertGreater(value[1], 0.0)
        self.assertLess(value[1], value[0] * 0.23)
        self.assertLess(value[2], 0.001)

    def test_firelight_preserves_receiver_color_and_limits_air_veil(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.rain = 1.0;
            frame.sun_direction = vec3<f32>(0.0, -1.0, 0.0);
            test_light_field = vec4<f32>(1.0, 0.22, 0.035, 0.76);
            var ground: MaterialInput;
            ground.albedo = vec4<f32>(0.07, 0.50, 0.09, 1.0);
            ground.shaded_tint = vec4<f32>(1.0);
            ground.light = vec2<f32>(0.8, 1.0);
            ground.colored_light = vec3<f32>(0.7, 0.2, 0.04);
            ground.position = vec3<f32>(0.0, 0.0, -8.0);
            ground.normal = vec3<f32>(0.0, 1.0, 0.0);
            let lit = shade_material(ground).color.rgb;
            ground.albedo = vec4<f32>(0.0, 0.0, 0.0, 1.0);
            let black = shade_material(ground).color.rgb;
            output[0] = vec4<f32>(lit.rg - black.rg, black.r, black.r - black.b);
        """
        enabled = self.execute(source, body, {"block_volumetric_strength": 0.65})
        disabled = self.execute(source, body, {"block_volumetric_strength": 0.0})
        self.assertGreater(disabled[1], 0.07)
        self.assertGreater(disabled[1], disabled[0])
        self.assertGreater(enabled[2], 0.0)
        self.assertLess(enabled[2], 0.003)
        self.assertTrue(0.001 < enabled[3] < 0.0019, enabled[3])
        self.assertAlmostEqual(disabled[2], 0.0, delta=0.00002)

    def test_wet_grass_darkens_without_changing_pigment_or_cutout(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        body = """
            frame.rain = 1.0;
            var grass: MaterialInput;
            grass.material = 40u;
            grass.albedo = vec4<f32>(0.3, 0.5, 0.2, 0.8);
            grass.shaded_tint = vec4<f32>(1.0);
            grass.light.y = 1.0;
            grass.normal = vec3<f32>(1.0, 0.0, 0.0);
            let wet = shade_material(grass).color;
            grass.light.y = 0.0;
            let sheltered = shade_material(grass).color;
            output[0] = vec4<f32>(wet.rg, sheltered.r, wet.a);
        """
        wet = self.execute(source, body)
        disabled = self.execute(source, body, {"wetness_strength": 0.0})
        self.assertLess(wet[0], disabled[0] * 0.90)
        self.assertLess(wet[1], disabled[1] * 0.88)
        self.assertAlmostEqual(wet[1] / wet[0], disabled[1] / disabled[0], delta=0.00002)
        self.assertAlmostEqual(wet[2], disabled[2], delta=0.00002)
        self.assertAlmostEqual(wet[3], 0.8, delta=0.00002)

    def test_exposed_stone_develops_a_stronger_wet_finish(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        body = """
            var stone: MaterialInput;
            stone.albedo = vec4<f32>(0.36, 0.36, 0.36, 1.0);
            stone.shaded_tint = vec4<f32>(1.0);
            stone.light.y = 1.0;
            stone.normal.y = 1.0;
            frame.rain = 0.65;
            let wet = shade_material(stone).color.r;
            let smoothness = test_surface_smoothness;
            let f0 = decode_f0(test_surface_data).r;
            stone.light.y = 0.0;
            let sheltered = shade_material(stone).color.r;
            output[0] = vec4<f32>(smoothness, f0, wet / sheltered, test_surface_smoothness);
        """
        wet = self.execute(source, body)
        disabled = self.execute(source, body, {"wetness_strength": 0.0})
        self.assertGreater(wet[0], 0.43)
        self.assertGreater(wet[1], 0.055)
        self.assertLess(wet[2], 0.84)
        self.assertEqual(wet[3], 0.0)
        self.assertEqual(disabled[0], 0.0)
        self.assertAlmostEqual(disabled[1], 0.04, delta=0.002)
        self.assertAlmostEqual(disabled[2], 1.0, delta=0.00002)

    def test_rain_coats_stone_with_some_skylight_loss(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        body = """
            var stone: MaterialInput;
            stone.albedo = vec4<f32>(0.36, 0.36, 0.36, 1.0);
            stone.shaded_tint = vec4<f32>(1.0);
            stone.light.y = 12.0 / 15.0;
            stone.normal.y = 1.0;
            let dry = shade_material(stone).color.r;
            frame.rain = 0.65;
            let wet = shade_material(stone).color.r;
            let smoothness = select(0.0, test_surface_smoothness, test_surface_data < 0.0);
            stone.light.y = 7.0 / 15.0;
            _ = shade_material(stone);
            let sheltered = test_surface_smoothness;
            stone.light.y = 1.0;
            stone.normal = vec3<f32>(1.0, 0.0, 0.0);
            _ = shade_material(stone);
            output[0] = vec4<f32>(wet / dry, smoothness, sheltered, test_surface_smoothness);
        """
        ratio, finish, sheltered, wall = self.execute(source, body)
        self.assertLess(ratio, 0.83)
        self.assertGreater(finish, 0.51)
        self.assertEqual(sheltered, 0.0)
        self.assertGreater(wall, 0.45)
        self.assertLess(wall, finish)

    def test_shaded_faces_receive_directional_skylight(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        top, underside, blue_gain, cave = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.light_direction = frame.sun_direction;
            let p = vec3<f32>(0.0);
            let base = vec3<f32>(0.5);
            let up = vec3<f32>(0.0, 1.0, 0.0);
            let no_local = vec3<f32>(0.0);
            let top = shade_surface(p, up, 1.0, base, 0.0, no_local, false, false, 1.0);
            let underside = shade_surface(p, -up, 1.0, base, 0.0, no_local, false, false, 1.0);
            let cave = shade_surface(p, up, 0.0, base, 0.0, no_local, false, false, 1.0);
            output[0] = vec4<f32>(top.g, underside.g, top.b / top.r - underside.b / underside.r, cave.g);
        """, {"sunlight_strength": 0.0, "indirect_warmth": 0.0})
        self.assertGreater(top, underside * 1.15)
        self.assertGreater(blue_gain, 0.08)
        self.assertLess(cave, 0.01)

    def test_open_canopy_shade_gets_cool_fill_while_sealed_caves_stay_dark(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        shade, blue_ratio, sunlit, cave = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.9474, 0.32, 0.0);
            frame.light_direction = frame.sun_direction;
            let normal = vec3<f32>(1.0, 0.0, 0.0);
            let base = vec3<f32>(0.5);
            let origin = vec3<f32>(0.0);
            shadow = 0.0;
            let shade = shade_surface(origin, normal, 0.60, base, 0.0, origin, false, true, 0.0);
            let cave = shade_surface(origin, normal, 0.08, base, 0.0, origin, false, true, 0.0);
            shadow = 1.0;
            let sunlit = shade_surface(origin, normal, 0.60, base, 0.0, origin, false, true, 0.0);
            output[0] = vec4<f32>(shade.g, shade.b / shade.r, sunlit.g, cave.g);
        """, {"procedural_clouds": False})
        self.assertGreater(shade, 0.055)
        self.assertGreater(blue_ratio, 0.95)
        self.assertGreater(sunlit, 2.0 * shade)
        self.assertLess(cave, 0.006)

    def test_cloud_shadows_track_the_layer_in_world_space(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        clear, rainy, camera_error, wrap_error = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.camera_position = vec3<f32>(30.0, 80.0, 83.0);
            let receiver = vec3<f32>(131.0, 0.0, 82.0);
            let clear = cloud_light_transmission(receiver, frame.sun_direction);
            frame.rain = 1.0;
            let rainy = cloud_light_transmission(receiver, frame.sun_direction);
            let movement = vec3<f32>(42.0, 10.0, -18.0);
            frame.camera_position += movement;
            let shifted = cloud_light_transmission(receiver - movement, frame.sun_direction);
            frame.time = 3600.0;
            let wrapped = cloud_light_transmission(receiver - movement, frame.sun_direction);
            output[0] = vec4<f32>(clear, rainy, abs(shifted - rainy), abs(wrapped - rainy));
        """)
        self.assertLess(rainy, clear - 0.2)
        self.assertAlmostEqual(camera_error, 0.0, places=5)
        self.assertAlmostEqual(wrap_error, 0.0, places=5)

    def test_clear_sky_has_a_bluer_zenith_and_rain_mutes_it(self):
        source = "struct SkyInput { direction: vec3<f32>, color: vec4<f32> }\n"
        source += "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "sky"))
        zenith, horizon, rain, rain_brightness = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.6, 0.8, 0.0);
            let original = vec4<f32>(0.24, 0.46, 0.89, 1.0);
            let up = SkyInput(vec3<f32>(0.0, 1.0, 0.0), original);
            let side = SkyInput(vec3<f32>(1.0, 0.0, 0.0), original);
            let zenith = sky(up);
            let horizon = sky(side);
            frame.rain = 1.0;
            let rain = sky(up);
            frame.dimension = -1;
            let nether_unchanged = all(sky(up) == original);
            output[0] = vec4<f32>(zenith.b / zenith.r, horizon.b / horizon.r,
                rain.b / rain.r, select(1.0, rain.g / zenith.g, nether_unchanged));
        """, {"procedural_clouds": False})
        self.assertGreater(zenith, horizon + 0.25)
        self.assertLess(rain, 1.24)
        self.assertLess(rain_brightness, 0.45)

    def test_sky_draws_solar_glare_in_rain_when_cloud_layer_is_disabled(self):
        source = "struct SkyInput { direction: vec3<f32>, color: vec4<f32> }\n"
        source += "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "sky"))
        center, halo, same_angle, far = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.rain = 1.0;
            let backdrop = vec4<f32>(0.24, 0.46, 0.89, 1.0);
            let center = sky(SkyInput(frame.sun_direction, backdrop)).r;
            let halo = sky(SkyInput(normalize(vec3<f32>(0.06, 1.0, 0.0)), backdrop)).r;
            let same_angle = sky(SkyInput(normalize(vec3<f32>(0.0, 1.0, 0.06)), backdrop)).r;
            let far = sky(SkyInput(normalize(vec3<f32>(0.45, 1.0, 0.0)), backdrop)).r;
            output[0] = vec4<f32>(center, halo, same_angle, far);
        """, {"procedural_clouds": False})
        self.assertGreater(center, 2.0 * halo)
        self.assertGreater(halo, far + 0.12)
        self.assertAlmostEqual(halo, same_angle, places=5)

    def test_solar_glare_has_no_hard_disk_edge(self):
        source = "struct SkyInput { direction: vec3<f32>, color: vec4<f32> }\n"
        source += "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "sky"))
        inside, outside, shoulder, _ = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            let inside = solar_disk_and_glare(normalize(vec3<f32>(0.019, 1.0, 0.0))).r;
            let outside = solar_disk_and_glare(normalize(vec3<f32>(0.024, 1.0, 0.0))).r;
            let shoulder = solar_disk_and_glare(normalize(vec3<f32>(0.065, 1.0, 0.0))).r;
            output[0] = vec4<f32>(inside, outside, shoulder, 0.0);
        """)
        self.assertGreater(outside, 0.75 * inside)
        self.assertGreater(shoulder, 1.3)

    def test_clear_clouds_leave_warm_sunset_light_and_cast_shadows_on_terrain(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        gain, blue_gain, red, blue = self.execute(source, """
            frame.camera_position = vec3<f32>(154.0, 110.0, 114.0);
            frame.sun_direction = normalize(vec3<f32>(-0.99, 0.14, 0.0));
            frame.light_direction = frame.sun_direction;
            let up = vec3<f32>(0.0, 1.0, 0.0);
            let origin = vec3<f32>(0.0);
            let stone = vec3<f32>(0.5);
            shadow = 1.0;
            let lit = shade_surface(origin, up, 1.0, stone, 0.0, origin, false, false, 0.0);
            shadow = 0.0;
            let dark = shade_surface(origin, up, 1.0, stone, 0.0, origin, false, false, 0.0);
            output[0] = vec4<f32>(lit.r - dark.r, lit.b - dark.b, lit.r, lit.b);
        """)
        self.assertGreater(gain, 0.16)
        self.assertGreater(gain, blue_gain * 4.0)
        self.assertGreater(red, blue * 1.45)

    def test_block_light_falls_when_propagation_weakens_near_a_source(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        dim, open_light, midrange, near_core = self.execute(source, """
            test_light_field = vec4<f32>(1.0, 0.42, 0.08, 0.90);
            let at = vec3<f32>(0.0, 0.0, -5.0);
            let dim = block_surface_light(at, 0.40).r;
            let open = block_surface_light(at, 0.85).r;
            test_light_field.a = 0.95;
            let core = block_surface_light(at, 0.92).r;
            test_light_field.a = 0.40;
            output[0] = vec4<f32>(dim, open, block_surface_light(at, 0.60).r, core);
        """)
        self.assertLess(dim, 0.35 * open_light)
        # Compact radius: outer midrange tapers strongly while the near-emitter core glows brightly.
        self.assertTrue(0.01 < midrange < 0.12, midrange)
        self.assertGreater(near_core, 1.5)

    def test_multiple_emitters_stay_bounded_in_brightness_and_radius(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        one_near, two_near, one_outer, two_outer = self.execute(source, """
            let at = vec3<f32>(0.0, 0.0, -4.0);
            test_light_field = vec4<f32>(1.06, 0.74, 0.34, 0.45);
            let one_near = block_surface_light(at, 0.87).r;
            test_light_field = vec4<f32>(2.12, 1.48, 0.68, 0.95);
            let two_near = block_surface_light(at, 0.87).r;
            test_light_field = vec4<f32>(1.06, 0.74, 0.34, 0.20);
            let one_outer = block_surface_light(at, 0.50).r;
            test_light_field = vec4<f32>(2.12, 1.48, 0.68, 0.60);
            let two_outer = block_surface_light(at, 0.50).r;
            output[0] = vec4<f32>(one_near, two_near, one_outer, two_outer);
        """)
        # A single torch stays bright close up; placing 2+ torches stays softly bounded.
        self.assertGreater(one_near, 1.0)
        self.assertLess(two_near, one_near * 1.40)
        # Outer surroundings stay clean and dark even when multiple torches overlap.
        self.assertLess(one_outer, 0.015)
        self.assertLess(two_outer, 0.025)

    def test_rain_in_desert_never_inverts_shadows(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        lit_r, lit_g, shaded_r, shaded_g = self.execute(source, """
            frame.rain = 1.0;
            frame.sun_direction = normalize(vec3<f32>(-0.92, 0.24, 0.30));
            frame.light_direction = frame.sun_direction;
            var sand: MaterialInput;
            sand.albedo = vec4<f32>(0.65, 0.58, 0.36, 1.0);
            sand.shaded_tint = vec4<f32>(1.0);
            sand.normal = vec3<f32>(0.0, 1.0, 0.0);
            sand.position = vec3<f32>(0.0, -1.0, -6.0);
            sand.light = vec2<f32>(0.0, 1.0);
            shadow = 1.0;
            let lit = shade_material(sand).color.rgb;
            shadow = 0.0;
            let shaded = shade_material(sand).color.rgb;
            output[0] = vec4<f32>(lit.rg, shaded.rg);
        """)
        # Lit wet sand in rain must never be darker than shadowed sand.
        self.assertGreaterEqual(lit_r, shaded_r)
        self.assertGreaterEqual(lit_g, shaded_g)

    def test_warm_blocks_under_sunset_limit_torch_overexposure(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        sunlit_no_torch, sunlit_with_torch, cave_with_torch, night_with_torch = self.execute(source, """
            let plank = vec4<f32>(0.48, 0.30, 0.12, 1.0);
            frame.sun_direction = normalize(vec3<f32>(-0.92, 0.24, 0.30));
            frame.light_direction = frame.sun_direction;
            test_light_field = vec4<f32>(1.06, 0.74, 0.34, 0.94);
            var block: MaterialInput;
            block.albedo = plank;
            block.shaded_tint = vec4<f32>(1.0);
            block.normal = vec3<f32>(0.0, 1.0, 0.0);
            block.position = vec3<f32>(0.0, -1.0, -4.0);
            block.light = vec2<f32>(0.0, 1.0);
            let sunlit_no_torch = shade_material(block).color.r;
            block.light = vec2<f32>(0.90, 1.0);
            let sunlit_with_torch = shade_material(block).color.r;
            block.light = vec2<f32>(0.90, 0.0);
            let cave_with_torch = shade_material(block).color.r;
            frame.sun_direction = vec3<f32>(0.0, -1.0, 0.0);
            frame.light_direction = vec3<f32>(0.0, 1.0, 0.0);
            block.light = vec2<f32>(0.90, 1.0);
            let night_with_torch = shade_material(block).color.r;
            output[0] = vec4<f32>(sunlit_no_torch, sunlit_with_torch, cave_with_torch, night_with_torch);
        """)
        # Sunset-lit warm blocks must not get blown out when a torch is placed nearby.
        self.assertLess(sunlit_with_torch - sunlit_no_torch, 0.14)
        self.assertLess(sunlit_with_torch, 0.78)
        # Caves and night keep strong, punchy torch illumination.
        self.assertGreater(cave_with_torch, 0.55)
        self.assertGreater(night_with_torch, 0.55)

    def test_water_waves_extend_across_midrange_and_fade_smoothly(self):
        source = UNLIT + MATERIAL_INPUT + (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "fog.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "water.wgsl").read_text("utf-8")
        near_amp, mid_amp, far_amp, horizon_amp = self.execute(source, """
            var a_near = 0.0;
            var a_mid = 0.0;
            var a_far = 0.0;
            var a_horizon = 0.0;
            for (var i = 0u; i < 8u; i++) {
                let p = vec2<f32>(f32(i) * 3.7 + 1.5, f32(i) * 2.3 + 4.1);
                a_near += length(water_ripple_slope(p, 5.0, 0.05));
                a_mid += length(water_ripple_slope(p, 5.0, 0.40));
                a_far += length(water_ripple_slope(p, 5.0, 1.40));
                a_horizon += length(water_ripple_slope(p, 5.0, 3.00));
            }
            output[0] = vec4<f32>(a_near, a_mid, a_far, a_horizon) / 8.0;
        """)
        self.assertGreater(near_amp, mid_amp)
        self.assertGreater(mid_amp, 0.04)
        self.assertGreater(far_amp, 0.01)
        self.assertLess(far_amp, mid_amp)
        self.assertLess(horizon_amp, 0.0001)

    def test_dense_storm_cloud_casts_a_deep_shadow(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        surface, above, opacity, _ = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.rain = 1.0;
            frame.thunder = 1.0;
            var shaded = 1.0;
            var peak_opacity = 0.0;
            for (var i = 0u; i < 16u; i++) {
                frame.camera_position = vec3<f32>(f32(i % 4u) * 260.0, 80.0, f32(i / 4u) * 260.0);
                shaded = min(shaded, cloud_light_transmission(vec3<f32>(0.0), frame.sun_direction));
                peak_opacity = max(peak_opacity, cloud_volume(frame.camera_position, frame.sun_direction, 1.0, 16u).a);
            }
            let exposed = cloud_light_transmission(vec3<f32>(0.0, 720.0, 0.0), frame.sun_direction);
            output[0] = vec4<f32>(shaded, exposed, peak_opacity, 0.0);
        """)
        self.assertLess(surface, 0.22)
        self.assertAlmostEqual(above, 1.0)
        self.assertGreater(opacity, 0.72)

    def test_distant_storm_clouds_fade_into_the_horizon(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        near, far, _, _ = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            var near = 0.0;
            for (var i = 0u; i < 8u; i++) {
                near = max(near, cloud_volume(vec3<f32>(f32(i) * 180.0, 80.0, 165.0), frame.sun_direction, 1.0, 12u).a);
            }
            let ray = normalize(vec3<f32>(1.0, 0.010, 0.0));
            var far = 0.0;
            for (var sample = 0u; sample < 8u; sample++) {
                let origin = vec3<f32>(110.0, 80.0, f32(sample) * 128.0);
                far = max(far, cloud_volume(origin, ray, 1.0, 12u).a);
            }
            output[0] = vec4<f32>(near, far, 0.0, 0.0);
        """)
        self.assertGreater(near, 0.70)
        self.assertLess(far, 0.12)

    def test_grazing_cloud_volume_fades_out_before_the_horizon(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        grazing, near, _, _ = self.execute(source, """
            frame.sun_direction.y = 1.0;
            let ray = normalize(vec3<f32>(1.0, 0.008, 0.0));
            var grazing = 0.0;
            var near = 0.0;
            for (var i = 0u; i < 12u; i++) {
                let origin = vec3<f32>(154.0, 110.0, f32(i) * 120.0);
                grazing = max(grazing, cloud_volume(origin, ray, 1.0, CLOUD_SKY_STEPS).a);
                near = max(near, cloud_volume(origin, frame.sun_direction, 1.0, CLOUD_SKY_STEPS).a);
            }
            output[0] = vec4<f32>(grazing, near, 0.0, 0.0);
        """)
        self.assertLess(grazing, 0.08)
        self.assertGreater(near, 0.70)

    def test_low_sun_shadow_matches_the_cloud_in_front_of_the_sun(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        error, dense, open, _ = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.9551, 0.296, 0.0));
            frame.rain = 1.0;
            var error = 0.0;
            var dense = 1.0;
            var open = 0.0;
            for (var i = 0u; i < 64u; i++) {
                frame.camera_position = vec3<f32>(1865.0 + f32(i % 8u) * 240.0, 75.0, 1109.0 + f32(i / 8u) * 260.0);
                let shadow = cloud_light_transmission(vec3<f32>(0.0), frame.sun_direction);
                let glow = clouded_sky(vec3<f32>(0.0), frame.camera_position, frame.sun_direction, 1.0);
                let lit = clouded_sky(vec3<f32>(1.0), frame.camera_position, frame.sun_direction, 1.0);
                let disk = lit.r - glow.r;
                error = max(error, abs(shadow - disk));
                dense = min(dense, disk);
                open = max(open, disk);
            }
            output[0] = vec4<f32>(error, dense, open, 0.0);
        """)
        self.assertLess(dense, 0.16)
        self.assertGreater(open, dense + 0.06)
        self.assertLess(error, 0.015)

    def test_cloud_volume_has_thickness_and_warm_to_pink_scattering(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        center, above, warm, twilight = self.execute(source, """
            let direction = normalize(vec3<f32>(-1.0, 0.48, 0.0));
            let base = vec3<f32>(0.0);
            var center = 0.0;
            var warm_sum = vec3<f32>(0.0);
            var pink_sum = vec3<f32>(0.0);
            for (var i = 0u; i < 16u; i++) {
                let sample_p = vec3<f32>(f32(i % 4u) * 260.0, CLOUD_HEIGHT, f32(i / 4u) * 260.0);
                center = max(center, cloud_density(sample_p, 1.0, 0.0));
                let origin = vec3<f32>(sample_p.x, 80.0, sample_p.z);
                frame.sun_direction = normalize(vec3<f32>(-1.0, 0.27, 0.0));
                warm_sum += clouded_sky(base, origin, direction, 1.0);
                frame.sun_direction = normalize(vec3<f32>(-1.0, 0.02, 0.0));
                pink_sum += clouded_sky(base, origin, direction, 1.0);
            }
            let above = cloud_density(vec3<f32>(161.0, CLOUD_HEIGHT + 120.0, 165.0), 1.0, 0.0);
            output[0] = vec4<f32>(center, above,
                warm_sum.b / max(warm_sum.g, 0.001), pink_sum.b / max(pink_sum.g, 0.001));
        """)
        self.assertGreater(center, 0.1)
        self.assertEqual(above, 0.0)
        self.assertTrue(0.05 < warm < 1.0)
        self.assertGreater(twilight, 1.08)

    def test_cloud_density_varies_dynamically_across_sky_and_time(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        spatial_span, time_span, wrap_err, _ = self.execute(source, """
            var s_min = 1.0;
            var s_max = 0.0;
            for (var i = 0u; i < 64u; i++) {
                let xz = vec2<f32>(f32(i % 8u) * 512.0, f32(i / 8u) * 512.0);
                let cov = cloud_macro_coverage(xz, 0.0);
                s_min = min(s_min, cov);
                s_max = max(s_max, cov);
            }
            frame.time = 0.0;
            let t0 = cloud_macro_coverage(vec2<f32>(1200.0, 800.0), 0.0);
            var t_min = t0;
            var t_max = t0;
            for (var s = 1u; s <= 6u; s++) {
                frame.time = f32(s) * 200.0;
                let cov = cloud_macro_coverage(vec2<f32>(1200.0, 800.0), 0.0);
                t_min = min(t_min, cov);
                t_max = max(t_max, cov);
            }
            frame.time = 3600.0;
            let t_wrap = cloud_macro_coverage(vec2<f32>(1200.0, 800.0), 0.0);
            output[0] = vec4<f32>(s_max - s_min, t_max - t_min, abs(t_wrap - t0), 0.0);
        """)
        self.assertGreater(spatial_span, 0.25)
        self.assertGreater(time_span, 0.12)
        self.assertAlmostEqual(wrap_err, 0.0, places=5)

    def test_twilight_dusk_clouds_carry_purple_magenta_violet_lighting(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        r_over_g, b_over_g, dusk_luma, _ = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(-1.0, -0.04, 0.0));
            let dir = normalize(vec3<f32>(-0.92, 0.34, 0.18));
            var accum = vec3<f32>(0.0);
            var weight = 0.0;
            for (var i = 0u; i < 16u; i++) {
                let origin = vec3<f32>(f32(i % 4u) * 320.0, 80.0, f32(i / 4u) * 320.0);
                let c = cloud_volume(origin, dir, 0.0, CLOUD_SKY_STEPS);
                accum += c.rgb;
                weight += c.a;
            }
            let avg = accum / max(weight, 0.0001);
            output[0] = vec4<f32>(avg.r / max(avg.g, 0.0001), avg.b / max(avg.g, 0.0001),
                dot(avg, vec3<f32>(0.2126, 0.7152, 0.0722)), 0.0);
        """)
        self.assertGreater(r_over_g, 1.35)
        self.assertGreater(b_over_g, 1.25)
        self.assertGreater(dusk_luma, 0.03)

    def test_cloud_columns_have_one_continuous_body(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        separated, occupied, outside, _ = self.execute(source, """
            var separated = 0.0;
            var occupied = 0.0;
            for (var i = 0u; i < 196u; i++) {
                var position = vec3<f32>(f32(i % 14u) * 95.0, 0.0, f32(i / 14u) * 95.0);
                var bodies = 0u;
                var inside = false;
                for (var y = 225; y <= 335; y += 3) {
                    position.y = f32(y);
                    let dense = cloud_density(position, 0.35, 16.0) > 0.06;
                    bodies += u32(dense && !inside);
                    inside = dense;
                }
                separated += f32(bodies > 1u);
                occupied += f32(bodies > 0u);
            }
            let outside = cloud_density(vec3<f32>(0.0, 355.0, 0.0), 1.0, 4.0);
            output[0] = vec4<f32>(separated, occupied, outside, 0.0);
        """)
        self.assertEqual(separated, 0.0)
        self.assertTrue(40 < occupied < 185)
        self.assertEqual(outside, 0.0)

    def test_three_vertical_cloud_layers_render_from_ground_and_altitude(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        l1_hit, l2_hit, l3_hit, down_from_top = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(-0.85, 0.35, 0.10));
            let pal = build_cloud_palette(vec3<f32>(0.0, 1.0, 0.0), 0.0);
            var l1 = 0.0;
            var l2 = 0.0;
            var l3 = 0.0;
            var below = 0.0;
            for (var i = 0u; i < 16u; i++) {
                let xz = vec2<f32>(f32(i % 4u) * 320.0, f32(i / 4u) * 320.0);
                let ground = vec3<f32>(xz.x, 80.0, xz.y);
                let mid = vec3<f32>(xz.x, 468.0, xz.y);
                let high = vec3<f32>(xz.x, 689.0, xz.y);
                l1 = max(l1, cloud_march_layer(ground, vec3<f32>(0.0, 1.0, 0.0), 0.0,
                    CLOUD_L1_BASE, CLOUD_L1_THICKNESS, CLOUD_SKY_STEPS, true, false, pal).a);
                l2 = max(l2, cloud_march_layer(ground, vec3<f32>(0.0, 1.0, 0.0), 0.0,
                    CLOUD_L2_BASE, CLOUD_L2_THICKNESS, CLOUD_L2_STEPS, true, true, pal).a);
                l3 = max(l3, cloud_cirrus_layer(mid, vec3<f32>(0.0, 1.0, 0.0), 0.0, pal).a);
                below = max(below, cloud_volume(high, normalize(vec3<f32>(0.6, -0.5, 0.6)), 0.0, CLOUD_SKY_STEPS).a);
            }
            output[0] = vec4<f32>(l1, l2, l3, below);
        """)
        self.assertGreater(l1_hit, 0.55)
        self.assertGreater(l2_hit, 0.30)
        self.assertGreater(l3_hit, 0.10)
        self.assertGreater(down_from_top, 0.50)

    def test_planar_cloud_blend_preserves_reflected_terrain(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog", "water")) + UNLIT
        sky_change, terrain_change, dimension_change, _ = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.rain = 0.6;
            frame.sky_color = vec3<f32>(0.18, 0.35, 0.62);
            frame.fog_color = vec3<f32>(0.44, 0.55, 0.65);
            let sky = mix(frame.sky_color, frame.fog_color, 0.3);
            let terrain = vec3<f32>(0.12, 0.23, 0.06);
            let point = vec3<f32>(161.0, 63.0, 165.0);
            let ray = vec3<f32>(0.0, 1.0, 0.0);
            let reflected_sky = water_environment(sky, sky, 1.0, point, ray);
            let reflected_terrain = water_environment(sky, terrain, 1.0, point, ray);
            frame.dimension = 1;
            let other_dimension = water_environment(sky, sky, 1.0, point, ray);
            output[0] = vec4<f32>(length(reflected_sky - sky),
                length(reflected_terrain - terrain), length(other_dimension - sky), 0.0);
        """)
        self.assertGreater(sky_change, 0.03)
        self.assertAlmostEqual(terrain_change, 0.0, places=5)
        self.assertEqual(dimension_change, 0.0)

    def test_cloud_ray_tracks_the_bobbed_world_projection(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += "\n" + (ROOT / "horizon_lighting" / "sky.wgsl").read_text("utf-8")
        code = "struct SkyInput { direction: vec3<f32>, color: vec4<f32> }\n" + source
        center_error, direction_error, ray_shift, no_bob_error = self.execute(code, """
            let lens = mat4x4<f32>(vec4<f32>(1.25, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.8, 0.0, 0.0), vec4<f32>(0.0, 0.0, 0.0, -1.0),
                vec4<f32>(0.0, 0.0, 0.05, 0.0));
            let inverse_lens = mat4x4<f32>(vec4<f32>(0.8, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0 / 1.8, 0.0, 0.0), vec4<f32>(0.0, 0.0, 0.0, 20.0),
                vec4<f32>(0.0, 0.0, -1.0, 0.0));
            let roll = 0.08;
            let c = cos(roll);
            let s = sin(roll);
            frame.view = mat4x4<f32>(vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0, 0.0, 0.0), vec4<f32>(0.0, 0.0, 1.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0));
            frame.view_inverse = frame.view;
            let shift = vec3<f32>(0.15, -0.09, 0.0);
            let inverse_bob = mat4x4<f32>(vec4<f32>(c, -s, 0.0, 0.0),
                vec4<f32>(s, c, 0.0, 0.0), vec4<f32>(0.0, 0.0, 1.0, 0.0), vec4<f32>(shift, 1.0));
            let bob = mat4x4<f32>(vec4<f32>(c, s, 0.0, 0.0),
                vec4<f32>(-s, c, 0.0, 0.0), vec4<f32>(0.0, 0.0, 1.0, 0.0),
                vec4<f32>(-c * shift.x + s * shift.y, -s * shift.x - c * shift.y, 0.0, 1.0));
            frame.projection = lens * bob;
            frame.projection_inverse = inverse_bob * inverse_lens;
            let unbobbed = normalize(vec3<f32>(0.3, 0.25, -1.0));
            let ray = cloud_view_ray(unbobbed);
            let source_clip = lens * vec4<f32>(unbobbed, 0.0);
            let cloud_clip = frame.projection * vec4<f32>(ray.origin + ray.direction * 300.0, 1.0);
            frame.projection = lens;
            frame.projection_inverse = inverse_lens;
            let still = cloud_view_ray(unbobbed);
            output[0] = vec4<f32>(length(ray.origin - shift),
                length(cloud_clip.xy / cloud_clip.w - source_clip.xy / source_clip.w),
                length(ray.direction - unbobbed), length(still.direction - unbobbed));
        """)
        self.assertAlmostEqual(center_error, 0.0, places=5)
        self.assertAlmostEqual(direction_error, 0.0, places=5)
        self.assertGreater(ray_shift, 0.015)
        self.assertAlmostEqual(no_bob_error, 0.0, places=5)

    def test_wide_cloud_steps_filter_out_unresolved_detail(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        close, far, _, _ = self.execute(source, """
            var close = 0.0;
            var far = 0.0;
            for (var i = 0u; i < 80u; i++) {
                let p = vec2<f32>(f32(i) * 40.0, 57.0);
                let q = p + vec2<f32>(40.0, 0.0);
                close += abs(cloud_column(p, 0.1, 4.0) - cloud_column(q, 0.1, 4.0));
                far += abs(cloud_column(p, 0.1, 160.0) - cloud_column(q, 0.1, 160.0));
            }
            output[0] = vec4<f32>(close, far, 0.0, 0.0);
        """)
        self.assertGreater(close, 3.0)
        self.assertLess(far, close * 0.65)

    def test_open_soil_sides_keep_pigment_and_sheltered_soil_stays_dark(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        east, north, warmth, sheltered = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.light_direction = frame.sun_direction;
            shadow = 0.0;
            var soil: MaterialInput;
            soil.material = 41u;
            soil.albedo = vec4<f32>(0.24, 0.11, 0.055, 1.0);
            soil.light.y = 1.0;
            soil.normal.x = 1.0;
            soil.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            let east = shade_material(soil).color.rgb;
            soil.normal = vec3<f32>(0.0, 0.0, 1.0);
            soil.shaded_tint = vec4<f32>(vec3<f32>(pow(0.8, 2.2)), 1.0);
            let north = shade_material(soil).color.r;
            soil.light.y = 0.25;
            let sheltered = shade_material(soil).color.r;
            output[0] = vec4<f32>(east.r, north, east.r / east.b, sheltered);
        """, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        self.assertTrue(0.088 < east < 0.14, east)
        self.assertGreater(east, north * 0.72)
        self.assertGreater(warmth, 3.25)
        self.assertLess(sheltered, east * 0.15)

    def test_high_sun_separates_lit_faces_from_ambient_shade(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        value = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.43, 0.902829, 0.0);
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.5, 0.5, 0.5, 1.0);
            block.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            block.light.y = 1.0;
            block.normal = vec3<f32>(1.0, 0.0, 0.0);
            let lit = shade_material(block).color.rgb;
            block.normal = -block.normal;
            let away = shade_material(block).color.rgb;
            shadow = 0.0;
            block.normal = -block.normal;
            let shaded = shade_material(block).color.rgb;
            block.light.y = 0.0;
            let cave = shade_material(block).color.r;
            output[0] = vec4<f32>(lit.r, away.r, shaded.b / shaded.r, cave);
        """)
        self.assertGreater(value[0], 0.23)
        self.assertTrue(0.10 < value[1] < value[0] * 0.70, value[:2])
        self.assertGreater(value[2], 1.18)
        self.assertLess(value[3], 0.01)

    def test_golden_hour_lights_neutral_surfaces_and_clouds_with_visible_warmth(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        sunrise, sunset, cloud_blue, noon = self.execute(source, """
            let point = vec3<f32>(161.0, 176.0, 165.0);
            frame.sun_direction = vec3<f32>(0.9474, 0.32, 0.0);
            frame.light_direction = frame.sun_direction;
            let sunrise = shade_surface(point, frame.light_direction, 1.0, vec3<f32>(0.5),
                0.0, vec3<f32>(0.0), false, false, 0.0);
            frame.sun_direction.x = -frame.sun_direction.x;
            frame.light_direction = frame.sun_direction;
            let sunset = shade_surface(point, frame.light_direction, 1.0, vec3<f32>(0.5),
                0.0, vec3<f32>(0.0), false, false, 0.0);
            var cloud = vec3<f32>(0.0);
            for (var i = 0u; i < 8u; i++) {
                let origin = vec3<f32>(161.0 + f32(i) * 240.0, 80.0, 165.0);
                cloud += clouded_sky(vec3<f32>(0.0), origin, frame.sun_direction, 1.0);
            }
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            let noon = solar_radiance();
            output[0] = vec4<f32>(sunrise.b / sunrise.r, sunset.b / sunset.r,
                cloud.b / max(cloud.r, 0.001), noon.b / noon.r);
        """)
        self.assertLess(sunrise, 0.34)
        self.assertLess(sunset, sunrise - 0.025)
        self.assertTrue(0.05 < cloud_blue < 0.70)
        self.assertAlmostEqual(noon, 0.86, delta=0.0001)

    def test_water_colour_and_opacity_ignore_the_vanilla_sprite(self):
        source = UNLIT + MATERIAL_INPUT + (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "gloss.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "fog.wgsl").read_text("utf-8")
        source += production_function("lighting.wgsl", "respect_effects")
        water_file = ROOT / "horizon_lighting" / "water.wgsl"
        if water_file.exists():
            source += water_file.read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "material.wgsl").read_text("utf-8")
        outputs = []
        for sprite, tint in [('1.0, 0.0, 0.0, 0.1', '1.0, 1.0, 1.0, 1.0'),
                             ('0.0, 0.0, 1.0, 0.9', '0.2, 0.7, 0.3, 0.5')]:
            outputs.append(self.execute(source, f"""
                frame.dimension = 0;
                frame.sky_color = vec3<f32>(0.2, 0.3, 0.5);
                frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
                frame.light_direction = frame.sun_direction;
                let identity = mat4x4<f32>(vec4<f32>(1.0,0.0,0.0,0.0),
                    vec4<f32>(0.0,1.0,0.0,0.0), vec4<f32>(0.0,0.0,1.0,0.0), vec4<f32>(0.0,0.0,0.0,1.0));
                frame.view = identity; frame.view_inverse = identity; frame.projection_inverse = identity;
                var input: MaterialInput;
                input.albedo = vec4<f32>({sprite}); input.shaded_tint = vec4<f32>({tint});
                input.position = vec3<f32>(0.0,-1.0,-3.0);
                input.normal = vec3<f32>(0.0,1.0,0.0); input.tangent = vec4<f32>(1.0,0.0,0.0,1.0);
                input.lightmap = vec3<f32>(0.8); input.light = vec2<f32>(0.0,1.0);
                input.fluid = 1u; input.translucent = true; input.face = 1u; input.screen = vec2<f32>(0.5);
                output[0] = shade_material(input).color;
            """))
        for actual, target in zip(outputs[0], outputs[1]):
            self.assertAlmostEqual(actual, target, delta=0.00002)
        self.assertAlmostEqual(outputs[0][3], 1.0, delta=0.00002)

    def test_water_normals_counter_scroll_freeze_and_wrap(self):
        source = UNLIT + MATERIAL_INPUT + (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "fog.wgsl").read_text("utf-8")
        source += (ROOT / "horizon_lighting" / "water.wgsl").read_text("utf-8")
        body = """
            let position = vec2<f32>(12.3, 8.5);
            let a = water_ripple_slope(position, 0.0, 0.0);
            let b = water_ripple_slope(position, 3.0, 0.0);
            let far = water_ripple_slope(position, 3.0, 3.0);
            let end = water_ripple_slope(position, 3600.0, 0.0);
            output[0] = vec4<f32>(b - a, length(far), length(end - a));
        """
        moving = self.execute(source, body)
        frozen = self.execute(source, body, {"water_speed": 0.0})
        self.assertGreater(abs(moving[0]) + abs(moving[1]), 0.001)
        self.assertLess(abs(frozen[0]) + abs(frozen[1]), 0.000001)
        self.assertLess(moving[2], 0.000001)
        fractional_speed = self.execute(source, body, {"water_speed": 1.37})
        self.assertLess(fractional_speed[3], 0.000001)

        # Two equal-and-opposite translations give the same sum when sampled across
        # space at a fixed time or across time at a fixed position.
        counter_scroll = self.execute(source, """
            let position = vec2<f32>(12.3, 8.5);
            let time = 120.0;
            let dt = 12.0;
            let shift = vec2<f32>(144.0, 48.0) * water_speed * (dt / (3600.0 * 0.17));
            let across_space = water_ripple_slope(position + shift, time, 0.0)
                + water_ripple_slope(position - shift, time, 0.0);
            let across_time = water_ripple_slope(position, time + dt, 0.0)
                + water_ripple_slope(position, time - dt, 0.0);
            output[0] = vec4<f32>(across_space - across_time, 0.0, 0.0);
        """)
        self.assertAlmostEqual(counter_scroll[0], 0.0, delta=0.002)
        self.assertAlmostEqual(counter_scroll[1], 0.0, delta=0.002)

    def test_cave_water_keeps_background_clear_and_side_faces_visible(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water"))
        body = """
            frame.sky_color = vec3<f32>(1.0, 1.0, 3.0);
            frame.sun_direction.y = 1.0;
            frame.light_direction = frame.sun_direction;
            var water: MaterialInput;
            water.screen = vec2<f32>(0.5);
            water.light = vec2<f32>(0.5, 0.0);
            water.face = 1u;
            water.position = vec3<f32>(1.0, -0.2, -5.0);
            water.normal = vec3<f32>(0.0, 1.0, 0.0);
            let top = shade_water(water).color;
            water.face = 3u;
            water.normal = vec3<f32>(0.0, 0.0, 1.0);
            water.tangent = vec4<f32>(1.0, 0.0, 0.0, 1.0);
            let side = shade_water(water).color;
            frame.time = 2.5;
            let later = shade_water(water).color;
        """
        value = self.execute(source, body + "output[0] = vec4<f32>(top.rgb, side.a);")
        side = self.execute(source, body + "output[0] = vec4<f32>(side.rgb, length(later - side));")
        transmission = [actual / (target / 255) for actual, target in zip(value[:3], (70, 100, 115))]
        self.assertTrue(0.55 < transmission[0] < 0.85)
        for channel in transmission[1:]:
            self.assertAlmostEqual(channel, transmission[0], delta=0.00002)
        self.assertTrue(0.20 < value[3] < 0.6)
        self.assertGreater(side[2], side[0] + 0.004)
        self.assertLess(side[2], 0.04)
        self.assertAlmostEqual(side[3], 0.0, places=5)

    def test_underwater_entities_match_the_terrain_haze(self):
        source = ENTITY_INPUT + MATERIAL_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material", "entity"))
        difference, blue, alpha, distant_error = self.execute(source, """
            frame.eye_in = 1u;
            frame.sun_direction.y = 1.0;
            frame.light_direction = frame.sun_direction;
            frame.eye_light_smooth.y = 1.0;
            frame.fog_color = vec3<f32>(0.0, 0.1, 1.0);
            frame.fog_environment = vec2<f32>(-8.0, 72.0);
            var mob: EntityInput;
            mob.albedo = vec4<f32>(0.21, 0.17, 0.08, 0.7);
            mob.tint = vec4<f32>(1.0);
            mob.light.y = 1.0;
            mob.normal.y = 1.0;
            mob.position.z = -16.0;
            let entity_colour = entity(mob).color;
            let lit = shade_surface(mob.position, mob.normal, mob.light.y, mob.albedo.rgb, 0.0,
                vec3<f32>(0.0), false, false, 0.0);
            let terrain = surface_fog(lit, mob.position);
            frame.eye_light_smooth.y = 0.0;
            mob.position.z = -160.0;
            let distant = entity(mob).color.rgb;
            output[0] = vec4<f32>(length(entity_colour.rgb - terrain), entity_colour.b, entity_colour.a,
                length(distant - underwater_haze()));
        """)
        self.assertAlmostEqual(difference, 0.0, places=5)
        self.assertLess(blue, 0.25)
        self.assertAlmostEqual(alpha, 0.7, places=5)
        self.assertLess(distant_error, 0.005)

    def test_cloud_layer_has_gaps_in_clear_weather_and_rain(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        clear, rain, rain_gaps, clear_gaps = self.execute(source, """
            frame.sun_direction.y = 1.0;
            var totals = vec4<f32>(0.0);
            for (var i = 0u; i < 144u; i++) {
                let origin = vec3<f32>(f32(i % 12u) * 340.0, 80.0, f32(i / 12u) * 340.0);
                let clear = cloud_volume(origin, frame.sun_direction, 0.0, CLOUD_SKY_STEPS).a;
                let rain = cloud_volume(origin, frame.sun_direction, 1.0, CLOUD_SKY_STEPS).a;
                let overcast = storm_deck_opacity(origin, frame.sun_direction, 1.0);
                totals += vec4<f32>(clear, mix(rain, 1.0, overcast), f32(rain < 0.35), f32(clear < 0.10));
            }
            output[0] = totals / 144.0;
        """)
        self.assertTrue(0.18 < clear < 0.55)
        self.assertTrue(0.65 < rain < 0.94)
        self.assertGreater(clear_gaps, 0.28)
        self.assertGreater(clear_gaps, rain_gaps)

    def test_twilight_dims_the_sky_and_shifts_sunward_glow_to_pink(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        for side in (-1, 1):
            with self.subTest(side=side):
                warm, pink, core, dimming = self.execute(source, f"""
                    let direction = vec3<f32>({side}.0, 0.0, 0.0);
                    let shoulder = normalize(direction + vec3<f32>(0.0, 0.0, 0.48));
                    let up = vec3<f32>(0.0, 1.0, 0.0);
                    frame.sun_direction = up;
                    let noon = overworld_sky_radiance(up);
                    frame.sun_direction = normalize(direction + up * 0.14);
                    let warm = golden_sky_glow(shoulder);
                    frame.sun_direction = normalize(direction + up * 0.02);
                    let pink = golden_sky_glow(shoulder);
                    let core = golden_sky_glow(frame.sun_direction);
                    let twilight = overworld_sky_radiance(up);
                    output[0] = vec4<f32>(warm.b / warm.g, pink.b / pink.g, core.b / core.g, twilight.g / noon.g);
                """)
                self.assertLess(warm, 0.65)
                self.assertGreater(pink, 1.15)
                self.assertLess(core, 0.70)
                self.assertLess(dimming, 0.30)

    def test_grass_blocks_keep_green_pigment_and_reflect_when_wet(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = vec3<f32>(0.953939, 0.30, 0.0);
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.20, 0.31, 0.09, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.material = 41u;
            // Sample the pigment outside the sun's specular highlight.
            block.position = vec3<f32>(7.0, -2.4, 4.0);
            block.normal.y = 1.0;
            let lit = shade_material(block).color.rgb;
            let coating = select(0.0, test_surface_smoothness, test_surface_data < 0.0);
            output[0] = vec4<f32>(lit, coating);
        """
        dry = self.execute(source, body)
        wet = self.execute(source, body, {"wet_in_clear": True})
        self.assertGreater(dry[1], 1.25 * dry[0])
        self.assertGreater(wet[1], 1.25 * wet[0])
        self.assertLess(wet[1], dry[1])
        self.assertEqual(dry[3], 0.0)
        self.assertGreater(wet[3], 0.65)

    def test_grass_root_contact_shade_follows_the_sprite_and_can_be_disabled(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        body = """
            var grass: MaterialInput;
            grass.albedo = vec4<f32>(0.28, 0.43, 0.12, 0.74);
            grass.shaded_tint = vec4<f32>(1.0);
            grass.material = 40u;
            grass.tags = 1u;
            grass.uv.y = 0.95;
            let root = material(grass).color;
            grass.uv.y = 0.35;
            let tip = material(grass).color.g;
            grass.tags = 0u;
            grass.uv.y = 0.95;
            let upper_plant = material(grass).color.g;
            output[0] = vec4<f32>(root.g, tip, upper_plant, root.a);
        """
        root, tip, upper_plant, alpha = self.execute(source, body)
        self.assertTrue(0.38 < root / tip < 0.58)
        self.assertAlmostEqual(tip, 0.43, delta=0.00002)
        self.assertAlmostEqual(upper_plant, tip, delta=0.00002)
        self.assertAlmostEqual(alpha, 0.74, delta=0.00002)
        off = self.execute(source, body, {"contact_ao": False})
        self.assertAlmostEqual(off[0], tip, delta=0.00002)

    def test_daylight_keeps_green_terrain_colorful_without_recoloring_stone(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        blue, red, green, neutral = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.28, 0.96, 0.0);
            frame.light_direction = frame.sun_direction;
            let position = vec3<f32>(0.0);
            let up = vec3<f32>(0.0, 1.0, 0.0);
            let grass = shade_surface(position, up, 1.0, vec3<f32>(0.18, 0.30, 0.13),
                0.0, position, false, true, 1.0);
            let stone = shade_surface(position, up, 1.0, vec3<f32>(0.30),
                0.0, position, false, false, 1.0);
            output[0] = vec4<f32>(grass.b / grass.g, grass.r / grass.g, grass.g, stone.b / stone.r);
        """, {"procedural_clouds": False})
        self.assertTrue(0.28 < blue < 0.40, blue)
        self.assertTrue(0.45 < red < 0.68, red)
        self.assertGreater(green, 0.4)
        self.assertTrue(0.86 < neutral < 1.10, neutral)

    def test_vegetation_keeps_its_original_biome_pigment_at_noon_and_night(self):
        source = UNLIT + MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "water", "material"))
        source += production_function("lighting.wgsl", "respect_effects")
        value = self.execute(source, """
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.44, 0.60, 0.22, 0.7);
            block.shaded_tint = vec4<f32>(0.45, 0.72, 0.23, 1.0);
            block.normal.y = 1.0;
            frame.sun_direction.y = 1.0;
            block.material = 40u;
            let grass = material(block).color;
            block.material = 42u;
            let noon = material(block).color;
            frame.sun_direction.y = -1.0;
            let night = material(block).color;
            let pigment = block.albedo.rgb * block.shaded_tint.rgb;
            output[0] = vec4<f32>(distance(grass.rgb, pigment), distance(noon.rgb, pigment),
                distance(night.rgb, pigment), night.a);
        """)
        for error in value[:3]:
            self.assertAlmostEqual(error, 0.0, delta=0.00002)
        self.assertAlmostEqual(value[3], 0.7, delta=0.00002)

    def test_experimental_fog_is_optional_and_respects_start_distance_and_medium(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        body = """
            frame.sun_direction.y = 1.0;
            frame.eye_light_smooth.y = 1.0;
            let scene = vec3<f32>(0.04, 0.12, 0.03);
            let near = apply_custom_fog(scene, 12.0);
            let far = apply_custom_fog(scene, 96.0);
            frame.eye_in = 1u;
            let underwater = apply_custom_fog(scene, 96.0);
            output[0] = vec4<f32>(length(near - scene), far.r, far.b, length(underwater - scene));
        """
        disabled = self.execute(source, body)
        cool = self.execute(source, body, {"custom_fog": True, "custom_fog_tint": 2})
        warm = self.execute(source, body, {"custom_fog": True, "custom_fog_tint": 1})
        self.assertAlmostEqual(disabled[1], 0.04, delta=0.00002)
        self.assertAlmostEqual(disabled[2], 0.03, delta=0.00002)
        self.assertEqual((cool[0], cool[3]), (0.0, 0.0))
        self.assertGreater(cool[2], cool[1])
        self.assertGreater(warm[1], warm[2])

    def test_air_shafts_keep_surface_colour_under_strong_amber_scattering(self):
        source = production_function("post/composite.wgsl", "apply_air_shafts_headroom")
        source += "\n" + production_function("post/composite.wgsl", "apply_air_shafts")
        value = self.execute(source, """
            let grass = vec3<f32>(0.035, 0.21, 0.025);
            let combined = apply_air_shafts(grass, vec3<f32>(0.22, 0.09, 0.015), 0.85);
            let dark = apply_air_shafts(vec3<f32>(0.0), vec3<f32>(0.22, 0.09, 0.015), 0.85);
            output[0] = vec4<f32>(combined.g / combined.r, combined.g - grass.g, dark.r, 1.0);
        """)
        self.assertGreater(value[0], 3.0)
        self.assertGreater(value[1], 0.0)
        self.assertLessEqual(value[2], 0.03061)

    def test_sun_shaft_slider_changes_already_bright_beams(self):
        source = production_function("post/composite.wgsl", "apply_air_shafts_headroom")
        source += "\n" + production_function("post/composite.wgsl", "apply_air_shafts")
        off, low, high, stronger_beam = self.execute(source, """
            let wall = vec3<f32>(0.03);
            let beam = vec3<f32>(0.10, 0.07, 0.04);
            let off = apply_air_shafts(wall, beam, 0.0).r - wall.r;
            let low = apply_air_shafts(wall, beam, 0.45).r - wall.r;
            let high = apply_air_shafts(wall, beam, 1.8).r - wall.r;
            let stronger_beam = apply_air_shafts(wall, beam * 2.0, 1.8).r - wall.r;
            output[0] = vec4<f32>(off, low, high, stronger_beam);
        """)
        self.assertEqual(off, 0.0)
        self.assertGreater(low, 0.01)
        self.assertGreater(high, low * 3.5)
        self.assertGreater(stronger_beam, high)

    def test_distant_shadow_does_not_fade_to_full_low_sun(self):
        source = "override quality_preset: u32 = 1u;\nconst PRESET_LITE: u32 = 0u;\nconst PRESET_BALANCED: u32 = 1u;\n"
        source += (ROOT / "horizon_lighting" / "shadow.wgsl").read_text("utf-8")
        source = source.replace("fn shadow_visibility(", "fn terrain_shadow_visibility(")
        source = source.replace("textureSampleCompareLevel(shadow_map, shadow_sampler,", "compare_shadow(")
        source += production_function("common.wgsl", "sun_presence") + "\n" + """
fn compare_shadow(uv: vec2<f32>, depth: f32) -> f32 { return shadow; }
fn shadow_distort(xy: vec2<f32>) -> vec2<f32> {
    let k = frame.shadow_distortion;
    return xy / (length(xy) * k + 1.0 - k);
}
"""
        edge, past_edge, past_corner, noon = self.execute(source, """
            frame.has_shadow = 1u;
            frame.shadow_distance = 96.0;
            frame.shadow_resolution = 2048.0;
            frame.shadow_distortion = 0.67;
            frame.shadow_view_proj = mat4x4<f32>(vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0, 0.0, 0.0), vec4<f32>(0.0, 0.0, 1.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0));
            frame.sun_direction.y = 0.10;
            shadow = 0.0;
            let normal = vec3<f32>(0.0, 0.0, 1.0);
            let edge = terrain_shadow_visibility(vec3<f32>(0.85, 0.0, 0.5), normal);
            let past_edge = terrain_shadow_visibility(vec3<f32>(1.05, 0.0, 0.5), normal);
            let past_corner = terrain_shadow_visibility(vec3<f32>(1.05, 0.97, 0.5), normal);
            frame.sun_direction.y = 1.0;
            let noon = terrain_shadow_visibility(vec3<f32>(1.05, 0.0, 0.5), normal);
            output[0] = vec4<f32>(edge, past_edge, past_corner, noon);
        """)
        self.assertLess(edge, 0.05)
        self.assertGreater(past_edge, edge)
        self.assertLess(past_edge, 0.5)
        self.assertAlmostEqual(past_corner, past_edge, delta=0.00001)
        self.assertAlmostEqual(noon, 1.0, delta=0.00001)

    def test_air_shaft_integrator_respects_occlusion_and_view_depth(self):
        source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        source += "\n" + production_function("post/atmosphere.wgsl", "integrate_air_light")
        source += """
fn air_shadow_visibility(position: vec3<f32>) -> f32 {
    // An opening in the occluder lights air 10 to 22 blocks along the ray.
    return f32(position.x > 10.0 && position.x < 22.0);
}
"""
        lit, stopped, high, cloudy = self.execute(source, """
            frame.camera_position.y = 65.0;
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.2, 0.0));
            let origin = vec3<f32>(0.0);
            let ray = vec3<f32>(1.0, 0.0, 0.0);
            let lit = integrate_air_light(origin, ray, 30.0, 16, 0.5);
            let stopped = integrate_air_light(origin, ray, 8.0, 16, 0.5);
            frame.camera_position.y = 170.0;
            let high = integrate_air_light(origin, ray, 30.0, 16, 0.5);
            frame.camera_position.y = 65.0;
            frame.rain = 1.0;
            frame.thunder = 1.0;
            let cloudy = integrate_air_light(origin, ray, 30.0, 16, 0.5);
            output[0] = vec4<f32>(lit, stopped, high, cloudy);
        """, {"procedural_clouds": False})
        self.assertGreater(lit, 0.015)
        self.assertEqual(stopped, 0.0)
        self.assertLess(high, lit * 0.3)
        self.assertLess(cloudy, lit * 0.15)

    def test_moon_lights_open_terrain_and_creates_occluded_shafts(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        source += "\n" + production_function("post/atmosphere.wgsl", "integrate_air_light")
        source += """
fn air_shadow_visibility(position: vec3<f32>) -> f32 {
    return f32(position.x > 10.0 && position.x < 22.0);
}
"""
        lit, cast_shadow, air, blocked = self.execute(source, """
            frame.camera_position.y = 65.0;
            frame.moon_direction = normalize(vec3<f32>(1.0, 0.3, 0.0));
            frame.sun_direction = -frame.moon_direction;
            frame.light_direction = frame.moon_direction;
            let origin = vec3<f32>(0.0);
            let normal = vec3<f32>(1.0, 0.0, 0.0);
            let base = vec3<f32>(0.45);
            shadow = 1.0;
            let lit = shade_surface(origin, normal, 1.0, base, 0.0, origin, false, false, 0.0);
            shadow = 0.0;
            let shade = shade_surface(origin, normal, 1.0, base, 0.0, origin, false, false, 0.0);
            let air = integrate_air_light(origin, normal, 30.0, 16, 0.5) * air_shaft_strength();
            let blocked = integrate_air_light(origin, normal, 8.0, 16, 0.5);
            output[0] = vec4<f32>(lit.b, shade.b, air, blocked);
        """, {"procedural_clouds": False, "volumetrics": False})
        self.assertGreater(lit, cast_shadow + 0.025)
        self.assertGreater(air, 0.005)
        self.assertEqual(blocked, 0.0)

    def test_underwater_fog_keeps_nearby_detail_without_a_blue_cast(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        value = self.execute(source, """
            frame.eye_in = 1u;
            frame.fog_color = vec3<f32>(0.0, 0.005, 0.4);
            frame.fog_environment = vec2<f32>(0.0, 20.0);
            frame.sun_direction.y = 1.0;
            frame.eye_light_smooth.y = 0.9;
            let near = surface_fog(vec3<f32>(0.5), vec3<f32>(0.0, 0.0, -5.0));
            let far = surface_fog(vec3<f32>(0.5), vec3<f32>(0.0, 0.0, -40.0));
            output[0] = vec4<f32>(near.r, near.b - near.r, far.r, far.b - far.r);
        """)
        self.assertGreater(value[0], 0.40)
        self.assertLess(value[1], 0.02)
        self.assertLess(value[2], value[0] - 0.16)
        self.assertLess(value[3], 0.05)

    def test_aerial_perspective_respects_caves_and_status_fog(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        value = self.execute(source, """
            frame.fog_environment = vec2<f32>(24.0, 48.0);
            frame.fog_render = vec2<f32>(24.0, 48.0);
            frame.fog_color = vec3<f32>(0.8, 0.6, 0.3);
            frame.sun_direction.y = 0.08;
            let position = vec3<f32>(0.0, 0.0, -95.0);
            let material = vec3<f32>(0.13, 0.20, 0.04);
            let cave_view = surface_fog(material, position);
            frame.eye_light_smooth.y = 1.0;
            frame.blindness = 1.0;
            let blind_view = surface_fog(material, position);
            frame.blindness = 0.0;
            frame.dimension = -1;
            let nether_view = surface_fog(material, position);
            output[0] = vec4<f32>(length(cave_view - material), blind_view.r, nether_view.r, 1.0);
        """)
        self.assertAlmostEqual(value[0], 0.0, delta=0.00002)
        self.assertAlmostEqual(value[1], 0.8, delta=0.00002)
        self.assertAlmostEqual(value[2], 0.8, delta=0.00002)

    def test_contact_occlusion_is_local_and_above_the_receiver(self):
        source = production_function("post/contact_ao.wgsl", "contact_weight")
        nearby, coplanar, behind, distant = self.execute(source, """
            let normal = vec3<f32>(0.0, 1.0, 0.0);
            let nearby = contact_weight(vec3<f32>(0.10, 0.23, 0.16), normal);
            let coplanar = contact_weight(vec3<f32>(0.22, 0.0, 0.0), normal);
            let behind = contact_weight(vec3<f32>(0.10, -0.23, 0.16), normal);
            let distant = contact_weight(vec3<f32>(0.80, 0.30, 0.0), normal);
            output[0] = vec4<f32>(nearby, coplanar, behind, distant);
        """)
        self.assertGreater(nearby, 0.60)
        self.assertEqual((coplanar, behind, distant), (0.0, 0.0, 0.0))

    def test_aerial_perspective_preserves_near_color_and_layers_distant_ridges(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        near, middle, far, high = self.execute(source, """
            frame.sun_direction.y = 1.0;
            frame.eye_light_smooth.y = 1.0;
            frame.camera_position.y = 64.0;
            let foliage = vec3<f32>(0.09, 0.21, 0.05);
            let near = surface_fog(foliage, vec3<f32>(0.0, 0.0, -12.0));
            let middle = surface_fog(foliage, vec3<f32>(0.0, 0.0, -60.0));
            let far = surface_fog(foliage, vec3<f32>(0.0, 0.0, -120.0));
            frame.camera_position.y = 160.0;
            let high = surface_fog(foliage, vec3<f32>(0.0, 0.0, -120.0));
            output[0] = vec4<f32>(near.b, middle.b, far.b, high.b);
        """)
        self.assertAlmostEqual(near, 0.05, delta=0.00002)
        self.assertGreater(middle, near + 0.024)
        self.assertLess(middle, near + 0.050)
        self.assertGreater(far, middle + 0.028)
        self.assertLess(far, near + 0.15)
        self.assertLess(high, middle)

    def test_entities_share_terrain_aerial_perspective(self):
        source = ENTITY_INPUT + MATERIAL_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material", "entity"))
        body = """
            frame.camera_position.y = 64.0;
            frame.eye_light_smooth.y = 1.0;
            frame.sun_direction = vec3<f32>(0.0, 0.3, 0.953939);
            frame.light_direction = frame.sun_direction;
            var mob: EntityInput;
            mob.albedo = vec4<f32>(0.21, 0.17, 0.08, 0.7);
            mob.tint = vec4<f32>(1.0);
            mob.light.y = 1.0;
            mob.normal = vec3<f32>(0.0, 1.0, 0.0);
            mob.position = vec3<f32>(0.0, 0.0, -12.0);
            let near = entity(mob).color;
            mob.position.z = -72.0;
            let far = entity(mob).color;
            var wall: MaterialInput;
            wall.albedo = mob.albedo;
            wall.shaded_tint = mob.tint;
            wall.light = mob.light;
            wall.normal = mob.normal;
            wall.position = mob.position;
            output[0] = vec4<f32>(near.b, far.b, material(wall).color.b, far.a);
        """
        neutral = {"dry_sun_strength": 0.0}
        enabled = self.execute(source, body, neutral)
        disabled = self.execute(source, body, dict(neutral, aerial_perspective=0.0))
        self.assertAlmostEqual(enabled[0], disabled[0], delta=0.00002)
        self.assertGreater(enabled[1], disabled[1] + 0.028)
        self.assertAlmostEqual(enabled[1], enabled[2], delta=0.00002)
        self.assertAlmostEqual(disabled[1], disabled[2], delta=0.00002)
        self.assertAlmostEqual(enabled[3], 0.7, delta=0.00002)

    def test_aerial_perspective_is_warmer_toward_the_low_sun(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        towards, away, rainy, rain_density_gain = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.08, 0.0));
            frame.eye_light_smooth.y = 1.0;
            frame.camera_position.y = 64.0;
            let stone = vec3<f32>(0.09);
            let path = vec3<f32>(110.0, 0.0, 0.0);
            let towards = surface_fog(stone, path);
            let away = surface_fog(stone, vec3<f32>(-110.0, 0.0, 0.0));
            let dry = aerial_opacity(path);
            frame.rain = 1.0;
            let rainy = surface_fog(stone, path);
            output[0] = vec4<f32>(towards.r / towards.b, away.r / away.b,
                rainy.r / rainy.b, aerial_opacity(path) - dry);
        """)
        self.assertGreater(towards, away + 0.10)
        self.assertLess(rainy, towards)
        self.assertGreater(rain_density_gain, 0.0)

    def test_aerial_perspective_integrates_rays_through_the_layer_boundaries(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        below, across, above, disabled = self.execute(source, """
            frame.sun_direction.y = 1.0;
            frame.eye_light_smooth.y = 1.0;
            let stone = vec3<f32>(0.05);
            let ray = vec3<f32>(40.0, 130.0, 0.0);
            frame.camera_position.y = 170.0;
            let above = surface_fog(stone, ray);
            let across = surface_fog(stone, -ray);
            frame.camera_position.y = 40.0;
            let below = surface_fog(stone, -ray);
            frame.eye_in = 2u;
            frame.fog_environment = vec2<f32>(200.0, 1024.0);
            frame.fog_render = vec2<f32>(200.0, 1024.0);
            let disabled = surface_fog(stone, -ray);
            output[0] = vec4<f32>(below.b, across.b, above.b, disabled.b);
        """, {"aerial_perspective": 1.0})
        self.assertGreater(below, across + 0.05)
        self.assertGreater(across, above + 0.05)
        self.assertAlmostEqual(disabled, 0.05, delta=0.00002)

    def test_distant_water_transmits_the_existing_snapshot_without_air_haze(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.camera_position.y = 160.0;
            frame.eye_light_smooth.y = 1.0;
            frame.sun_direction.y = 1.0;
            var water: MaterialInput;
            water.position = vec3<f32>(0.0, -96.0, 0.0);
            water.face = 1u;
            water.normal = vec3<f32>(0.0, 1.0, 0.0);
            water.screen = vec2<f32>(0.5);
            water.light.y = 1.0;
            water.fluid = 1u;
            water.translucent = true;
            water.albedo.a = 1.0;
            output[0] = material(water).color;
        """
        opts = {"water_ripples": 0.0, "reflections": False}
        aerial = self.execute(source, body, opts)
        disabled = self.execute(source, body, dict(opts, aerial_perspective=0.0))
        for actual, old in zip(aerial[:3], disabled[:3]):
            # Only the small normal-incidence reflection gains atmospheric radiance.
            self.assertGreater(actual, old)
            self.assertLess(actual - old, 0.01)
        self.assertEqual(aerial[3], 1.0)

    def test_artistic_grade_preserves_highlight_hue_and_hdr_headroom(self):
        source = "struct TonemapInput { color: vec3<f32> }\n" + (
            ROOT / "horizon_lighting" / "tonemap.wgsl").read_text("utf-8")
        gain_ratio, sdr_peak, hdr_peak, black = self.execute(source, """
            let warm = TonemapInput(vec3<f32>(2.1, 0.84, 0.21));
            frame.headroom = 1.0;
            let sdr = tonemap(warm);
            frame.headroom = 3.0;
            let hdr = tonemap(warm);
            let black = tonemap(TonemapInput(vec3<f32>(0.0)));
            output[0] = vec4<f32>(sdr.r / sdr.g, sdr.r, hdr.r, black.r);
        """)
        self.assertAlmostEqual(gain_ratio, 2.5, delta=0.00002)
        self.assertGreater(sdr_peak, 0.9)
        self.assertLessEqual(sdr_peak, 1.0)
        self.assertGreater(hdr_peak, 1.5)
        self.assertLessEqual(hdr_peak, 3.0)
        self.assertEqual(black, 0.0)

    def test_only_selected_materials_are_glossy_and_metals_have_coloured_f0(self):
        source = (ROOT / "horizon_lighting" / "gloss.wgsl").read_text("utf-8")
        for material, smoothness, metallic in [(0, 0.0, False), (10, 0.88, True), (20, 0.72, False), (30, 0.92, False)]:
            with self.subTest(material=material):
                value = self.execute(source, f"""
                    let finish = surface_finish({material}u);
                    let f0 = decode_f0(encode_surface_data(surface_f0(vec3<f32>(0.8, 0.4, 0.1), finish.y), true, true, true, 3.1));
                    output[0] = vec4<f32>(f0, finish.x);
                """)
                self.assertAlmostEqual(value[3], smoothness, delta=0.00001)
                expected = [0.04 * 0.12 + c * 0.88 for c in (0.8, 0.4, 0.1)] if metallic else [0.04] * 3
                for actual, target in zip(value[:3], expected):
                    self.assertAlmostEqual(actual, target, delta=0.5 / 255 + 0.00001)

    def test_overworld_sky_glare_cannot_seed_bloom(self):
        source = (ROOT / "horizon_lighting/gloss.wgsl").read_text("utf-8") + """
            struct PostInput { uv: vec2<f32> }
            struct TestSurface { present: bool, data: f32 }
            fn surface_at(pixel: vec2<i32>) -> TestSurface { return TestSurface(false, 0.0); }
            fn sun_colour() -> vec3<f32> { return vec3<f32>(1.0, 0.6, 0.2); }
            const bloom_strength: f32 = 0.2;
        """
        source += production_function("post/bloom_extract.wgsl", "bloom_response").replace(
            "frame.luminance", "vec3<f32>(0.2126, 0.7152, 0.0722)") + "\n"
        source += production_function("post/bloom_extract.wgsl", "bright_part") + "\n"
        source += production_function("post/bloom_extract.wgsl", "emissive_part") + "\n"
        source += production_function("post/bloom_extract.wgsl", "terrain_bloom") + "\n"
        source += production_function("post/bloom_extract.wgsl", "foliage_edge_at").replace("scene_depth", "opaque_depth") + "\n"
        source += production_function("post/bloom_extract.wgsl", "post").replace(
            "textureLoad(scene_color, pixel, 0).rgb", "vec3<f32>(4.0, 2.0, 1.0)").replace(
            "scene_color", "opaque_color").replace("scene_depth", "opaque_depth")
        sky = self.execute(source, "output[0] = post(PostInput(vec2<f32>(0.5)));")
        self.assertEqual(sky[:3], (0.0, 0.0, 0.0))
        diffuse, reflective, emissive, _ = self.execute(source, """
            let hdr = vec3<f32>(4.0, 2.0, 1.0);
            let f0 = vec3<f32>(0.04);
            let diffuse = surface_data_bits(encode_surface_data(f0, false, false, false, 0.0)) >> 24u;
            let reflective = surface_data_bits(encode_surface_data(f0, true, false, false, 0.775)) >> 24u;
            let emissive = surface_data_bits(encode_surface_data(f0, false, true, false, 0.0)) >> 24u;
            output[0] = vec4<f32>(terrain_bloom(hdr, diffuse, 0.0).r, terrain_bloom(hdr, reflective, 0.0).r,
                terrain_bloom(hdr, emissive, 0.0).r, 0.0);
        """)
        self.assertEqual(diffuse, 0.0)
        self.assertAlmostEqual(reflective, 0.775, places=5)
        self.assertGreater(emissive, 1.0)
        edge_glow, interior_glow, green, blue = self.execute(source, """
            let leaf = vec3<f32>(0.10, 0.40, 0.04);
            let data = encode_surface_data(vec3<f32>(0.04), false, false, true, 0.775);
            let source = surface_data_bits(data) >> 24u;
            let edge = terrain_bloom(leaf, source, 1.0);
            output[0] = vec4<f32>(edge.r, terrain_bloom(leaf, source, 0.0).r, edge.g, edge.b);
        """)
        self.assertGreater(edge_glow, green)
        self.assertGreater(green, blue)
        self.assertEqual(interior_glow, 0.0)

    def test_solar_bloom_rejects_the_away_from_sun_mirror_angle(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        away, aligned, nearby, unwanted_source = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.29, 0.0));
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.16, 0.16, 0.16, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.material = 60u;
            block.normal.x = 1.0;
            block.position = -9.0 * reflect(-frame.sun_direction, block.normal);
            let away = shade_material(block).color.r;
            let away_source = surface_data_bits(test_surface_data) >> 24u;
            block.normal = vec3<f32>(0.0, 1.0, 0.0);
            block.position = -9.0 * reflect(-frame.sun_direction, block.normal);
            let aligned = shade_material(block).color.r;
            block.position.z += 0.60;
            let nearby = shade_material(block).color.r;
            let nearby_source = surface_data_bits(test_surface_data) >> 24u;
            output[0] = vec4<f32>(away, aligned, nearby, f32(away_source | nearby_source));
        """, {"procedural_clouds": False})
        self.assertLess(away, 0.8)
        self.assertGreater(aligned, 0.9)
        self.assertLess(nearby, 0.45 * aligned)
        self.assertEqual(unwanted_source, 0.0)

    def test_solar_glow_falls_off_with_distance_across_the_surface(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        centre, shoulder, far, _ = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.29, 0.0));
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.16, 0.16, 0.16, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.material = 60u;
            block.normal.y = 1.0;
            block.position = -9.0 * reflect(-frame.sun_direction, block.normal);
            _ = shade_material(block);
            let centre = surface_data_bits(test_surface_data) >> 24u;
            block.position.z += 0.18;
            _ = shade_material(block);
            let shoulder = surface_data_bits(test_surface_data) >> 24u;
            block.position *= 8.0;
            _ = shade_material(block);
            let far = surface_data_bits(test_surface_data) >> 24u;
            output[0] = vec4<f32>(f32(centre), f32(shoulder), f32(far), 0.0);
        """, {"procedural_clouds": False})
        self.assertGreater(centre, shoulder)
        self.assertGreater(shoulder, 1.0)
        self.assertLess(far, 0.25 * shoulder)

    def test_sunward_leaves_and_grass_can_seed_bloom(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        leaf, blade, away, shaded = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.31, 0.0));
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.18, 0.29, 0.05, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.normal.x = -1.0;
            block.position = vec3<f32>(8.0, 1.0, 0.0);
            block.material = 42u;
            _ = shade_material(block);
            let leaf = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            block.material = 40u;
            _ = shade_material(block);
            let blade = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            block.position = -block.position;
            block.normal = -block.normal;
            _ = shade_material(block);
            let away = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            block.position = -block.position;
            block.normal = -block.normal;
            shadow = 0.0;
            _ = shade_material(block);
            let shaded = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            output[0] = vec4<f32>(f32(leaf), f32(blade), f32(away), f32(shaded));
        """, {"procedural_clouds": False})
        self.assertGreater(leaf, 2.0)
        self.assertGreater(blade, 2.0)
        self.assertEqual((away, shaded), (0.0, 0.0))

    def test_solar_reflection_feeds_bloom_at_the_mirror_angle(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        source += "\n" + production_function("post/bloom_extract.wgsl", "bloom_response").replace(
            "frame.luminance", "vec3<f32>(0.2126, 0.7152, 0.0722)")
        source += "\n" + production_function("post/bloom_extract.wgsl", "bright_part")
        source += "\n" + production_function("post/bloom_extract.wgsl", "emissive_part")
        source += "\n" + production_function("post/bloom_extract.wgsl", "terrain_bloom")
        source += """
            fn block_bloom(block: MaterialInput) -> vec3<f32> {
                let shaded = shade_material(block).color.rgb;
                return terrain_bloom(shaded, surface_data_bits(test_surface_data) >> 24u, 0.0);
            }
        """
        faces = [(0, 1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
        for material, normal, wet in [(60, face, False) for face in faces] + [
            (20, (1, 0, 0), False), (60, (1, 0, 0), True),
        ]:
            with self.subTest(material=material, normal=normal, wet=wet):
                x, y, z = normal
                aligned, oblique, covered, tint_ratio = self.execute(source, f"""
                    var block: MaterialInput;
                    block.albedo = vec4<f32>(0.16, 0.16, 0.16, 1.0);
                    block.shaded_tint = vec4<f32>(1.0);
                    block.normal = vec3<f32>({x}.0, {y}.0, {z}.0);
                    block.light.y = 1.0;
                    block.material = {material}u;
                    let tangent = select(vec3<f32>(0.0, 0.3, 1.0), vec3<f32>(1.0, 0.3, 0.0), abs(block.normal.x) == 0.0);
                    let sun = normalize(tangent + 0.28 * block.normal * (1.0 - block.normal.y));
                    frame.sun_direction = sun;
                    frame.light_direction = sun;
                    let mirror = reflect(-sun, block.normal);
                    block.position = -mirror * 9.0;
                    let aligned = block_bloom(block);
                    block.albedo.g = 0.04;
                    let tinted = block_bloom(block);
                    shadow = 0.0;
                    let shaded = block_bloom(block).r;
                    shadow = 1.0;
                    block.light.y = 0.1;
                    let roofed = block_bloom(block).r;
                    block.light.y = 1.0;
                    block.position = -normalize(mirror + vec3<f32>(0.0, 0.0, 2.0) * abs(block.normal.x)
                        + vec3<f32>(0.0, 2.0, 0.0) * abs(block.normal.z)
                        + vec3<f32>(0.0, 0.0, 2.0) * block.normal.y) * 9.0;
                    let oblique = block_bloom(block).r;
                    block.normal = vec3<f32>(0.0, -1.0, 0.0);
                    block.position = vec3<f32>(0.0, 9.0, 0.0);
                    let underside = block_bloom(block).r;
                    output[0] = vec4<f32>(aligned.r, oblique, max(shaded, max(roofed, underside)),
                        (tinted.g * aligned.r) / max(tinted.r * aligned.g, 0.0001));
                """, {"procedural_clouds": False, "wet_in_clear": wet})
                self.assertGreater(aligned, 0.15)
                self.assertLess(oblique, 0.15 * aligned)
                self.assertLess(covered, 0.03)
                self.assertGreater(tint_ratio, 0.70)
                self.assertLess(tint_ratio, 0.96)

    def test_dry_sunlight_on_block_sides_is_directional_and_respects_shadows(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.4, 0.36, 0.28, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.normal.x = 1.0;
            block.light.y = 1.0;
            block.position.x = -8.0;
            let facing = shade_material(block).color.r;
            let reflection_finish = test_surface_smoothness;
            block.position = vec3<f32>(-2.0, 0.0, 8.0);
            let oblique = shade_material(block).color.r;
            shadow = 0.0;
            let shadowed = shade_material(block).color.r;
            output[0] = vec4<f32>(facing, oblique, shadowed, reflection_finish);
        """
        clear_sky = {"procedural_clouds": False}
        lit = self.execute(source, body, clear_sky)
        self.assertGreater(lit[0], lit[1] + 0.012)
        off = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        self.assertGreater(lit[0], off[0] + 0.012)
        self.assertAlmostEqual(lit[2], off[2], delta=0.00002)
        self.assertEqual(lit[3], 0.0)

    def test_leaf_backlighting_in_sun_and_moon_respects_occlusion(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        source += "\noverride test_moonlit: bool = false;\n"
        body = """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            if test_moonlit {
                frame.moon_direction = frame.sun_direction;
                frame.sun_direction = -frame.moon_direction;
            }
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.10, 0.36, 0.07, 0.65);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.normal.x = -1.0;
            block.position.x = 8.0;
            block.material = 42u;
            let leaf = material(block).color;
            shadow = 0.0;
            let covered = material(block).color.g;
            shadow = 1.0;
            block.normal.x = 1.0;
            block.position.x = -8.0;
            block.material = 0u;
            block.albedo = vec4<f32>(0.35, 0.35, 0.35, 0.65);
            output[0] = vec4<f32>(leaf.g, covered, material(block).color.r, leaf.a);
        """
        clear_sky = {"procedural_clouds": False}
        default = self.execute(source, body, clear_sky)
        disabled = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        self.assertGreater(default[0], disabled[0] + 0.04)
        self.assertAlmostEqual(default[1], disabled[1], delta=0.00002)
        self.assertAlmostEqual(default[3], 0.65, delta=0.00002)
        moon = self.execute(source, body, dict(clear_sky, test_moonlit=True))
        moon_disabled = self.execute(source, body, dict(clear_sky, test_moonlit=True, dry_sun_strength=0.0))
        self.assertGreater(moon[0], moon_disabled[0] + 0.005)
        self.assertAlmostEqual(moon[1], moon_disabled[1], delta=0.00002)

    def test_grazing_sun_return_adds_a_pale_highlight_to_green_leaves(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var leaf: MaterialInput;
            leaf.albedo = vec4<f32>(0.12, 0.38, 0.10, 1.0);
            leaf.shaded_tint = vec4<f32>(1.0);
            leaf.light.y = 1.0;
            leaf.normal.y = 1.0;
            leaf.material = 42u;
            leaf.position = vec3<f32>(7.68, -2.24, 0.0);
            let aligned = shade_material(leaf).color.rgb;
            leaf.position.z = 6.0;
            let oblique = shade_material(leaf).color.g;
            output[0] = vec4<f32>(aligned, oblique);
        """
        clear_sky = {"procedural_clouds": False}
        lit = self.execute(source, body, clear_sky)
        base = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        returned = [channel - original for channel, original in zip(lit, base)]
        self.assertGreater(returned[1], 0.18)
        self.assertGreater(returned[2], 0.65 * returned[0])
        self.assertGreater(lit[1], lit[0])
        self.assertGreater(returned[1], 2.0 * returned[3])

    def test_leaf_crowns_catch_low_sun_while_opaque_cover_blocks_it(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        sunlit, shadowed, roofed, red = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var leaf: MaterialInput;
            leaf.albedo = vec4<f32>(0.14, 0.36, 0.06, 0.8);
            leaf.shaded_tint = vec4<f32>(1.0);
            leaf.light.y = 1.0;
            leaf.normal.y = 1.0;
            leaf.material = 42u;
            leaf.position = vec3<f32>(4.0, -1.0, 0.0);
            let sunlit = material(leaf).color;
            shadow = 0.0;
            let shadowed = material(leaf).color.g;
            leaf.light.y = 0.12;
            shadow = 1.0;
            let roofed = material(leaf).color.g;
            output[0] = vec4<f32>(sunlit.g, shadowed, roofed, sunlit.r);
        """, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        self.assertGreater(sunlit - shadowed, 0.16)
        self.assertGreater(sunlit, 1.40 * red)
        self.assertLess(roofed, 0.01)

    def test_low_sun_brightens_green_leaf_sides_without_washing_out_the_pigment(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        red_ratio, green, luma_gain, blue_ratio = self.execute(source, """
            frame.sun_direction = vec3<f32>(-0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var leaf: MaterialInput;
            leaf.albedo = vec4<f32>(0.18, 0.38, 0.08, 0.8);
            let side_tint = pow(0.6, 2.2);
            leaf.shaded_tint = vec4<f32>(vec3<f32>(side_tint), 1.0);
            leaf.light.y = 1.0;
            leaf.normal.x = -1.0;
            leaf.material = 42u;
            leaf.position.x = 8.0;
            let lit = material(leaf).color.rgb;
            shadow = 0.0;
            let direct = lit - material(leaf).color.rgb;
            let solar = solar_radiance();
            let old_light = mix(solar, vec3<f32>(solar.g), 0.42);
            let old_direct = leaf.albedo.rgb * old_light * (0.96 * 1.24 * side_tint);
            let weights = vec3<f32>(0.2126, 0.7152, 0.0722);
            output[0] = vec4<f32>(direct.r / direct.g, direct.g,
                dot(direct, weights) / dot(old_direct, weights), direct.b / direct.g);
        """, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        self.assertLess(red_ratio, 0.67)
        self.assertGreater(green, 0.30)
        self.assertGreater(luma_gain, 1.6)
        self.assertLess(luma_gain, 3.1)
        self.assertLess(blue_ratio, 0.24)

    def test_exposed_cardinal_leaf_sides_match_crown_brightness_in_low_sun(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        east, north, south, dark = self.execute(source, """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var leaf: MaterialInput;
            leaf.albedo = vec4<f32>(0.18, 0.38, 0.08, 1.0);
            leaf.shaded_tint = vec4<f32>(1.0);
            leaf.light.y = 1.0;
            leaf.material = 42u;
            leaf.normal.y = 1.0;
            let weights = vec3<f32>(0.2126, 0.7152, 0.0722);
            let crown = dot(material(leaf).color.rgb, weights);
            leaf.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            leaf.normal = vec3<f32>(1.0, 0.0, 0.0);
            let east = dot(material(leaf).color.rgb, weights);
            leaf.normal.x = -1.0;
            let west = dot(material(leaf).color.rgb, weights);
            leaf.shaded_tint = vec4<f32>(vec3<f32>(pow(0.8, 2.2)), 1.0);
            leaf.normal = vec3<f32>(0.0, 0.0, -1.0);
            let north = dot(material(leaf).color.rgb, weights);
            leaf.normal.z = 1.0;
            let south = dot(material(leaf).color.rgb, weights);
            shadow = 0.0;
            let roofed = dot(material(leaf).color.rgb, weights);
            output[0] = vec4<f32>(east, north, south, max(west, roofed)) / crown;
        """, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        for side in (east, north, south):
            self.assertAlmostEqual(side, 1.0, delta=0.10)
        self.assertLess(dark, 0.48)

    def test_perpendicular_leaf_side_glint_is_distance_independent(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var leaf: MaterialInput;
            leaf.albedo = vec4<f32>(0.18, 0.38, 0.08, 1.0);
            leaf.shaded_tint = vec4<f32>(vec3<f32>(pow(0.8, 2.2)), 1.0);
            leaf.light.y = 1.0;
            leaf.material = 42u;
            leaf.normal = vec3<f32>(0.0, 0.0, 1.0);
            let direction = normalize(vec3<f32>(0.0, -0.35, -1.0));
            leaf.position = direction * 14.0;
            let middle = material(leaf).color.rgb;
            leaf.position = direction * 3.0;
            let near = material(leaf).color.g;
            leaf.position = direction * 32.0;
            let far = material(leaf).color.g;
            leaf.position = direction * 14.0;
            shadow = 0.0;
            let covered = material(leaf).color.g;
            output[0] = vec4<f32>(middle.g, middle.r, abs(near - middle.g) + abs(far - middle.g), covered);
        """
        clear_sky = {"procedural_clouds": False, "aerial_perspective": 0.0}
        on = self.execute(source, body, clear_sky)
        off = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        green_gain = on[0] - off[0]
        red_gain = on[1] - off[1]
        self.assertGreater(green_gain, 0.025)
        self.assertGreater(red_gain / green_gain, 0.25)
        self.assertLess(red_gain / green_gain, 0.48)
        self.assertAlmostEqual(on[2], 0.0, delta=0.00002)
        self.assertAlmostEqual(on[3], off[3], delta=0.00002)

    def test_solid_block_side_highlights_do_not_change_with_distance(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.42, 0.16, 0.07, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.normal.y = 1.0;
            let top = material(block).color.r;
            block.normal = vec3<f32>(0.0, 0.0, 1.0);
            block.shaded_tint = vec4<f32>(vec3<f32>(pow(0.8, 2.2)), 1.0);
            let direction = normalize(vec3<f32>(0.0, -0.35, -1.0));
            block.position = direction * 14.0;
            let middle = material(block).color.rg;
            block.position = direction * 3.0;
            let near = material(block).color.r;
            block.position = direction * 32.0;
            let far = material(block).color.r;
            shadow = 0.0;
            block.position = direction * 14.0;
            let covered = material(block).color.r;
            output[0] = vec4<f32>(top, middle.r, abs(near - middle.r) + abs(far - middle.r), covered);
        """
        clear_sky = {"procedural_clouds": False, "aerial_perspective": 0.0}
        off = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        self.assertAlmostEqual(off[1] / off[0], 1.0, delta=0.12)
        on = self.execute(source, body, clear_sky)
        self.assertGreater(on[1] - off[1], 0.005)
        self.assertAlmostEqual(on[2], 0.0, delta=0.00002)
        self.assertAlmostEqual(on[3], off[3], delta=0.00002)

    def test_moonlit_block_side_highlights_do_not_change_with_distance(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.moon_direction = vec3<f32>(0.96, 0.28, 0.0);
            frame.sun_direction = -frame.moon_direction;
            frame.light_direction = frame.moon_direction;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.42, 0.16, 0.07, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.normal.y = 1.0;
            let top = material(block).color.r;
            block.normal = vec3<f32>(0.0, 0.0, 1.0);
            block.shaded_tint = vec4<f32>(vec3<f32>(pow(0.8, 2.2)), 1.0);
            let direction = normalize(vec3<f32>(0.0, -0.35, -1.0));
            block.position = direction * 14.0;
            let middle = material(block).color.rg;
            block.position = direction * 3.0;
            let near = material(block).color.r;
            block.position = direction * 32.0;
            let far = material(block).color.r;
            shadow = 0.0;
            block.position = direction * 14.0;
            let covered = material(block).color.r;
            output[0] = vec4<f32>(top, middle.r, abs(near - middle.r) + abs(far - middle.r), covered);
        """
        clear_sky = {"procedural_clouds": False, "aerial_perspective": 0.0}
        off = self.execute(source, body, dict(clear_sky, dry_sun_strength=0.0))
        self.assertAlmostEqual(off[1] / off[0], 1.0, delta=0.12)
        on = self.execute(source, body, clear_sky)
        self.assertGreater(on[1] - off[1], 0.0004)
        self.assertAlmostEqual(on[2], 0.0, delta=0.00002)
        self.assertAlmostEqual(on[3], off[3], delta=0.00002)
        dark = self.execute(source, body, dict(clear_sky, night_brightness=0.0))
        self.assertAlmostEqual(dark[1], 0.42 * pow(0.8, 2.2) * 0.008, delta=0.00002)

    def test_oblique_shoreline_uses_the_water_plane_not_radial_distance(self):
        source = production_function("water.wgsl", "water_plane_distance")
        source += production_function("water.wgsl", "water_background_is_foreground")
        value = self.execute(source, """
            let surface = vec3<f32>(0.0, -2.0, -9.797959);
            let normal = vec3<f32>(0.0, 1.0, 0.0);
            let dry = vec3<f32>(0.0, -1.9, -10.32618);
            let bottom = vec3<f32>(0.0, -3.0, -10.0);
            let ray = normalize(vec3<f32>(0.0, -1.0, -4.0));
            output[0] = vec4<f32>(
                select(0.0, 1.0, water_background_is_foreground(dry, surface, normal)),
                select(0.0, 1.0, water_background_is_foreground(bottom, surface, normal)),
                water_plane_distance(ray, surface, normal), 1.0);
        """)
        self.assertEqual(value[0], 1.0)
        self.assertEqual(value[1], 0.0)
        self.assertAlmostEqual(value[2], 2 * (17 ** 0.5), delta=0.00002)

    def test_clear_transmission_does_not_fog_the_background_twice(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        value = self.execute(source, """
            frame.fog_environment = vec2<f32>(0.0, 20.0);
            frame.fog_color = vec3<f32>(0.8);
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.eye_in = 1u;
            var water: MaterialInput;
            water.position = vec3<f32>(0.0, 0.0, -10.0);
            water.face = 1u;
            water.normal = vec3<f32>(0.0, -1.0, 0.0);
            water.screen = vec2<f32>(0.5);
            water.light.y = 1.0;
            water.fluid = 1u;
            water.translucent = true;
            water.albedo.a = 1.0;
            let prior_scene = vec3<f32>(0.35, 0.46, 0.60); // Includes an already-blended glass layer.
            let water_layer = material(water).color;
            let composited = mix(prior_scene, water_layer.rgb, water_layer.a);
            output[0] = vec4<f32>(composited, surface_fog_factor(water.position));
        """)
        for actual, expected in zip(value, (0.35, 0.46, 0.60, 0.5)):
            self.assertAlmostEqual(actual, expected, delta=0.00002)

    def test_all_light_sources_emit_colored_glow_and_seed_bloom(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        source += "\n" + production_function("post/bloom_extract.wgsl", "bloom_response").replace(
            "frame.luminance", "vec3<f32>(0.2126, 0.7152, 0.0722)")
        source += "\n" + production_function("post/bloom_extract.wgsl", "bright_part")
        source += "\n" + production_function("post/bloom_extract.wgsl", "emissive_part")
        source += "\n" + production_function("post/bloom_extract.wgsl", "terrain_bloom")
        source += """
            fn bloom_of(block: MaterialInput) -> vec3<f32> {
                let shaded = shade_material(block).color.rgb;
                return terrain_bloom(shaded, surface_data_bits(test_surface_data) >> 24u, 0.0);
            }
        """
        redstone, sea_lantern, glowstone, frame_bloom = self.execute(source, """
            var block: MaterialInput;
            block.shaded_tint = vec4<f32>(1.0);
            block.normal = vec3<f32>(0.0, 1.0, 0.0);
            block.emission = 7.0 / 15.0;
            block.albedo = vec4<f32>(0.85, 0.14, 0.06, 1.0);
            let redstone = bloom_of(block);
            block.emission = 1.0;
            block.albedo = vec4<f32>(0.18, 0.72, 0.80, 1.0);
            let sea_lantern = bloom_of(block);
            block.albedo = vec4<f32>(0.82, 0.64, 0.28, 1.0);
            let glowstone = bloom_of(block);
            block.albedo = vec4<f32>(0.16, 0.16, 0.16, 1.0);
            let frame_bloom = bloom_of(block);
            output[0] = vec4<f32>(redstone.r, sea_lantern.b, glowstone.r,
                max(frame_bloom.r, max(frame_bloom.g, frame_bloom.b)));
        """)
        self.assertGreater(redstone, 0.8)
        self.assertGreater(sea_lantern, 1.5)
        self.assertGreater(glowstone, 1.5)
        self.assertLess(frame_bloom, 0.01)

    def test_deep_overworld_water_gains_aquatic_blue_depth_tint(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water"))
        body = """
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.light_direction = frame.sun_direction;
            let sand = vec3<f32>(0.62, 0.56, 0.34);
            let pos = vec3<f32>(0.0, -4.0, -6.0);
            let shallow = water_depth_tint(sand, 0.5, 1.0, 1.0, pos);
            let deep = water_depth_tint(sand, 14.0, 1.0, 1.0, pos);
            output[0] = vec4<f32>(deep.b / max(deep.r, 0.001), deep.b - shallow.b,
                deep.g - deep.r, shallow.r - deep.r);
        """
        aquatic = self.execute(source, body)
        clear = self.execute(source, body, {"water_clarity": 4.0})
        self.assertGreater(aquatic[0], 2.5)
        self.assertGreater(aquatic[2], 0.04)
        self.assertGreater(aquatic[3], 0.35)
        self.assertAlmostEqual(clear[1], 0.0, places=5)
        self.assertAlmostEqual(clear[3], 0.0, places=5)

    def test_cave_water_uses_animated_default_texture_for_sources_and_flows(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water"))
        body = """
            var water: MaterialInput;
            water.albedo = vec4<f32>(0.85, 0.85, 0.85, 0.75);
            water.shaded_tint = vec4<f32>(0.18, 0.38, 0.85, 1.0);
            water.screen = vec2<f32>(0.5);
            water.light = vec2<f32>(0.0, 0.0);
            water.face = 1u;
            water.position = vec3<f32>(1.5, -0.5, -4.0);
            water.normal = vec3<f32>(0.0, 1.0, 0.0);
            let pool_t0 = shade_water(water).color;
            water.albedo = vec4<f32>(0.25, 0.25, 0.25, 0.75);
            let pool_body = shade_water(water).color;
            water.albedo = vec4<f32>(0.85, 0.85, 0.85, 0.75);
            water.face = 3u;
            water.normal = vec3<f32>(0.0, 0.0, 1.0);
            let flow_t0 = shade_water(water).color;
            water.albedo = vec4<f32>(0.25, 0.25, 0.25, 0.75);
            let body_side = shade_water(water).color;
            water.albedo = vec4<f32>(0.85, 0.85, 0.85, 0.75);
            frame.time = 1.4;
            let flow_t1 = shade_water(water).color;
            water.face = 1u;
            water.normal = vec3<f32>(0.0, 1.0, 0.0);
            let pool_t1 = shade_water(water).color;
            let added_pool = pool_t0.rgb - pool_body.rgb;
            output[0] = vec4<f32>(added_pool.r / max(added_pool.b, 0.001),
                flow_t0.r - body_side.r, length(flow_t1.rgb - flow_t0.rgb),
                length(pool_t1.rgb - pool_t0.rgb));
        """
        moving = self.execute(source, body)
        frozen = self.execute(source, body, {"water_speed": 0.0})
        self.assertGreater(moving[0], 0.85)
        self.assertGreater(moving[1], 0.12)
        self.assertGreater(moving[2], 0.001)
        self.assertAlmostEqual(frozen[2], 0.0, places=6)
        self.assertAlmostEqual(frozen[3], 0.0, places=6)

    def test_other_plants_share_grass_backlighting_and_bloom(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.31, 0.0));
            frame.light_direction = frame.sun_direction;
            var plant: MaterialInput;
            plant.material = 40u;
            plant.albedo = vec4<f32>(0.42, 0.34, 0.12, 1.0);
            plant.shaded_tint = vec4<f32>(1.0);
            plant.light.y = 1.0;
            plant.normal = vec3<f32>(-1.0, 0.0, 0.0);
            plant.position = vec3<f32>(8.0, 1.0, 0.0);
            let backlit = shade_material(plant).color.r;
            let bloom = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            shadow = 0.0;
            let covered = shade_material(plant).color.r;
            output[0] = vec4<f32>(backlit, covered, f32(bloom), 0.0);
        """
        lit = self.execute(source, body, {"procedural_clouds": False})
        off = self.execute(source, body, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        self.assertGreater(lit[0], off[0] + 0.12)
        self.assertAlmostEqual(lit[1], off[1], delta=0.00002)
        self.assertGreater(lit[2], 2.0)

    def test_terrain_micro_relief_adds_depth_without_breaking_pbr_or_foliage(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        tilt, flat_delta, pbr_tilt, far_tilt = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.85, 0.52, 0.0));
            frame.light_direction = frame.sun_direction;
            test_block_bump_grad = vec2<f32>(16.0, 0.0);
            var stone: MaterialInput;
            stone.material = 60u;
            stone.albedo = vec4<f32>(0.36, 0.36, 0.36, 1.0);
            stone.shaded_tint = vec4<f32>(1.0);
            stone.light.y = 1.0;
            stone.position = vec3<f32>(0.0, -1.0, -4.0);
            stone.normal = vec3<f32>(0.0, 1.0, 0.0);
            stone.uv = vec2<f32>(0.125, 0.125);
            let flat_lit = shade_material(stone).color.r;
            stone.tangent = vec4<f32>(1.0, 0.0, 0.0, 1.0);
            let relieved = shade_material(stone).color.r;
            let bump_tilt = abs(test_surface_normal.x);
            test_block_pbr = true;
            _ = shade_material(stone);
            let pbr_tilt = abs(test_surface_normal.x);
            test_block_pbr = false;
            stone.position = vec3<f32>(0.0, -1.0, -30.0);
            _ = shade_material(stone);
            let far_tilt = abs(test_surface_normal.x);
            output[0] = vec4<f32>(bump_tilt, flat_lit - relieved, pbr_tilt, far_tilt);
        """, {"procedural_clouds": False})
        self.assertGreater(tilt, 0.03)
        self.assertGreater(flat_delta, 0.01)
        self.assertEqual(pbr_tilt, 0.0)
        self.assertEqual(far_tilt, 0.0)

    def test_near_emitter_block_light_pool_stays_saturated_and_rich(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        near_r, near_g, near_b, far_r = self.execute(source, """
            test_light_field = vec4<f32>(1.06, 0.74, 0.34, 0.90);
            let near_pool = block_surface_light(vec3<f32>(0.0, 0.0, -4.0), 0.92);
            test_light_field.a = 0.40;
            let far_pool = block_surface_light(vec3<f32>(0.0, 0.0, -4.0), 0.60);
            output[0] = vec4<f32>(near_pool, far_pool.r);
        """)
        self.assertGreater(near_r, 1.35)
        self.assertGreater(near_r / near_g, 1.30)
        self.assertGreater(near_g / near_b, 1.65)
        self.assertLess(far_r, 0.22)

    def test_sunlit_grass_block_side_reacts_cleanly_to_direct_sunlight(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        lit_r, lit_g, shaded_r, bright_cap = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.94, 0.34, 0.0));
            frame.light_direction = frame.sun_direction;
            var block: MaterialInput;
            block.material = 41u;
            block.albedo = vec4<f32>(0.36, 0.22, 0.14, 1.0);
            block.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            block.light.y = 1.0;
            block.normal = vec3<f32>(1.0, 0.0, 0.0);
            block.position = vec3<f32>(-8.0, 0.0, 0.0);
            let sunlit = shade_material(block).color.rgb;
            shadow = 0.0;
            let shaded = shade_material(block).color.rgb;
            shadow = 1.0;
            block.albedo = vec4<f32>(0.92, 0.72, 0.56, 1.0);
            let bright_cap = shade_material(block).color.r;
            output[0] = vec4<f32>(sunlit.rg, shaded.r, bright_cap);
        """, {"procedural_clouds": False})
        self.assertGreater(lit_r, shaded_r * 2.4)
        self.assertGreater(lit_g / lit_r, 0.38)
        self.assertLess(lit_g / lit_r, 0.56)
        self.assertGreater(lit_r, 0.28)
        self.assertLess(bright_cap, 1.15)

    def test_dry_grass_ground_stays_natural_without_mirror_stripe(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = normalize(vec3<f32>(1.0, 0.29, 0.0));
            frame.light_direction = frame.sun_direction;
            var grass: MaterialInput;
            grass.material = 41u;
            grass.albedo = vec4<f32>(0.22, 0.34, 0.10, 1.0);
            grass.shaded_tint = vec4<f32>(1.0);
            grass.light.y = 1.0;
            grass.normal.y = 1.0;
            grass.position = -9.0 * reflect(-frame.sun_direction, grass.normal);
            let out = shade_material(grass).color.rgb;
            let smoothness = test_surface_smoothness;
            let bloom_bits = (surface_data_bits(test_surface_data) >> 24u) & 31u;
            output[0] = vec4<f32>(out.g, smoothness, f32(bloom_bits), out.r);
        """
        dry = self.execute(source, body, {"procedural_clouds": False})
        wet = self.execute(source, body, {"procedural_clouds": False, "wet_in_clear": True})
        self.assertEqual(dry[1], 0.0)
        self.assertEqual(dry[2], 0.0)
        self.assertGreater(wet[1], 0.65)
        self.assertGreater(wet[2], 0.0)

    def test_warm_sunlight_stays_active_away_from_noon_and_sunrise_is_warm(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        sunrise_rg, sunrise_gb, morning_rb, noon_br = self.execute(source, """
            let origin = vec3<f32>(0.0);
            let up = vec3<f32>(0.0, 1.0, 0.0);
            let stone = vec3<f32>(0.45);
            frame.sun_direction = normalize(vec3<f32>(0.997, 0.08, 0.0));
            frame.light_direction = frame.sun_direction;
            let sunrise = shade_surface(origin, up, 1.0, stone, 0.0, origin, false, false, 0.0);
            frame.sun_direction = normalize(vec3<f32>(0.694, 0.72, 0.0));
            frame.light_direction = frame.sun_direction;
            let morning = shade_surface(origin, up, 1.0, stone, 0.0, origin, false, false, 1.0);
            frame.sun_direction = normalize(vec3<f32>(0.20, 0.98, 0.0));
            frame.light_direction = frame.sun_direction;
            let noon = shade_surface(origin, up, 1.0, stone, 0.0, origin, false, false, 1.0);
            output[0] = vec4<f32>(sunrise.r / max(sunrise.g, 0.001),
                sunrise.g / max(sunrise.b, 0.001),
                morning.r / max(morning.b, 0.001),
                noon.b / max(noon.r, 0.001));
        """, {"procedural_clouds": False})
        self.assertGreater(sunrise_rg, 1.25)
        self.assertGreater(sunrise_gb, 1.90)
        self.assertGreater(morning_rb, 1.55)
        self.assertGreater(noon_br, 0.78)

    def test_dry_grass_grazing_sheen_is_warm_and_preserves_pixel_texture(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        body = """
            frame.sun_direction = normalize(vec3<f32>(0.95, 0.31, 0.0));
            frame.light_direction = frame.sun_direction;
            var grass: MaterialInput;
            grass.material = 41u;
            grass.shaded_tint = vec4<f32>(1.0);
            grass.light.y = 1.0;
            grass.normal = vec3<f32>(0.0, 1.0, 0.0);
            grass.position = vec3<f32>(12.0, -2.8, 0.0);
            grass.albedo = vec4<f32>(0.26, 0.38, 0.10, 1.0);
            let bright = shade_material(grass).color.rgb;
            grass.albedo = vec4<f32>(0.07, 0.11, 0.03, 1.0);
            let dark = shade_material(grass).color.g;
            var wood: MaterialInput;
            wood.material = 0u;
            wood.albedo = vec4<f32>(0.42, 0.28, 0.14, 1.0);
            wood.shaded_tint = vec4<f32>(1.0);
            wood.light.y = 1.0;
            wood.normal.y = 1.0;
            wood.position = -9.0 * reflect(-frame.sun_direction, wood.normal);
            _ = shade_material(wood);
            let wood_bloom = f32((surface_data_bits(test_surface_data) >> 24u) & 31u);
            output[0] = vec4<f32>(bright.r, bright.g, bright.b, dark + 10.0 * wood_bloom);
        """
        on = self.execute(source, body, {"procedural_clouds": False})
        off = self.execute(source, body, {"procedural_clouds": False, "dry_sun_strength": 0.0})
        added_r = on[0] - off[0]
        added_g = on[1] - off[1]
        added_b = on[2] - off[2]
        dark_gain = on[3] - off[3]
        self.assertGreater(added_g, 0.025)
        self.assertGreater(added_r, added_b * 1.8)
        self.assertGreater(added_g, dark_gain * 3.5)
        self.assertLess(on[3], 1.0)

    def test_sunlit_cliff_sides_stay_clean_and_invariant_across_distance(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        near_r, mid_r, far_r, dirt_bump = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.88, 0.47, 0.0));
            frame.light_direction = frame.sun_direction;
            test_block_bump_grad = vec2<f32>(16.0, 0.0);
            var dirt: MaterialInput;
            dirt.material = 61u;
            dirt.albedo = vec4<f32>(0.34, 0.20, 0.12, 1.0);
            dirt.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            dirt.light.y = 1.0;
            dirt.normal = vec3<f32>(1.0, 0.0, 0.0);
            dirt.tangent = vec4<f32>(0.0, 0.0, 1.0, 1.0);
            dirt.uv = vec2<f32>(0.125, 0.125);
            let ray = normalize(vec3<f32>(-1.0, 0.15, 0.0));
            dirt.position = ray * 4.0;
            let near_r = shade_material(dirt).color.r;
            let dirt_bump = abs(test_surface_normal.z);
            dirt.position = ray * 14.0;
            let mid_r = shade_material(dirt).color.r;
            dirt.position = ray * 40.0;
            let far_r = shade_material(dirt).color.r;
            output[0] = vec4<f32>(near_r, mid_r, far_r, dirt_bump);
        """, {"procedural_clouds": False, "aerial_perspective": 0.0})
        self.assertGreater(near_r, 0.42)
        self.assertAlmostEqual(near_r, mid_r, delta=0.0001)
        self.assertAlmostEqual(mid_r, far_r, delta=0.0001)
        self.assertEqual(dirt_bump, 0.0)

    def test_sunset_sand_shadow_and_exposure_stay_cohesive(self):
        source = MATERIAL_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        side_lit_r, top_lit_r, shadow_r, shadow_rb = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(-0.98, 0.20, 0.0));
            frame.light_direction = frame.sun_direction;
            var sand: MaterialInput;
            sand.material = 0u;
            sand.albedo = vec4<f32>(0.76, 0.68, 0.45, 1.0);
            sand.light.y = 1.0;
            sand.position = vec3<f32>(8.0, -1.0, 0.0);
            sand.normal = vec3<f32>(-1.0, 0.0, 0.0);
            sand.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            let side_lit = shade_material(sand).color.rgb;
            sand.normal = vec3<f32>(0.0, 1.0, 0.0);
            sand.shaded_tint = vec4<f32>(1.0);
            let top_lit = shade_material(sand).color.rgb;
            shadow = 0.0;
            let top_shadow = shade_material(sand).color.rgb;
            output[0] = vec4<f32>(side_lit.r, top_lit.r, top_shadow.r,
                top_shadow.r / max(top_shadow.b, 0.001));
        """, {"procedural_clouds": False, "aerial_perspective": 0.0})
        self.assertLess(side_lit_r, 0.95)
        self.assertLess(top_lit_r, 0.95)
        self.assertGreater(top_lit_r, shadow_r * 1.6)
        self.assertGreater(shadow_rb, 1.45)

    def test_wind_animates_foliage_keeps_roots_anchored_and_tall_plants_seamless(self):
        source = VERTEX_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        root_move, top_move, seam_error, static_move = self.execute(source, """
            frame.time = 1.25;
            frame.camera_position = vec3<f32>(12.0, 64.0, -8.0);
            var v: VertexInput;
            v.position = vec3<f32>(3.0, 1.0, -5.0);
            v.light = vec2<f32>(0.0, 1.0);
            v.material = 40u;
            v.uv = vec2<f32>(0.5, 1.0);
            let root_move = length(vertex(v) - v.position);
            v.uv = vec2<f32>(0.5, 0.0);
            let bottom_top = vertex(v);
            let top_move = length(bottom_top - v.position);
            // Upper half of a 2-tall plant shares the exact position at uv.y = 1.0.
            v.material = 43u;
            v.uv = vec2<f32>(0.5, 1.0);
            let upper_bottom = vertex(v);
            let seam_error = length(upper_bottom - bottom_top);
            // Solid blocks (0), grass blocks (41), and flat foliage (47) stay static.
            v.material = 47u;
            v.uv = vec2<f32>(0.5, 0.0);
            let static_move = length(vertex(v) - v.position);
            v.material = 41u;
            let grass_block_move = length(vertex(v) - v.position);
            output[0] = vec4<f32>(root_move, top_move, seam_error, static_move + grass_block_move);
        """)
        self.assertEqual(root_move, 0.0)
        self.assertGreater(top_move, 0.015)
        self.assertAlmostEqual(seam_error, 0.0, places=6)
        self.assertEqual(static_move, 0.0)

    def test_wind_speeds_up_in_rain_shelters_caves_and_wraps_cleanly(self):
        source = VERTEX_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        calm_speed, rain_speed, cave_rain_diff, wrap_error = self.execute(source, """
            frame.camera_position = vec3<f32>(4.0, 65.0, 2.0);
            var v: VertexInput;
            v.position = vec3<f32>(2.0, 0.0, -4.0);
            v.uv = vec2<f32>(0.5, 0.0);
            v.material = 40u;
            v.light = vec2<f32>(0.0, 1.0);
            // Measure RMS velocity over several timestamps to verify rain speeds up oscillation.
            var calm_v = 0.0;
            var rain_v = 0.0;
            let dt = 0.05;
            for (var i = 0; i < 8; i++) {
                let t = f32(i) * 0.45;
                frame.rain = 0.0;
                frame.time = t;
                let c0 = vertex(v);
                frame.time = t + dt;
                let c1 = vertex(v);
                calm_v += length(c1 - c0) / dt;
                frame.rain = 1.0;
                frame.time = t;
                let r0 = vertex(v);
                frame.time = t + dt;
                let r1 = vertex(v);
                rain_v += length(r1 - r0) / dt;
            }
            // Sheltered cave plant (light.y = 0) ignores surface rain gusts.
            v.light = vec2<f32>(0.5, 0.0);
            frame.time = 1.3;
            frame.rain = 0.0;
            let cave_dry = vertex(v);
            frame.rain = 1.0;
            let cave_wet = vertex(v);
            // Exact wrap at 3600s.
            v.light = vec2<f32>(0.0, 1.0);
            frame.rain = 0.7;
            frame.time = 0.0;
            let t0 = vertex(v);
            frame.time = 3600.0;
            let t3600 = vertex(v);
            output[0] = vec4<f32>(calm_v, rain_v, length(cave_wet - cave_dry), length(t3600 - t0));
        """)
        self.assertGreater(calm_speed, 0.05)
        self.assertGreater(rain_speed, calm_speed * 2.5)
        self.assertAlmostEqual(cave_rain_diff, 0.0, places=6)
        self.assertAlmostEqual(wrap_error, 0.0, places=5)

    def test_wind_rain_transition_has_no_phase_jump_and_respects_options_and_distance(self):
        source = VERTEX_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        step_delta, far_move, leaf_move, disabled_move = self.execute(source, """
            frame.time = 1842.5;
            var v: VertexInput;
            v.position = vec3<f32>(0.0, 0.0, -6.0);
            v.uv = vec2<f32>(0.5, 0.0);
            v.material = 40u;
            v.light = vec2<f32>(0.0, 1.0);
            frame.rain = 0.40;
            let a = vertex(v);
            frame.rain = 0.42;
            let b = vertex(v);
            // Beyond 96 blocks, foliage wind fades completely to zero.
            v.position = vec3<f32>(0.0, 0.0, -100.0);
            let far_move = length(vertex(v) - v.position);
            // Tree leaves (42) wave in 3D including subtle vertical flutter.
            v.position = vec3<f32>(1.5, 4.0, -5.0);
            v.material = 42u;
            let leaf_delta0 = vertex(v) - v.position;
            frame.time += 0.45;
            let leaf_delta1 = vertex(v) - v.position;
            let leaf_y = max(abs(leaf_delta0.y), abs(leaf_delta1.y));
            output[0] = vec4<f32>(length(b - a), far_move, max(length(leaf_delta0), length(leaf_delta1)), leaf_y);
        """)
        self.assertLess(step_delta, 0.008)
        self.assertEqual(far_move, 0.0)
        self.assertGreater(leaf_move, 0.01)
        self.assertGreater(disabled_move, 0.001)
        off_move, _, _, _ = self.execute(source, """
            frame.time = 1.5;
            var v: VertexInput;
            v.position = vec3<f32>(0.0, 0.0, -6.0);
            v.uv = vec2<f32>(0.5, 0.0);
            v.material = 40u;
            v.light = vec2<f32>(0.0, 1.0);
            output[0] = vec4<f32>(length(vertex(v) - v.position), 0.0, 0.0, 0.0);
        """, {"foliage_wind": False})
        self.assertEqual(off_move, 0.0)

    def test_dynamic_lighting_follows_placed_light_colors_across_terrain_water_and_dimensions(self):
        source = MATERIAL_INPUT + ENTITY_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material", "entity"))
        # Cyan soul lantern color (gamma [0.50, 0.88, 1.0] -> linear ~[0.218, 0.755, 1.0])
        soul_b_over_r, nether_r, water_gain, placed_match_diff = self.execute(source, """
            frame.sun_direction.y = -1.0;
            var stone: MaterialInput;
            stone.albedo = vec4<f32>(0.5, 0.5, 0.5, 1.0);
            stone.shaded_tint = vec4<f32>(1.0);
            stone.normal.y = 1.0;
            stone.position = vec3<f32>(0.0, -1.2, -7.0);
            stone.light.x = 0.85;
            stone.colored_light = vec3<f32>(0.17, 0.58, 0.78);
            let soul_lit = material(stone).color.rgb;
            // Nether dynamic light matches placed brightness even without a placed block nearby.
            frame.dimension = -1;
            stone.colored_light = vec3<f32>(0.80, 0.36, 0.065);
            let nether_lit = material(stone).color.rgb;
            // Held/dropped torch matches placed torch brightness and does not stack with placed light.
            frame.dimension = 0;
            test_light_field = vec4<f32>(1.00, 0.46, 0.085, 0.95);
            stone.light.x = 0.90;
            stone.colored_light = vec3<f32>(0.0);
            let placed_only = material(stone).color.r;
            stone.colored_light = vec3<f32>(0.85, 0.39, 0.072);
            let placed_plus_dyn = material(stone).color.r;
            // Held/dropped light illuminates dark cave water lines.
            test_light_field = vec4<f32>(0.0);
            var water: MaterialInput;
            water.fluid = 1u;
            water.translucent = true;
            water.face = 1u;
            water.normal = vec3<f32>(0.0, 1.0, 0.0);
            water.position = vec3<f32>(0.0, -1.2, -3.0);
            water.albedo = vec4<f32>(0.9, 0.9, 0.9, 0.8);
            water.shaded_tint = vec4<f32>(1.0);
            water.screen = vec2<f32>(0.5, 0.5);
            let dark_water = shade_water(water).color.r;
            water.light.x = 0.85;
            water.colored_light = vec3<f32>(0.82, 0.37, 0.07);
            let lit_water = shade_water(water).color.r;
            output[0] = vec4<f32>(soul_lit.b / max(soul_lit.r, 0.001), nether_lit.r,
                lit_water - dark_water, abs(placed_plus_dyn - placed_only));
        """, {"block_volumetric_strength": 0.0})
        self.assertGreater(soul_b_over_r, 3.0)
        self.assertGreater(nether_r, 0.25)
        self.assertGreater(water_gain, 0.05)
        self.assertLess(placed_match_diff, 0.02)
        off_val, _, _, _ = self.execute(source, """
            output[0] = vec4<f32>(local_surface_light(vec3<f32>(0.0, -1.2, -2.0), 0.85, vec3<f32>(0.85, 0.38, 0.07)), 0.0);
        """, {"dynamic_lights": False})
        self.assertEqual(off_val, 0.0)

    def test_multiple_nearby_dynamic_lights_preserve_warm_hue_and_soft_placed_falloff(self):
        source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        one_r, stacked_r, white_clip_rg, yellow_clip_rg = self.execute(source, """
            let at = vec3<f32>(0.0, -1.0, -8.0);
            // Same MAX light.x -> single dropped torch and 10 stacked torches have identical intensity & radius.
            let one = local_surface_light(at, 0.88, vec3<f32>(0.80, 0.36, 0.068));
            let mid_clip = local_surface_light(at, 0.88, vec3<f32>(1.00, 1.00, 0.85));
            let white_clip = local_surface_light(at, 0.88, vec3<f32>(1.00, 1.00, 1.00));
            output[0] = vec4<f32>(one.r, white_clip.r,
                white_clip.r / max(white_clip.g, 0.001),
                mid_clip.r / max(mid_clip.g, 0.001));
        """)
        self.assertGreater(one_r, 0.9)
        self.assertAlmostEqual(one_r, stacked_r, delta=0.05)
        # Neither yellow-green nor all-channel white clipping shifts warm torches away from amber.
        self.assertGreater(white_clip_rg, 1.65)
        self.assertGreater(yellow_clip_rg, 1.65)
        # Genuine green emitters (R < G) stay green and untouched.
        green_r, green_g, _, _ = self.execute(source, """
            let verdant = local_surface_light(vec3<f32>(0.0, -1.0, -8.0), 0.88, vec3<f32>(0.45, 0.92, 0.19));
            output[0] = vec4<f32>(verdant, 0.0);
        """)
        self.assertGreater(green_g, green_r * 1.6)

    def test_rain_increases_foliage_wind_amplitude_and_weather_removes_vanilla_blue_rain(self):
        wind_source = VERTEX_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        calm_amp, rain_amp, _, _ = self.execute(wind_source, """
            var v: VertexInput;
            v.position = vec3<f32>(2.0, 0.0, -4.0);
            v.uv = vec2<f32>(0.5, 0.0);
            v.material = 40u;
            v.light = vec2<f32>(0.0, 1.0);
            var calm_max = 0.0;
            var rain_max = 0.0;
            for (var i = 0; i < 16; i++) {
                frame.time = f32(i) * 0.25;
                frame.rain = 0.0;
                calm_max = max(calm_max, length(vertex(v) - v.position));
                frame.rain = 1.0;
                rain_max = max(rain_max, length(vertex(v) - v.position));
            }
            output[0] = vec4<f32>(calm_max, rain_max, 0.0, 0.0);
        """)
        self.assertGreater(rain_amp, calm_amp * 2.5)

        weather_source = WEATHER_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "weather"))
        rain_r, rain_b, rain_a, snow_a = self.execute(weather_source, """
            frame.sun_direction = vec3<f32>(0.3, 0.9, 0.2);
            frame.rain = 1.0;
            var drop: WeatherInput;
            // Vanilla Minecraft rain is heavily blue and nearly opaque.
            drop.color = vec4<f32>(0.08, 0.22, 0.95, 0.85);
            drop.light = vec2<f32>(0.0, 1.0);
            drop.position = vec3<f32>(0.0, 0.0, -6.0);
            drop.snow = false;
            let rain = weather(drop);
            drop.color = vec4<f32>(0.9, 0.9, 0.9, 0.9);
            drop.snow = true;
            let snow = weather(drop);
            output[0] = vec4<f32>(rain.r, rain.b, rain.a, snow.a);
        """)
        # Rain must lose its saturated vanilla blue cast and stay translucent.
        self.assertLess(rain_b / max(rain_r, 0.0001), 1.35)
        self.assertLess(rain_a, 0.35)
        self.assertGreater(rain_a, 0.08)
        self.assertGreater(snow_a, rain_a)

    def test_quality_presets_scale_fidelity_while_preserving_core_look_and_boosting_ultra_beams(self):
        # 1. Core surface lighting stays identical across Lite (0), Balanced (1), High (2), Ultra (3).
        lit_source = "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "lighting"))
        lit_body = """
            frame.sun_direction = normalize(vec3<f32>(0.90, 0.435, 0.0));
            frame.light_direction = frame.sun_direction;
            shadow = 1.0;
            let lit = shade_surface(vec3<f32>(0.0), vec3<f32>(0.0, 1.0, 0.0), 1.0,
                vec3<f32>(0.45, 0.42, 0.38), 0.0, vec3<f32>(0.0), false, false, 0.0);
            output[0] = vec4<f32>(lit, f32(CLOUD_SKY_STEPS));
        """
        preset_lit = [self.execute(lit_source, lit_body, {"quality_preset": p, "procedural_clouds": False})
                      for p in range(4)]
        for p in range(1, 4):
            for ch in range(3):
                self.assertAlmostEqual(preset_lit[0][ch], preset_lit[p][ch], places=5)
        # Cloud raymarch steps climb Balanced (10) < High (12) < Ultra (16).
        self.assertEqual(preset_lit[1][3], 10.0)
        self.assertEqual(preset_lit[2][3], 12.0)
        self.assertEqual(preset_lit[3][3], 16.0)

        # 2. Preset toggles and Ultra sun beams (higher strength + headroom -> stronger and higher-contrast rays).
        beam_source = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        beam_source += "\n" + production_function("post/composite.wgsl", "apply_air_shafts_headroom")
        beam_body = """
            let grass = vec3<f32>(0.04, 0.14, 0.03);
            let lit_beam = vec3<f32>(0.50, 0.28, 0.08);
            let shadow_gap = vec3<f32>(0.06, 0.035, 0.01);
            let beam_add = apply_air_shafts_headroom(grass, lit_beam, volumetric_strength, shaft_headroom).r - grass.r;
            let gap_add = apply_air_shafts_headroom(grass, shadow_gap, volumetric_strength, shaft_headroom).r - grass.r;
            output[0] = vec4<f32>(beam_add, gap_add, f32(volumetric_clouds), volumetric_strength);
        """
        lite = self.execute(beam_source, beam_body, {"quality_preset": 0})
        balanced = self.execute(beam_source, beam_body, {"quality_preset": 1})
        high = self.execute(beam_source, beam_body, {"quality_preset": 2})
        ultra = self.execute(beam_source, beam_body, {"quality_preset": 3})
        self.assertEqual(lite[2], 0.0)
        self.assertEqual(balanced[2], 1.0)
        self.assertAlmostEqual(balanced[0], high[0], places=5)
        self.assertGreater(ultra[0], balanced[0] * 2.2)
        self.assertGreater(ultra[0] / ultra[1], balanced[0] / balanced[1] * 1.4)

        # 3. Lite disables foliage wind while Balanced+ enables it.
        wind_source = VERTEX_INPUT + "\n".join((ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        wind_body = """
            frame.time = 1.25;
            var v: VertexInput;
            v.position = vec3<f32>(2.0, 0.0, -4.0);
            v.uv = vec2<f32>(0.5, 0.0);
            v.material = 40u;
            v.light = vec2<f32>(0.0, 1.0);
            output[0] = vec4<f32>(length(vertex(v) - v.position), 0.0, 0.0, 0.0);
        """
        self.assertEqual(self.execute(wind_source, wind_body, {"quality_preset": 0})[0], 0.0)
        self.assertGreater(self.execute(wind_source, wind_body, {"quality_preset": 1})[0], 0.005)

    def test_bayer4x4_and_atmosphere_upsample_eliminate_grain_and_thin_geometry_dropouts(self):
        # 1. Verify bayer4x4 produces all 16 stratified phases over a 4x4 block with exact mean 0.5.
        bayer_source = production_function("post/atmosphere.wgsl", "bayer4x4")
        bayer_sum, bayer_min, bayer_max, bayer_unique = self.execute(bayer_source, """
            var sum = 0.0;
            var low = 1.0;
            var high = 0.0;
            var mask = 0u;
            for (var y = 0; y < 4; y++) {
                for (var x = 0; x < 4; x++) {
                    let v = bayer4x4(vec2<f32>(f32(x) + 0.5, f32(y) + 0.5));
                    sum += v;
                    low = min(low, v);
                    high = max(high, v);
                    let bucket = u32(round(v * 16.0 - 0.5));
                    mask |= (1u << bucket);
                }
            }
            output[0] = vec4<f32>(sum / 16.0, low, high, f32(mask == 0xFFFFu));
        """)
        self.assertAlmostEqual(bayer_sum, 0.5, delta=0.00001)
        self.assertAlmostEqual(bayer_min, 0.5 / 16.0, delta=0.00001)
        self.assertAlmostEqual(bayer_max, 15.5 / 16.0, delta=0.00001)
        self.assertEqual(bayer_unique, 1.0)

        # 2. Verify production upsample_atmosphere cancels 4x4 Bayer jitter exactly, prevents
        #    thin midground geometry (bamboo/leaves) from dropping to black, merges far forest
        #    beyond shaft reach seamlessly with sky, and suppresses halos on near silhouettes.
        up_src = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        up_src += "\n" + production_function("post/atmosphere.wgsl", "bayer4x4")
        up_src += "\n" + production_function("post/composite.wgsl", "ray_distance_clamped")
        up_fn = production_function("post/composite.wgsl", "upsample_atmosphere")
        up_fn = up_fn.replace("textureDimensions(atmosphere)", "vec2<u32>(32u, 32u)")
        up_fn = up_fn.replace("textureSampleLevel(atmosphere, nearest_sampler, tap_uv, 0.0)", "test_atmosphere(tap_uv)")
        up_src += "\nvar<private> test_tap_depth: f32;\nvar<private> test_dither_amp: f32;\n"
        up_src += """
fn depth_at(uv: vec2<f32>) -> f32 { return test_tap_depth; }
fn test_atmosphere(uv: vec2<f32>) -> vec4<f32> {
    let pixel = floor(uv * 32.0) + 0.5;
    let v = 0.40 + test_dither_amp * (bayer4x4(pixel) - 0.5);
    return vec4<f32>(v, v, v, 1.0);
}
""" + up_fn
        # Perspective-like reversed-Z matrix where depth = 1.0 / distance along -Z.
        setup = """
            frame.shadow_distance = 96.0;
            frame.projection_inverse = mat4x4<f32>(
                vec4<f32>(0.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0),
                vec4<f32>(0.0, 0.0, -1.0, 0.0)
            );
            test_tap_depth = 0.0; // background sky across all half-res taps
            test_dither_amp = 0.60;
            // Subpixel variance on uniform depth (should cancel 4x4 Bayer jitter completely)
            let s0 = upsample_atmosphere(vec2<f32>(10.25 / 32.0, 10.25 / 32.0), 0.0, true).r;
            let s1 = upsample_atmosphere(vec2<f32>(10.75 / 32.0, 11.25 / 32.0), 0.0, true).r;
            // Thin 1px midground bamboo stalk (30m) in front of sky: must stay proportional, never drop to 0
            let bamboo = upsample_atmosphere(vec2<f32>(10.25 / 32.0, 10.25 / 32.0), 1.0 / 30.0, true).r;
            // Distant forest beyond Ultra reach (95m) in front of sky: matches sky seamlessly
            let far_forest = upsample_atmosphere(vec2<f32>(10.25 / 32.0, 10.25 / 32.0), 1.0 / 95.0, true).r;
            // Close foreground pillar (3m) in front of sky: strongly suppressed to prevent bright halo
            let near_pillar = upsample_atmosphere(vec2<f32>(10.25 / 32.0, 10.25 / 32.0), 1.0 / 3.0, true).r;
            output[0] = vec4<f32>(abs(s0 - s1) + abs(s0 - 0.40), bamboo, far_forest, near_pillar);
        """
        err, bamboo, far_forest, near_pillar = self.execute(up_src, setup, {"quality_preset": 3})
        self.assertLess(err, 0.0005)
        self.assertGreater(bamboo, 0.12)
        self.assertAlmostEqual(far_forest, 0.40, delta=0.001)
        self.assertLess(near_pillar, 0.025)

    def test_material_and_entity_guard_degenerate_normals_and_collinear_tangents(self):
        source = MATERIAL_INPUT + ENTITY_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material", "entity"))
        zero_n, collinear_t, nan_n, entity_zero = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.85, 0.52, 0.0));
            frame.light_direction = frame.sun_direction;
            shadow = 1.0;
            test_block_bump_grad = vec2<f32>(0.6, -0.4);
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.24, 0.42, 0.16, 1.0);
            block.shaded_tint = vec4<f32>(1.0);
            block.light.y = 1.0;
            block.position = vec3<f32>(0.0, 0.0, -12.0);
            block.face = 5u;
            // 1. Zero normal (degenerate derivative) on a bamboo stalk
            block.material = 44u;
            block.normal = vec3<f32>(0.0);
            let zero_n = shade_material(block).color.g;
            // 2. Collinear fallback tangent (1,0,0) on an East stone face with micro-relief enabled
            block.material = 60u;
            block.normal = vec3<f32>(1.0, 0.0, 0.0);
            block.tangent = vec4<f32>(1.0, 0.0, 0.0, 1.0);
            let collinear_t = shade_material(block).color.g;
            // 3. NaN normal (0/0) on a bamboo stalk
            let zero = f32(frame.has_shadow);
            let nan_val = zero / zero;
            block.material = 44u;
            block.normal = vec3<f32>(nan_val);
            let nan_n = shade_material(block).color.g;
            // 4. Entity with zero/degenerate normal
            var mob: EntityInput;
            mob.albedo = vec4<f32>(0.4, 0.4, 0.4, 1.0);
            mob.tint = vec4<f32>(1.0);
            mob.shade = 1.0;
            mob.light.y = 1.0;
            mob.position = vec3<f32>(0.0, 0.0, -8.0);
            mob.normal = vec3<f32>(0.0);
            let entity_zero = entity(mob).color.g;
            output[0] = vec4<f32>(zero_n, collinear_t, nan_n, entity_zero);
        """, {"procedural_clouds": False, "quality_preset": 3})
        for val in (zero_n, collinear_t, nan_n, entity_zero):
            self.assertGreater(val, 0.05)
            self.assertLess(val, 10.0)

    def test_bamboo_stalks_receive_sunlight_and_wave_in_lockstep_with_leaves(self):
        # 1. Bamboo stalk (48) recovers baked cardinal shade and lights cohesively with bamboo leaves (44).
        source = MATERIAL_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water", "material"))
        stalk_front, stalk_back, leaf_front, leaf_back = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(0.92, 0.39, 0.0));
            frame.light_direction = frame.sun_direction;
            shadow = 1.0;
            var block: MaterialInput;
            block.albedo = vec4<f32>(0.24, 0.46, 0.10, 1.0);
            block.light.y = 1.0;
            block.position = vec3<f32>(10.0, 0.0, 0.0);
            // Bamboo stalk with Minecraft's 0.6 baked cardinal darken on +-X faces
            block.material = 48u;
            block.shaded_tint = vec4<f32>(vec3<f32>(pow(0.6, 2.2)), 1.0);
            block.normal = vec3<f32>(1.0, 0.0, 0.0);
            let stalk_front = shade_material(block).color.g;
            block.normal = vec3<f32>(-1.0, 0.0, 0.0);
            let stalk_back = shade_material(block).color.g;
            // Attached bamboo leaves (unshaded cross planes)
            block.material = 44u;
            block.shaded_tint = vec4<f32>(1.0);
            block.normal = vec3<f32>(1.0, 0.0, 0.0);
            let leaf_front = shade_material(block).color.g;
            block.normal = vec3<f32>(-1.0, 0.0, 0.0);
            let leaf_back = shade_material(block).color.g;
            output[0] = vec4<f32>(stalk_front, stalk_back, leaf_front, leaf_back);
        """, {"procedural_clouds": False})
        self.assertGreater(stalk_front, leaf_front * 0.75)
        self.assertGreater(stalk_back, leaf_back * 0.55)

        # 2. Bamboo stalk (48) and bamboo leaves (44) displace identically in wind so leaves stay attached.
        wind_source = VERTEX_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "vertex"))
        diff, stalk_move, _, _ = self.execute(wind_source, """
            frame.time = 2.4;
            var v: VertexInput;
            v.position = vec3<f32>(4.0, 3.0, -6.0);
            v.uv = vec2<f32>(0.5, 0.5);
            v.light = vec2<f32>(0.0, 1.0);
            v.material = 44u;
            let leaf_pos = vertex(v);
            v.material = 48u;
            let stalk_pos = vertex(v);
            output[0] = vec4<f32>(length(leaf_pos - stalk_pos), length(stalk_pos - v.position), 0.0, 0.0);
        """, {"quality_preset": 3})
        self.assertAlmostEqual(diff, 0.0, places=6)
        self.assertGreater(stalk_move, 0.005)

    def test_tonemap_world_grade_warms_sunrise_and_shifts_sunset_orange_red(self):
        source = "struct TonemapInput { color: vec3<f32> }\n" + (
            ROOT / "horizon_lighting" / "tonemap.wgsl").read_text("utf-8")
        noon_rb, sunrise_rb, sunset_rb, cave_diff = self.execute(source, """
            frame.headroom = 1.0;
            frame.eye_light_smooth.y = 1.0;
            let mid = TonemapInput(vec3<f32>(0.20, 0.20, 0.20));
            // Midday (high sun): neutral daylight grade
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            let noon = tonemap(mid);
            // Sunrise (+X, low sun): warm golden grade
            frame.sun_direction = normalize(vec3<f32>(0.97, 0.22, 0.0));
            let sunrise = tonemap(mid);
            // Sunset (-X, low sun): richer orange-red grade
            frame.sun_direction = normalize(vec3<f32>(-0.97, 0.22, 0.0));
            let sunset = tonemap(mid);
            // Sealed cave during sunset: unchanged from midday
            frame.eye_light_smooth.y = 0.0;
            let cave = tonemap(mid);
            output[0] = vec4<f32>(
                noon.r / max(noon.b, 0.0001),
                sunrise.r / max(sunrise.b, 0.0001),
                sunset.r / max(sunset.b, 0.0001),
                length(cave - noon)
            );
        """)
        self.assertGreater(sunrise_rb, noon_rb + 0.25)
        self.assertGreater(sunset_rb, sunrise_rb + 0.25)
        self.assertAlmostEqual(cave_diff, 0.0, places=5)

    def test_night_moon_shafts_are_intense_cool_white_with_hazy_aerial_mist(self):
        # 1. Night moon shafts are cool silver-white (not overly blue) and clearly visible on dark terrain.
        post_src = (ROOT / "horizon_lighting" / "common.wgsl").read_text("utf-8")
        post_src += "\noverride shadows: bool = true;\noverride volumetric_samples: i32 = 24;\noverride underwater_shafts: f32 = 2.0;\n"
        post_src += """
struct PostInput { uv: vec2<f32>, pixel: vec2<f32>, depth: f32 }
fn air_shadow_visibility(position: vec3<f32>) -> f32 { return shadow; }
fn underwater_sun_scatter(d: vec3<f32>, dist: f32, j: f32, e: f32) -> vec3<f32> { return vec3<f32>(0.0); }
fn view_position(uv: vec2<f32>, depth: f32) -> vec3<f32> { return vec3<f32>(1.0 / depth, 0.0, 0.0); }
"""
        post_src += "\n" + production_function("post/atmosphere.wgsl", "bayer4x4")
        post_src += "\n" + production_function("post/atmosphere.wgsl", "integrate_air_light")
        post_src += "\n" + production_function("post/atmosphere.wgsl", "post").replace("fn post(", "fn atmosphere_post(")
        post_src += "\n" + production_function("post/composite.wgsl", "apply_air_shafts_headroom")
        shaft_add, rb_ratio, gb_ratio, blocked = self.execute(post_src, """
            frame.camera_position = vec3<f32>(0.0, 76.0, 0.0);
            frame.shadow_distance = 96.0;
            frame.sun_direction = normalize(vec3<f32>(-0.92, -0.39, 0.0));
            frame.moon_direction = -frame.sun_direction;
            frame.light_direction = frame.moon_direction;
            frame.has_shadow = 1u;
            frame.eye_light_smooth.y = 1.0;
            frame.projection_inverse = mat4x4<f32>(
                vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0),
                vec4<f32>(0.0, 0.0, -1.0, 0.0));
            frame.view_inverse = mat4x4<f32>(
                vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 1.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0));
            // Open moonlit air at 40m
            shadow = 1.0;
            let raw = atmosphere_post(PostInput(vec2<f32>(0.5, 0.5), vec2<f32>(4.5, 4.5), 1.0 / 40.0)).rgb;
            let night_base = vec3<f32>(0.008, 0.010, 0.014);
            let composited = apply_air_shafts_headroom(night_base, raw, air_shaft_strength(), 1.75);
            let added = composited - night_base;
            // Occluded shadow ray produces zero shaft
            shadow = 0.0;
            let blocked = atmosphere_post(PostInput(vec2<f32>(0.5, 0.5), vec2<f32>(4.5, 4.5), 1.0 / 40.0)).b;
            output[0] = vec4<f32>(added.b, added.r / max(added.b, 0.0001), added.g / max(added.b, 0.0001), blocked);
        """, {"procedural_clouds": False, "quality_preset": 3})
        self.assertGreater(shaft_add, 0.030)
        self.assertGreater(rb_ratio, 0.78)
        self.assertGreater(gb_ratio, 0.85)
        self.assertEqual(blocked, 0.0)

        # 2. Hazy night aerial perspective deepens cool-silver mist outdoors at night while staying crisp and zero in caves.
        fog_src = "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "fog"))
        night_op, day_op, moon_haze_b, cave_op = self.execute(fog_src, """
            frame.camera_position = vec3<f32>(0.0, 76.0, 0.0);
            frame.eye_light_smooth.y = 1.0;
            let dist_pos = vec3<f32>(90.0, 0.0, 0.0);
            // Midday baseline
            frame.sun_direction = vec3<f32>(0.0, 1.0, 0.0);
            frame.moon_direction = vec3<f32>(0.0, -1.0, 0.0);
            let day_op = aerial_opacity(dist_pos);
            // Moonrise looking toward moon
            frame.sun_direction = normalize(vec3<f32>(-0.92, -0.39, 0.0));
            frame.moon_direction = -frame.sun_direction;
            let night_op = aerial_opacity(dist_pos);
            let moon_haze_b = aerial_radiance(dist_pos).b;
            // Sealed cave at night: zero aerial perspective
            frame.eye_light_smooth.y = 0.0;
            let cave_op = aerial_opacity(dist_pos);
            output[0] = vec4<f32>(night_op, day_op, moon_haze_b, cave_op);
        """)
        self.assertGreater(night_op, day_op * 1.25)
        self.assertGreater(moon_haze_b, 0.020)
        self.assertLess(moon_haze_b, 0.040)
        self.assertEqual(cave_op, 0.0)

    def test_planar_water_reflection_reaches_screen_edges_without_vignette_falloff(self):
        source = MATERIAL_INPUT + "\n".join(
            (ROOT / "horizon_lighting" / f"{name}.wgsl").read_text("utf-8")
            for name in ("common", "gloss", "fog", "lighting", "water"))
        # Replace textureSampleLevel on the planar reflection buffer with a dark reflected treeline colour
        # so any artificial screen-edge fade to bright twilight sky immediately shows up as a red spike.
        source = source.replace(
            "textureSampleLevel(reflection, reflection_sampler, mirror_uv, 0.0)",
            "vec4<f32>(0.01, 0.04, 0.01, 1.0)")
        center_r, left_r, right_r, sky_only_r = self.execute(source, """
            frame.sun_direction = normalize(vec3<f32>(-0.998, -0.04, 0.0));
            frame.light_direction = frame.sun_direction;
            frame.sky_color = vec3<f32>(0.18, 0.06, 0.14);
            frame.fog_color = vec3<f32>(0.24, 0.08, 0.18);
            frame.camera_position = vec3<f32>(0.0, 66.0, 0.0);
            frame.water_plane = 63.0;
            frame.has_reflection = 1u;
            frame.resolution = vec2<f32>(1600.0, 900.0);
            frame.projection = mat4x4<f32>(
                vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.7, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, -1.0),
                vec4<f32>(0.0, 0.0, 0.05, 0.0));
            frame.view = mat4x4<f32>(
                vec4<f32>(1.0, 0.0, 0.0, 0.0),
                vec4<f32>(0.0, 1.0, 0.0, 0.0),
                vec4<f32>(0.0, 0.0, 1.0, 0.0),
                vec4<f32>(0.0, 0.0, 0.0, 1.0));
            var w: MaterialInput;
            w.normal = vec3<f32>(0.0, 1.0, 0.0);
            w.face = 1u;
            w.light = vec2<f32>(0.0, 1.0);
            w.position = vec3<f32>(-18.0, -3.0, 0.0);
            w.screen = vec2<f32>(0.50, 0.50);
            let center_r = shade_water(w).color.r;
            w.screen = vec2<f32>(0.01, 0.50);
            let left_r = shade_water(w).color.r;
            w.screen = vec2<f32>(0.99, 0.50);
            let right_r = shade_water(w).color.r;
            frame.has_reflection = 0u;
            let sky_only_r = shade_water(w).color.r;
            output[0] = vec4<f32>(center_r, left_r, right_r, sky_only_r);
        """, {"procedural_clouds": False, "water_ripples": 0.0})
        self.assertGreater(sky_only_r, center_r + 0.03)
        self.assertAlmostEqual(left_r, center_r, delta=0.001)
        self.assertAlmostEqual(right_r, center_r, delta=0.001)
