import frappe


def is_system_manager():
	"""The hub is for the vendor only."""
	return "System Manager" in frappe.get_roles()
