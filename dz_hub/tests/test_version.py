"""The hub refuses to run on a dz_core older than DZ_CORE_MIN (dz_hub/__init__.py)."""

from unittest.mock import patch

import dz_core
from frappe.tests import UnitTestCase

import dz_hub


class TestDzCoreVersion(UnitTestCase):
	def test_versions_compare_as_numbers(self):
		self.assertLess(dz_hub.version_tuple("0.9.0"), dz_hub.version_tuple("0.10.0"))
		self.assertEqual(dz_hub.version_tuple("1.2"), (1, 2))

	def test_this_bench_is_new_enough(self):
		dz_hub.check_dz_core()

	def test_an_older_dz_core_is_refused_with_the_fix(self):
		with patch.object(dz_core, "__version__", "0.0.9"), patch.object(dz_hub, "DZ_CORE_MIN", "0.1.0"):
			with self.assertRaises(ImportError) as error:
				dz_hub.check_dz_core()
		self.assertIn("update apps/dz_core", str(error.exception))
