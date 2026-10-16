"""Monthly billing of a client with ERPNext's Subscription.

One Subscription per client: the base plan plus one plan per optional
feature. ERPNext's daily job turns it into one Sales Invoice a month (one
line per plan); an unpaid invoice past its due date becomes "Overdue" and the
client shows in the report "Clients en retard".
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from dz_cod_hub.setup import BASE


def plans_for(client):
	"""Subscription Plans of the client: base + chosen features."""
	codes = [BASE] + [row.feature for row in client.features if row.feature != BASE]
	plans = []
	for code in codes:
		plan = frappe.db.get_value("DZ Feature", code, "subscription_plan")
		if not plan:
			frappe.throw(_("La fonction {0} n'a pas de plan d'abonnement.").format(code))
		plans.append(plan)
	return plans


def sync_subscription(client):
	"""Create or update the client's Subscription to match its features."""
	settings = frappe.get_single("DZ Hub Settings")
	if client.subscription and frappe.db.exists("Subscription", client.subscription):
		subscription = frappe.get_doc("Subscription", client.subscription)
		if client.status == "Résilié":
			if subscription.status != "Cancelled":
				subscription.cancel_subscription()
			return subscription.name
		subscription.plans = []
	elif client.status == "Résilié":
		return None
	else:
		subscription = frappe.new_doc("Subscription")
		subscription.update(
			{
				"party_type": "Customer",
				"party": client.customer,
				"company": settings.company or frappe.db.get_value("Company", {}, "name"),
				# Monthly from the start date (ERPNext's "follow calendar months"
				# needs an end date, and a client's subscription has none)
				"start_date": getdate(client.start_date or today()),
				"generate_new_invoices_past_due_date": 1,
				"submit_invoice": 1,
				"generate_invoice_at": "Beginning of the current subscription period",
				"days_until_due": settings.days_until_due or 10,
			}
		)
	for plan in plans_for(client):
		subscription.append("plans", {"plan": plan, "qty": 1})
	subscription.save(ignore_permissions=True)
	if client.subscription != subscription.name:
		client.db_set("subscription", subscription.name, update_modified=False)
	return subscription.name
