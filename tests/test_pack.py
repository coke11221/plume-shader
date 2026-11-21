"""Distribution and renderer-contract tests; actual WGSL is checked by Horizon."""
from pathlib import Path
import re
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "horizon_lighting"


class PackContract(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((PACK / "horizon-shaders.toml").read_text("utf-8"))

    def stage_files(self, stage):
        return [*self.manifest.get("shared", []), *stage.get("files", []), stage["file"]]

    def test_raster_only_without_hidden_shader_dependencies(self):
        self.assertEqual(self.manifest["api"], "0.2")
        self.assertNotIn("ray_tracing", self.manifest)
        self.assertEqual(self.manifest.get("textures", []), [
            {
                "id": "water_normal",
                "file": "water-normal.png",
                "filter": "linear",
                "wrap": "repeat",
            },
            {
                "id": "cloud_noise",
                "file": "cloud-noise.png",
                "filter": "linear",
                "wrap": "repeat",
            },
        ])
        for file in PACK.rglob("*.wgsl"):
            code = re.sub(r"//[^\n]*|/\*.*?\*/", "", file.read_text("utf-8"), flags=re.S)
            self.assertNotRegex(code, r"\b(trace|trace_any|trace_layers|trace_any_layers)\s*\(")
            self.assertNotRegex(code, r"@(group|binding|vertex|fragment|compute)\b")

    def test_required_stages_and_engine_pass_gates(self):
        self.assertEqual(self.manifest["frame"]["blend"], "linear")
        for name in ("material", "vertex", "weather", "entity", "tonemap"):
            self.assertTrue((PACK / self.manifest[name]["file"]).is_file())
        self.assertEqual(self.manifest["shadow"]["resolution"], 2048)
        self.assertEqual(self.manifest["shadow"]["distance"], 96.0)
        self.assertNotIn("option", self.manifest["shadow"])
        self.assertIn("reflection", self.manifest)
        self.assertNotIn("option", self.manifest["reflection"])
        self.assertEqual(self.manifest["material"].get("coverage"), "pack")
        self.assertEqual(self.manifest["entity"].get("coverage", "engine"), "engine")
        self.assertEqual(self.manifest["frame"].get("fog"), "pack", "Pack owns fog to preserve water's already-fogged background")
        self.assertNotIn("fog", self.manifest["material"])

    def test_preset_only_options_contract(self):
        options = self.manifest["options"]
        self.assertEqual(len(options), 1)
        preset = options[0]
        self.assertEqual(preset["id"], "quality_preset")
        self.assertEqual(preset["type"], "choice")
        self.assertEqual(preset["values"], ["Lite", "Balanced", "High", "Ultra"])
        self.assertEqual(preset["default"], "Balanced")
        self.assertEqual(len(self.manifest["pages"]), 1)
        self.assertEqual(self.manifest["pages"][0]["items"], ["quality_preset"])

    def test_named_targets_are_written_before_their_consumers(self):
        stages = self.manifest["post"]
        targets = {s["output"] for s in stages if "output" in s}
        written = set()
        self.assertLessEqual(len(stages), 8)
        for stage in stages:
            for file in self.stage_files(stage):
                source = (PACK / file).read_text("utf-8")
                # Resources can be read by textureSample*, textureLoad, or textureDimensions.
                uses = set(re.findall(r"\btexture\w*\(\s*(\w+)", source)) & targets
                self.assertFalse(uses - written, f"{file} reads unwritten targets: {uses - written}")
            if "output" in stage:
                self.assertNotIn(stage["output"], written)
                written.add(stage["output"])
        self.assertNotIn("output", stages[-1])

    def test_every_pack_file_is_referenced_and_pages_reach_all_options(self):
        stages = [self.manifest[k] for k in ("sky", "material", "vertex", "weather", "entity", "tonemap") if k in self.manifest]
        stages += self.manifest["post"]
        used = {"horizon-shaders.toml", "LICENSE"}
        used.update(texture["file"] for texture in self.manifest.get("textures", []))
        for stage in stages:
            used.update(self.stage_files(stage))
        actual = {p.relative_to(PACK).as_posix() for p in PACK.rglob("*") if p.is_file()}
        self.assertEqual(used, actual)
        pages = {p["id"]: p for p in self.manifest["pages"]}
        todo = [self.manifest["pages"][0]["id"]]
        visited, displayed = set(), set()
        while todo:
            current = todo.pop()
            if current in visited:
                continue
            visited.add(current)
            for item in pages[current]["items"]:
                if item.startswith("page:"):
                    todo.append(item[5:])
                elif item:
                    displayed.add(item)
        self.assertEqual(set(pages), visited)
        self.assertEqual({o["id"] for o in self.manifest["options"]}, displayed)

    def test_distribution_matches_checked_source(self):
        archive = ROOT / "dist" / f"{self.manifest['id']}-{self.manifest['version']}.hshader"
        self.assertTrue(archive.is_file(), "Run tools/check.ps1 -Package to build the distribution")
        with zipfile.ZipFile(archive) as z:
            self.assertIn("horizon-shaders.toml", z.namelist())
            source_files = {p.relative_to(PACK).as_posix(): p.read_bytes()
                            for p in PACK.rglob("*") if p.is_file()}
            self.assertEqual(set(z.namelist()), set(source_files))
            for name, content in source_files.items():
                self.assertEqual(z.read(name), content, name)

    def test_sunlight_color_is_non_editable_signature_look(self):
        option_ids = {o["id"] for o in self.manifest["options"]}
        page_ids = {p["id"] for p in self.manifest["pages"]}
        self.assertTrue(option_ids.isdisjoint({"golden_warmth", "sunlight_red", "sunlight_green", "sunlight_blue"}))
        self.assertNotIn("sunlight_color", page_ids)


if __name__ == "__main__":
    unittest.main()
