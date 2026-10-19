// DZ Client: buttons that act on the client's site (dz_hub/remote.py)
// and on their billing (dz_hub/billing.py).

frappe.ui.form.on("DZ Client", {
	setup(frm) {
		frappe.realtime.on("dz_client_updated", (data) => {
			if (data.client !== frm.doc.name) return;
			frappe.show_alert(
				{
					message: `${data.title} : ${data.failed ? __("échec, voir le journal") : "OK"}`,
					indicator: data.failed ? "red" : "green",
				},
				10
			);
			frm.reload_doc();
		});
	},

	onload(frm) {
		// Packs are fields of the client (Atelier always, Vente en ligne ticked):
		// the table only offers options
		frm.set_query("features", () => ({ filters: { kind: "Option" } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		show_indicator(frm);

		const run = (action, confirm_text) => {
			const go = () =>
				frappe
					.xcall("dz_hub.remote.start", { client: frm.doc.name, action })
					.then((message) => frappe.show_alert({ message, indicator: "blue" }, 8));
			confirm_text ? frappe.confirm(confirm_text, go) : go();
		};

		if (!frm.doc.site_created) {
			frm.add_custom_button(
				__("Créer le site"),
				() =>
					run(
						"create_site",
						__("Créer le site {0} avec ERPNext et {1} ? Cela prend quelques minutes.", [
							frm.doc.site_name,
							frm.doc.online_sales ? "dz_core + dz_cod" : "dz_core",
						])
					),
				__("Site")
			);
		}
		frm.add_custom_button(__("Appliquer au site"), () => run("apply_features"), __("Site"));
		if (frm.doc.status === "Suspendu") {
			frm.add_custom_button(__("Réactiver"), () => run("reactivate"), __("Site"));
		} else if (frm.doc.status === "Actif") {
			frm.add_custom_button(
				__("Suspendre"),
				() =>
					run(
						"suspend",
						__("Suspendre {0} ? Le site affichera une page de maintenance jusqu'à la réactivation.", [
							frm.doc.site_name,
						])
					),
				__("Site")
			);
		}
		frm.add_custom_button(__("Mettre à jour l'abonnement"), () =>
			frm.call("update_subscription").then((r) => {
				frappe.show_alert({ message: r.message, indicator: "green" });
				frm.reload_doc();
			})
		);
	},
});

// Orange "Non appliqué" when the site does not have the options the client pays for
function show_indicator(frm) {
	const chosen = (frm.doc.features || []).map((row) => row.feature).sort().join(", ") || "-";
	const applied = frm.doc.applied_features || "";
	if (applied && applied !== chosen) {
		frm.dashboard.set_headline_alert(
			__("Fonctions non appliquées au site : choisies {0}, sur le site {1}.", [chosen, applied]),
			"orange"
		);
	} else if (!applied) {
		frm.dashboard.set_headline_alert(__("Fonctions jamais appliquées à ce site."), "orange");
	} else {
		frm.dashboard.clear_headline();
	}
}
