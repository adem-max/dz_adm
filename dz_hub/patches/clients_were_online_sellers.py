"""Clients made while the hub was "dz_cod_hub" were all online sellers: that
hub only made dz_cod sites. Tick "Vente en ligne" for them, so their COD
options stay valid and their Subscription gets the Vente en ligne plan.
"""

import frappe


def execute():
	for name in frappe.get_all("DZ Client", filters={"online_sales": 0}, pluck="name"):
		client = frappe.get_doc("DZ Client", name)
		client.online_sales = 1
		client.save(ignore_permissions=True)
