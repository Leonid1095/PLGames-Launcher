import struct
import unittest

from tools import build_forever_packs as bf

BS = "\\"


def dbc(records, fields=3):
    rsize = fields * 4
    body = b"".join(struct.pack("<3I", *r) for r in records)
    return struct.pack("<4s4I", b"WDBC", len(records), fields, rsize, 1) + body + b"\0"


def ids_of(raw):
    count, _, rsize = struct.unpack_from("<3I", raw, 4)
    return [struct.unpack_from("<I", raw, 20 + i * rsize)[0] for i in range(count)]


class SelectNamesTests(unittest.TestCase):
    def test_d_drops_terrain_tiles_and_metadata(self):
        names = ["World" + BS + "Maps" + BS + "Azeroth" + BS + "Azeroth_32_48.adt",
                 "World" + BS + "wmo" + BS + "goldshireinn.wmo",
                 "world" + BS + "generic" + BS + "tree.m2", "notes.json", "x.mtl", "y.png"]
        self.assertEqual(bf.select_names("D", names),
                         ["world" + BS + "generic" + BS + "tree.m2", "World" + BS + "wmo" + BS + "goldshireinn.wmo"])

    def test_e_drops_addon_inside_mpq(self):
        names = ["interface" + BS + "Addons" + BS + "ObjectFade" + BS + "ObjectFade.lua",
                 "Tileset" + BS + "a.blp"]
        self.assertEqual(bf.select_names("E", names), ["Tileset" + BS + "a.blp"])

    def test_dedupes_case_and_skips_internal_files(self):
        names = ["(listfile)", "A" + BS + "b.blp", "a/B.BLP"]
        self.assertEqual(bf.select_names("B", names), ["A" + BS + "b.blp"])

    def test_p_leaves_attach_table_to_merged_mpq(self):
        names = [bf.ATTACH_DBC, "DBFilesClient" + BS + "SpellVisual.dbc"]
        self.assertEqual(bf.select_names("P", names), ["DBFilesClient" + BS + "SpellVisual.dbc"])


class FixWmoGroupTests(unittest.TestCase):
    def group(self, declared, actual):
        mver = struct.pack("<4sII", b"REVM", 4, 17)
        return mver + struct.pack("<4sI", b"PGOM", declared) + b"\x01" * actual

    def test_pads_truncated_mogp_to_declared_size(self):
        fixed = bf.fix_wmo_group(self.group(declared=40, actual=16))
        self.assertEqual(len(fixed), 12 + 8 + 40)
        self.assertTrue(fixed.endswith(b"\x01" * 16 + b"\0" * 24))

    def test_leaves_consistent_files_alone(self):
        ok = self.group(declared=16, actual=16)
        self.assertIs(bf.fix_wmo_group(ok), ok)

    def test_refuses_absurd_sizes(self):
        broken = self.group(declared=10 ** 9, actual=16)
        self.assertIs(bf.fix_wmo_group(broken), broken)


class MergeDbcTests(unittest.TestCase):
    def test_primary_wins_and_new_ids_are_added_sorted(self):
        primary = dbc([(1, 10, 10), (5, 50, 50)])
        secondary = dbc([(5, 99, 99), (3, 30, 30), (7, 70, 70)])
        merged, added = bf.merge_dbc(primary, secondary)
        self.assertEqual(added, 2)
        self.assertEqual(ids_of(merged), [1, 3, 5, 7])
        rec5 = struct.unpack_from("<3I", merged, 20 + 2 * 12)
        self.assertEqual(rec5, (5, 50, 50))

    def test_rejects_different_layout(self):
        four_fields = struct.pack("<4s4I", b"WDBC", 0, 4, 16, 1) + b"\0"
        with self.assertRaises(ValueError):
            bf.merge_dbc(dbc([(1, 1, 1)]), four_fields)

    def test_rejects_string_tables(self):
        raw = struct.pack("<4s4I", b"WDBC", 0, 3, 12, 5) + b"\0abc\0"
        with self.assertRaises(ValueError):
            bf.merge_dbc(raw, raw)


class PartWriterTests(unittest.TestCase):
    def test_starts_next_part_after_limit(self):
        sizes, opened = {}, []

        class Fake:
            def __init__(self, path):
                self.path = path
                sizes[path] = 0
                opened.append(path)

            def add(self, name, data):
                sizes[self.path] += len(data)

            def close(self):
                pass

        w = bf.PartWriter(["p1", "p2", "p3"], Fake, limit=10, size_of=lambda p: sizes[p])
        for i in range(5):
            w.add(f"f{i}", b"x" * 6)
        w.close()
        self.assertEqual(opened, ["p1", "p2", "p3"])
        self.assertEqual(w.used, ["p1", "p2", "p3"])
        self.assertEqual([sizes[p] for p in opened], [12, 12, 6])

    def test_runs_out_of_letters_loudly(self):
        class Fake:
            def __init__(self, path):
                self.n = 0

            def add(self, name, data):
                self.n += len(data)

            def close(self):
                pass

        parts = {}

        def open_part(p):
            parts[p] = Fake(p)
            return parts[p]

        w = bf.PartWriter(["only"], open_part, limit=1, size_of=lambda p: parts[p].n)
        w.add("a", b"xx")
        with self.assertRaises(RuntimeError):
            w.add("b", b"xx")
