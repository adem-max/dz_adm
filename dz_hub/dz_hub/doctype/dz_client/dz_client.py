"""DZ Client: one of your clients, their site, what they pay for.

- What they buy: the Atelier pack (dz_core, always), the Vente en ligne pack
  (dz_cod) for online sellers, and options. An option belongs to an app: one
  from dz_cod needs the Vente en ligne pack.
- Saving with a different offer (or status) updates their Subscription
  (dz_hub/billing.py).
- The buttons (dz_client.js) run actions on their site (dz_hub/remote.py):
  Créer le site, Appliquer au site, Suspendre, Réactiver.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from dz_hub.billing import sync_subscription
from dz_hub.remote import check_site_format
from dz_hub.setup import BASE, CORE_APP, ONLINE, ONLINE_APP


class DZClient(Document):
	def validate(self):
		self.site_name = (self.site_name or "").strip().lower()
		check_site_format(self.site_name)  # the site itself may not exist yet
		if self.company_abbr:
			self.company_abbr = self.company_abbr.strip().upper()
		# Packs are fields, not options: the Atelier pack is always billed
		if any(row.feature == ONLINE for row in self.features):
			self.online_sales = 1
		self.features = [row for row in self.features if row.feature not in (BASE, ONLINE)]
		self.check_options()
		self.check_sector()

	def apps(self):
		"""The apps this client's site gets."""
		return [CORE_APP, ONLINE_APP] if self.online_sales else [CORE_APP]

	def check_options(self):
		apps = self.apps()
		for row in self.features:
			app = frappe.db.get_value("DZ Feature", row.feature, "app")
			if app and app not in apps:
				frappe.throw(
					_("L'option {0} fait partie de {1} : cochez « Vente en ligne » ou retirez-la.").format(
						row.feature, app
					)
				)

	def check_sector(self):
		"""The choices must match what dz_core's prepare() knows (it is on this bench)."""
		from dz_core.dz_core.doctype.dz_core_settings.dz_core_settings import IFU, REEL
		from dz_core.setup.sectors import SECTORS

		if self.sector and self.sector not in SECTORS:
			frappe.throw(_("Secteur inconnu de dz_core : {0}").format(self.sector))
		if self.tax_regime and self.tax_regime not in (IFU, REEL):
			frappe.throw(_("Régime fiscal inconnu : {0}").format(self.tax_regime))

	def on_update(self):
		changed = any(self.has_value_changed(field) for field in ("features", "status", "online_sales"))
		if changed or not self.subscription:
			sync_subscription(self)

	@frappe.whitelist()
	def update_subscription(self):
		frappe.only_for("System Manager")
		name = sync_subscription(self)
		return _("Abonnement {0} à jour.").format(name) if name else _("Pas d'abonnement (client résilié).")
