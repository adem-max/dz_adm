"""Run after install and after every migrate on the hub site.

Creates one DZ Feature per dz_cod optional feature (the list lives in
dz_cod/features.py, on the same bench), plus "base", each with a service Item
and a monthly Subscription Plan used to bill clients. Prices start at 0:
set them on the Subscription Plans (Abonnements) when the offer is decided.
Existing records are never overwritten (prices you typed are kept).
"""

import frappe

ITEM_GROUP = "Abonnements DZ COD"
BASE = "base"


def after_install():
	setup_all()


def after_migrate():
	setup_all()


def feature_list():
	"""[(code, label, description, is_base)]: base first, then dz_cod's features."""
	from dz_cod.features import FEATURES

	features = [(BASE, "Base COD", "Commandes, stock, versements, transporteurs manuels.", 1)]
	features += [(code, f["label"], f["description"], 0) for code, f in FEATURES.items()]
	return features


def setup_all():
	if not frappe.db.get_value("Company", {}, "name"):
		return  # setup wizard not done yet: items and plans need a company and currency
	ensure_item_group()
	for code, label, description, is_base in feature_list():
		item = ensure_item(code, label)
		plan = ensure_plan(code, label, item)
		if frappe.db.exists("DZ Feature", code):
			continue
		frappe.get_doc(
			{
				"doctype": "DZ Feature",
				"code": code,
				"label": label,
				"description": description,
				"is_base": is_base,
				"item": item,
				"subscription_plan": plan,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()


def ensure_item_group():
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		from frappe.utils.nestedset import get_root_of

		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": get_root_of("Item Group")}
		).insert(ignore_permissions=True)


def item_code(code):
	return f"DZCOD-{code.upper().replace('_', '-')}"


def ensure_item(code, label):
	name = item_code(code)
	if not frappe.db.exists("Item", name):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": f"Abonnement COD - {label}",
				"item_group": ITEM_GROUP,
				"stock_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
			}
		).insert(ignore_permissions=True)
	return name


def ensure_plan(code, label, item):
	name = f"COD - {label}"
	if not frappe.db.exists("Subscription Plan", name):
		company = frappe.db.get_single_value("DZ Hub Settings", "company") or frappe.db.get_value("Company", {}, "name")
		frappe.get_doc(
			{
				"doctype": "Subscription Plan",
				"plan_name": name,
				"item": item,
				"currency": frappe.get_cached_value("Company", company, "default_currency"),
				"price_determination": "Fixed Rate",
				"cost": 0,
				"billing_interval": "Month",
				"billing_interval_count": 1,
			}
		).insert(ignore_permissions=True)
	return name
