"""DZ COD Hub: the vendor's own site to manage dz-cod clients.

Installed ONLY on the vendor's hub site (never on a client site). It needs
ERPNext (customers, subscriptions, invoices) and the dz_cod app present on the
same bench (it reads dz_cod/features.py and runs `bench` for client sites),
but dz_cod is not installed on the hub site itself.
"""

app_name = "dz_cod_hub"
app_title = "DZ COD Hub"
app_publisher = "Adem"
app_description = "Client management and billing for dz-cod (vendor only)"
app_email = "adembenlecheb1@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

# A tile on the apps screen that opens the client list
add_to_apps_screen = [
	{
		"name": "dz_cod_hub",
		"logo": "/assets/erpnext/images/erpnext-logo.svg",
		"title": "Hub COD",
		"route": "/desk/dz-client",
		"has_permission": "dz_cod_hub.hooks_permission.is_system_manager",
	}
]

# Features, billing items and monthly plans (dz_cod_hub/setup.py)
after_install = "dz_cod_hub.setup.after_install"
after_migrate = "dz_cod_hub.setup.after_migrate"
