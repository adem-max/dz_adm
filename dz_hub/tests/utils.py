"""Before the hub's tests (hooks.py before_tests): a fresh test site gets the
setup wizard (a company to bill from) and the packs and options, so the tests
run the same on a new site (CI) as on hub-test.localhost."""

import frappe

from dz_hub.setup import setup_all

COMPANY = "Hub Test DZ"
ABBR = "HTD"


def before_tests():
	if not frappe.is_setup_complete():
		# dz_core's wizard (Algeria, DZD, French): the hub does not install
		# dz_core, but its code is on the bench (plain import)
		from dz_core.setup.new_client import run_setup_wizard

		run_setup_wizard(COMPANY, ABBR)
	setup_all()
	frappe.db.commit()
