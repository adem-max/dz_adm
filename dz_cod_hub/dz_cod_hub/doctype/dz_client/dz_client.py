"""DZ Client: one of your clients, their site, what they pay for.

- Saving with different features (or status) updates their Subscription
  (dz_cod_hub/billing.py).
- The buttons (dz_client.js) run actions on their site (dz_cod_hub/remote.py):
  Créer le site, Appliquer au site, Suspendre, Réactiver.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from dz_cod_hub.billing import sync_subscription
from dz_cod_hub.remote import check_site_format
from dz_cod_hub.setup import BASE


class DZClient(Document):
	def validate(self):
		self.site_name = (self.site_name or "").strip().lower()
		check_site_format(self.site_name)  # the site itself may not exist yet
		self.features = [row for row in self.features if row.feature != BASE]  # base is always billed
		if self.company_abbr:
			self.company_abbr = self.company_abbr.strip().upper()

	def on_update(self):
		changed = self.has_value_changed("features") or self.has_value_changed("status")
		if changed or not self.subscription:
			sync_subscription(self)

	@frappe.whitelist()
	def update_subscription(self):
		frappe.only_for("System Manager")
		name = sync_subscription(self)
		return _("Abonnement {0} à jour.").format(name) if name else _("Pas d'abonnement (client résilié).")
