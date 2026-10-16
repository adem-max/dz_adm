"""Report "Clients en retard": clients with an unpaid invoice past its due date.

ERPNext marks a submitted Sales Invoice "Overdue" (daily job) once its due
date has passed. "Tolérance" in DZ Hub Settings keeps clients only a few days
late out of the list. Suspension stays manual: open the client, "Suspendre".
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, today

OVERDUE = ("Overdue", "Overdue and Discounted")


def execute(filters=None):
	return get_columns(), get_rows()


def get_columns():
	return [
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Link", "options": "DZ Client", "width": 200},
		{"fieldname": "customer", "label": _("Facturé à"), "fieldtype": "Link", "options": "Customer", "width": 180},
		{"fieldname": "status", "label": _("État"), "fieldtype": "Data", "width": 90},
		{"fieldname": "invoices", "label": _("Factures en retard"), "fieldtype": "Int", "width": 130},
		{"fieldname": "outstanding", "label": _("Montant dû"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "oldest_due", "label": _("Plus ancienne échéance"), "fieldtype": "Date", "width": 150},
		{"fieldname": "days_late", "label": _("Jours de retard"), "fieldtype": "Int", "width": 120},
	]


def get_rows():
	grace = cint(frappe.db.get_single_value("DZ Hub Settings", "grace_days"))
	limit = add_days(today(), -grace)
	clients = frappe.get_all("DZ Client", fields=["name", "customer", "status"])
	rows = []
	for client in clients:
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={
				"customer": client.customer,
				"docstatus": 1,
				"status": ["in", OVERDUE],
				"due_date": ["<=", limit],
			},
			fields=["outstanding_amount", "due_date"],
		)
		if not invoices:
			continue
		oldest = min(invoice.due_date for invoice in invoices)
		rows.append(
			{
				"client": client.name,
				"customer": client.customer,
				"status": _(client.status),
				"invoices": len(invoices),
				"outstanding": sum(invoice.outstanding_amount for invoice in invoices),
				"oldest_due": oldest,
				"days_late": date_diff(today(), oldest),
			}
		)
	return sorted(rows, key=lambda row: -row["days_late"])
