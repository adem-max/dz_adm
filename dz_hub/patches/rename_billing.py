"""One-time move of the billing records made while the hub was "dz_cod_hub".

Item group "Abonnements DZ COD" -> "Abonnements DZ", items "DZCOD-<CODE>" ->
"DZ-<CODE>", plans "COD - <label>" -> "DZ - <label>", and the old "Base COD"
becomes "Pack Atelier". Renaming (not recreating) keeps every Subscription
pointing at its plans and keeps the prices you typed.
"""

import frappe

from dz_hub.setup import BASE, ITEM_GROUP, item_code, plan_name

OLD_ITEM_GROUP = "Abonnements DZ COD"
NEW_BASE_LABEL = "Pack Atelier"
NEW_BASE_DESCRIPTION = "Production, stock, achats, ventes, factures, import Excel."


def execute():
	if frappe.db.exists("Item Group", OLD_ITEM_GROUP) and not frappe.db.exists("Item Group", ITEM_GROUP):
		frappe.rename_doc("Item Group", OLD_ITEM_GROUP, ITEM_GROUP, force=True)

	for feature in frappe.get_all("DZ Feature", fields=["name", "label", "item", "subscription_plan"]):
		label = NEW_BASE_LABEL if feature.name == BASE else feature.label
		new_item = item_code(feature.name)
		if feature.item and feature.item != new_item and not frappe.db.exists("Item", new_item):
			frappe.rename_doc("Item", feature.item, new_item, force=True)
			frappe.db.set_value("Item", new_item, "item_name", f"Abonnement - {label}")
		new_plan = plan_name(label)
		if (
			feature.subscription_plan
			and feature.subscription_plan != new_plan
			and not frappe.db.exists("Subscription Plan", new_plan)
		):
			frappe.rename_doc("Subscription Plan", feature.subscription_plan, new_plan, force=True)
			frappe.db.set_value("Subscription Plan", new_plan, "plan_name", new_plan)
		if feature.name == BASE:
			frappe.db.set_value("DZ Feature", BASE, {"label": label, "description": NEW_BASE_DESCRIPTION})
