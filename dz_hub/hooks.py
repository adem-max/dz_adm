"""DZ Hub: the vendor's own site to manage every client (Daftar apps).

Installed ONLY on the vendor's hub site (never on a client site). It needs
ERPNext (customers, subscriptions, invoices) and the client apps present on
the same bench: dz_core always (it reads the offer through
dz_core.features.bench_catalog and runs `bench` for client sites), dz_cod for
online sellers. Neither is installed on the hub site itself.
"""

app_name = "dz_hub"
app_title = "DZ Hub"
app_publisher = "Adem"
app_description = "Client management and billing for the Daftar apps (vendor only)"
app_email = "adembenlecheb1@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

# A tile on the apps screen that opens the client list
add_to_apps_screen = [
	{
		"name": "dz_hub",
		"logo": "/assets/erpnext/images/erpnext-logo.svg",
		"title": "Hub DZ",
		"route": "/desk/dz-client",
		"has_permission": "dz_hub.hooks_permission.is_system_manager",
	}
]

# Features, billing items and monthly plans (dz_hub/setup.py)
after_install = "dz_hub.setup.after_install"
after_migrate = "dz_hub.setup.after_migrate"

# A fresh test site gets a company and the offer before the tests (dz_hub/tests/utils.py)
before_tests = "dz_hub.tests.utils.before_tests"
