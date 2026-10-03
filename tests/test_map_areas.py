import os
import struct
import unittest

from tools import build_map_areas as bma

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dbc(rows):
    body = b"".join(struct.pack("<4I4f3i", rid, m, area, 0, left, right, top, bottom, -1, 0, 0)
                    for rid, m, area, left, right, top, bottom in rows)
    return struct.pack("<4s4I", b"WDBC", len(rows), 11, 44, 1) + body + b"\0"


class MapAreasTests(unittest.TestCase):
    def test_parse_and_render(self):
        raw = dbc([(11, 1, 17, 2622.917, -7510.417, 1612.5, -5143.75), (5, 0, 0, 0, 0, 0, 0)])
        rows = bma.parse_world_map_area(raw)
        self.assertEqual([r[:3] for r in rows], [(11, 1, 17), (5, 0, 0)])
        text = bma.render_lua(rows)
        self.assertIn("[11] = {1, 17, 2622.917, -7510.417, 1612.5, -5143.75},", text)
        self.assertNotIn("[5] =", text)  # запись без границ пропускается

    def test_rejects_other_layout(self):
        raw = struct.pack("<4s4I", b"WDBC", 0, 10, 40, 1) + b"\0"
        with self.assertRaises(ValueError):
            bma.parse_world_map_area(raw)

    def test_generated_table_name_matches_addon(self):
        with open(os.path.join(ROOT, "addons", "PLGames_Events", "Core.lua"), encoding="utf-8") as f:
            core = f.read()
        with open(os.path.join(ROOT, "addons", "PLGames_Events", "MapAreas.lua"), encoding="utf-8") as f:
            areas = f.read()
        self.assertIn("E.IndexAreas(PLGamesEventsMapAreas)", core)
        self.assertIn("PLGamesEventsMapAreas = {", areas)
        self.assertIn("PLGamesEventsMapAreas = {", bma.render_lua([]))
