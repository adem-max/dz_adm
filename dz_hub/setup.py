"""Run after install and after every migrate on the hub site.

Creates what you sell, as DZ Feature records, each with a service Item and a
monthly Subscription Plan used to bill clients:

- two packs: "Pack Atelier" (dz_core, every client, always billed) and
  "Vente en ligne" (dz_cod, online sellers);
- one option per optional feature the apps declare (`dz_features` hook,
  read with dz_core.features.bench_catalog from every app on this bench:
  the apps are not installed on the hub site itself).

Prices start at 0: set them on the Subscription Plans (Abonnements) when the
offer is decided. Existing records are never overwritten (prices you typed
are kept); patches/rename_billing.py moved the records made before the
hub was renamed.
"""

import frappe

ITEM_GROUP = "Abonnements DZ"
BASE = "base"  # Pack Atelier, always billed
ONLINE = "vente_en_ligne"  # Pack Vente en ligne
CORE_APP = "dz_core"
ONLINE_APP = "dz_cod"

PACKS = [
	(BASE, "Pack Atelier", "Production, stock, achats, ventes, factures, import Excel.", CORE_APP, 1),
	(ONLINE, "Vente en ligne", "Commandes COD, transporteurs, retours, versements.", ONLINE_APP, 0),
]


def after_install():
	# Installing dz_hub on a hub that ran dz_cod_hub: Frappe marks a new app's
	# patches as done without running them, so run the rename here
	from dz_hub.patches.clients_were_online_sellers import execute as clients_were_online_sellers
	from dz_hub.patches.rename_billing import execute as rename_billing

	rename_billing()
	setup_all()
	clients_were_online_sellers()


def after_migrate():
	setup_all()


def feature_list():
	"""[(code, label, description, app, kind, is_base)]: the packs, then every app's options."""
	from dz_core.features import bench_catalog

	features = [
		(code, label, description, app, "Pack", is_base) for code, label, description, app, is_base in PACKS
	]
	features += [
		(code, f["label"], f["description"], f["app"], "Option", 0) for code, f in bench_catalog().items()
	]
	return features


def setup_all():
	if not frappe.db.get_value("Company", {}, "name"):
		return  # setup wizard not done yet: items and plans need a company and currency
	ensure_item_group()
	for code, label, description, app, kind, is_base in feature_list():
		item = ensure_item(code, label)
		plan = ensure_plan(label, item)
		if frappe.db.exists("DZ Feature", code):
			# Keep your label and description; only fill what older records lack
			frappe.db.set_value("DZ Feature", code, {"kind": kind, "app": app}, update_modified=False)
			continue
		frappe.get_doc(
			{
				"doctype": "DZ Feature",
				"code": code,
				"label": label,
				"description": description,
				"kind": kind,
				"app": app,
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
			{
				"doctype": "Item Group",
				"item_group_name": ITEM_GROUP,
				"parent_item_group": get_root_of("Item Group"),
			}
		).insert(ignore_permissions=True)


def item_code(code):
	return f"DZ-{code.upper().replace('_', '-')}"


def plan_name(label):
	return f"DZ - {label}"


def ensure_item(code, label):
	name = item_code(code)
	if not frappe.db.exists("Item", name):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": f"Abonnement - {label}",
				"item_group": ITEM_GROUP,
				"stock_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
			}
		).insert(ignore_permissions=True)
	return name


def ensure_plan(label, item):
	name = plan_name(label)
	if not frappe.db.exists("Subscription Plan", name):
		company = frappe.db.get_single_value("DZ Hub Settings", "company") or frappe.db.get_value(
			"Company", {}, "name"
		)
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
