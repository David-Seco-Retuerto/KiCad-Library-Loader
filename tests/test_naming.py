"""Synthetic compact-name cases retain identity without vendor prose or aliases."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import dump, parse, suggestion


class NamingTests(unittest.TestCase):
    def name(self, mpn, geometry, description):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'synthetic.kicad_mod'
            tree = parse('(footprint "TEST" (descr "TEST"))')
            tree[1], tree[2][1] = geometry, description
            path.write_text(dump(tree), encoding='utf-8')
            return suggestion(SimpleNamespace(mpn=mpn), path)

    def test_specific_geometry_does_not_repeat_package_aliases_or_case_revisions(self):
        self.assertEqual(self.name('PART123', 'SOT96P237X111-3N', 'SOT-23, TO-236, CASE 318-08 ISSUE AR'), 'PART123_SOT96P237X111-3N')
        self.assertEqual(self.name('ADC123', 'SOP65P640X120-24N', 'RU-24, TSSOP'), 'ADC123_SOP65P640X120-24N')

    def test_part_repeated_as_geometry_is_only_included_once(self):
        self.assertEqual(self.name('MODULE-1-N4R8', 'MODULE1N4R8', '41-SMD 2026'), 'MODULE-1-N4R8')
        self.assertEqual(self.name('CHIP123', 'CHIP123', 'SOIC-8 package, drawing revision 42'), 'CHIP123_SOIC-8')

    def test_generic_geometry_uses_only_a_known_compact_description(self):
        self.assertEqual(self.name('TEST123', 'GEOM', 'SOIC 1-pin test'), 'TEST123_GEOM_SOIC-1')
        self.assertEqual(self.name('TEST123', 'GEOM', 'Vendor case drawing 300 Issue AA'), 'TEST123_GEOM')
        self.assertEqual(self.name('TEST123', 'QFN-16_3x3mm_P0.5mm', 'QFN, 16 pins, case 99'), 'TEST123_QFN-16_3x3mm_P0.5mm')

    def test_long_identities_are_bounded_and_remain_distinct(self):
        first = self.name('A' * 110 + '1', 'GEOM', '')
        second = self.name('A' * 110 + '2', 'GEOM', '')
        self.assertLessEqual(len(first), 100)
        self.assertNotEqual(first, second)
        self.assertEqual(first, self.name('A' * 110 + '1', 'GEOM', ''))
