"""Hub tests: packs, options and plans, a client's subscription, overdue
clients, and the actions on client sites (the `bench` subprocess is mocked: no site is
created, changed or suspended by these tests).

Run on a hub TEST site (never the real hub):
    bench --site hub-test.localhost run-tests --app dz_hub
"""

import ast
import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from dz_core.features import bench_catalog
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from dz_hub import remote
from dz_hub.dz_hub.report.clients_en_retard import clients_en_retard
from dz_hub.setup import BASE, ONLINE, setup_all

SITE = "client-test.localhost"


def customer(name="Client Hub Test"):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert()
	return name


def make_client(features=("phone_checks",), site=SITE, online=1):
	client = frappe.new_doc("DZ Client")
	client.update({"customer": customer(), "site_name": site, "start_date": today(), "online_sales": online})
	for feature in features:
		client.append("features", {"feature": feature})
	return client.insert()


def plans(subscription):
	return sorted(row.plan for row in frappe.get_doc("Subscription", subscription).plans)


def plan_of(code):
	return frappe.db.get_value("DZ Feature", code, "subscription_plan")


class TestSetup(IntegrationTestCase):
	def test_two_packs_and_one_option_per_app_feature(self):
		setup_all()
		codes = set(frappe.get_all("DZ Feature", pluck="name"))
		self.assertEqual(codes, {BASE, ONLINE, *bench_catalog()})
		self.assertEqual(frappe.db.get_value("DZ Feature", BASE, ["kind", "app"]), ("Pack", "dz_core"))
		self.assertEqual(frappe.db.get_value("DZ Feature", ONLINE, ["kind", "app"]), ("Pack", "dz_cod"))
		self.assertEqual(
			frappe.db.get_value("DZ Feature", "courier_api", ["kind", "app"]), ("Option", "dz_cod")
		)
		for code in codes:
			plan = plan_of(code)
			self.assertEqual(frappe.db.get_value("Subscription Plan", plan, "billing_interval"), "Month")


class TestBilling(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_all()
		frappe.db.set_single_value("DZ Hub Settings", "company", frappe.db.get_value("Company", {}, "name"))

	def test_subscription_follows_the_features(self):
		client = make_client(["phone_checks"])
		self.assertTrue(client.subscription)
		self.assertEqual(
			plans(client.subscription), sorted([plan_of(BASE), plan_of(ONLINE), plan_of("phone_checks")])
		)

		client.reload()
		client.set("features", [])
		for code in ("courier_api", "labels_reports"):
			client.append("features", {"feature": code})
		client.save()
		self.assertEqual(
			plans(client.subscription),
			sorted([plan_of(BASE), plan_of(ONLINE), plan_of("courier_api"), plan_of("labels_reports")]),
		)

	def test_atelier_only_client_pays_the_base_pack(self):
		client = make_client([], site="client-atelier.localhost", online=0)
		self.assertEqual(plans(client.subscription), [plan_of(BASE)])

	def test_cod_options_need_the_online_pack(self):
		with self.assertRaises(frappe.ValidationError):
			make_client(["courier_api"], site="client-no-cod.localhost", online=0)

	def test_packs_are_not_options(self):
		client = make_client([BASE, ONLINE, "phone_checks"], site="client-base.localhost", online=0)
		self.assertEqual([row.feature for row in client.features], ["phone_checks"])
		self.assertTrue(client.online_sales)

	def test_one_monthly_invoice_with_one_line_per_plan(self):
		for code in (BASE, "phone_checks"):
			frappe.db.set_value("Subscription Plan", plan_of(code), "cost", 1000)
		client = make_client(["phone_checks"], site="client-invoice.localhost")
		subscription = frappe.get_doc("Subscription", client.subscription)
		subscription.process(posting_date=today())
		invoices = frappe.get_all(
			"Sales Invoice", filters={"subscription": client.subscription, "docstatus": 1}, pluck="name"
		)
		self.assertEqual(len(invoices), 1)
		self.assertEqual(len(frappe.get_doc("Sales Invoice", invoices[0]).items), 3)  # 2 packs + 1 option

	def test_overdue_invoice_lists_the_client(self):
		from dz_hub.dz_hub.report.clients_en_retard.clients_en_retard import get_rows

		for code in (BASE, "phone_checks"):
			frappe.db.set_value("Subscription Plan", plan_of(code), "cost", 1000)
		client = make_client(["phone_checks"], site="client-late.localhost")
		frappe.get_doc("Subscription", client.subscription).process(posting_date=today())
		invoice = frappe.get_all(
			"Sales Invoice", filters={"subscription": client.subscription, "docstatus": 1}, pluck="name"
		)[0]
		late = {"due_date": add_days(today(), -20), "status": "Overdue"}
		frappe.db.set_value("Sales Invoice", invoice, late)
		row = next(r for r in get_rows() if r["client"] == client.name)
		self.assertEqual(row["invoices"], 1)
		self.assertEqual(row["days_late"], 20)

	def test_cancelled_client_cancels_the_subscription(self):
		client = make_client(["phone_checks"], site="client-gone.localhost")
		client.db_set("status", "Résilié")
		client.reload()
		client.update_subscription()
		self.assertEqual(frappe.db.get_value("Subscription", client.subscription, "status"), "Cancelled")


class TestRemote(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_all()
		frappe.db.set_single_value("DZ Hub Settings", "company", frappe.db.get_value("Company", {}, "name"))

	def test_site_names_are_checked(self):
		for bad in ("../etc", "Client One", "a;rm -rf", ""):
			with self.assertRaises(frappe.ValidationError):
				remote.check_site_format(bad)
		remote.check_site_format("erp.client-1.com")

	def test_run_bench_uses_an_argument_list_without_shell(self):
		done = SimpleNamespace(returncode=0, stdout="ok", stderr="")
		with patch.object(remote.subprocess, "run", return_value=done) as run:
			self.assertEqual(remote.run_bench("client1.localhost", ["dz-features", "--list"]), "ok")
		command = run.call_args.args[0]
		self.assertEqual(command[-4:], ["--site", "client1.localhost", "dz-features", "--list"])
		self.assertNotIn("shell", run.call_args.kwargs)

	def test_apply_features_records_what_the_site_answered(self):
		client = make_client(["phone_checks", "labels_reports"], site="client-apply.localhost")
		on = {"courier_api": False, "phone_checks": True, "n8n_webhooks": False, "labels_reports": True}
		answer = json.dumps({"site": client.site_name, "configured": True, "features": on})
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "installed_apps", return_value=["frappe", "erpnext", "dz_core", "dz_cod"]),
			patch.object(remote, "run_bench", return_value=answer) as run,
		):
			remote.run_action(client.name, "apply_features")
		args = run.call_args.args[1]
		self.assertEqual(args[:3], ["dz-features", "--set", "labels_reports,phone_checks"])
		client.reload()
		self.assertEqual(client.applied_features, "labels_reports, phone_checks")

	def test_suspend_and_reactivate_set_maintenance_mode_and_status(self):
		client = make_client([], site="client-suspend.localhost")
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "run_bench", return_value="") as run,
		):
			remote.run_action(client.name, "suspend")
			self.assertEqual(run.call_args.args[1], ["set-maintenance-mode", "on"])
			self.assertEqual(frappe.db.get_value("DZ Client", client.name, "status"), "Suspendu")
			remote.run_action(client.name, "reactivate")
			self.assertEqual(run.call_args.args[1], ["set-maintenance-mode", "off"])
		self.assertEqual(frappe.db.get_value("DZ Client", client.name, "status"), "Actif")

	def test_a_failed_command_is_logged_and_changes_nothing(self):
		client = make_client([], site="client-fail.localhost")
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "run_bench", side_effect=remote.BenchError("site down")),
		):
			remote.run_action(client.name, "suspend")
		client.reload()
		self.assertEqual(client.status, "Actif")
		self.assertIn("site down", client.apply_log)
		self.assertIn("échec", client.last_action)

	def create(self, client, sites=(), mark=None, apps=("frappe", "erpnext")):
		"""Run "Créer le site" with bench mocked. `sites`: the sites already on
		the bench; `mark`: the client name found in an existing site's config."""
		answer = json.dumps({"site": client.site_name, "configured": True, "features": {}})
		frappe.db.set_single_value("DZ Hub Settings", "mariadb_root_password", "secret")
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "get_sites", return_value=list(sites)),
			patch.object(remote, "site_mark", return_value=mark),
			patch.object(remote, "installed_apps", return_value=list(apps)),
			patch.object(remote, "run_bench", return_value=answer) as run,
		):
			remote.run_action(client.name, "create_site")
		return [call.args[1] for call in run.call_args_list]

	def kwargs_of(self, args):
		"""What `bench execute --kwargs` gets. Bench reads it with Python's eval();
		literal_eval refuses the same things (JSON's null, true, false)."""
		return ast.literal_eval(args[-1])

	def test_create_site_for_an_online_seller(self):
		client = make_client(["courier_api"], site="client-new.localhost")
		client.db_set({"company_name": "Client Nouveau", "company_abbr": "CN", "courier": "Yalidine"})
		calls = self.create(client)
		steps = [args[0] for args in calls]
		self.assertEqual(
			steps, ["new-site", "set-config", "install-app", "execute", "dz-features", "enable-scheduler"]
		)
		self.assertEqual(calls[1], ["set-config", remote.SITE_MARK, client.name])
		self.assertEqual(calls[2], ["install-app", "dz_cod"])  # dz_cod installs dz_core first
		self.assertEqual(calls[3][1], "dz_cod.setup.new_client.prepare")
		kwargs = self.kwargs_of(calls[3])
		self.assertEqual(kwargs["features"], ["courier_api"])
		self.assertEqual(
			(kwargs["company"], kwargs["sector"], kwargs["tax_regime"]),
			("Client Nouveau", "Confection", "IFU"),
		)
		client.reload()
		self.assertTrue(client.site_created)
		# the site's Administrator password is stored encrypted, never in clear in the table
		password = client.get_password("admin_password")
		self.assertEqual(len(password), 16)
		self.assertEqual(frappe.db.get_value("DZ Client", client.name, "admin_password"), "*" * 16)
		self.assertIn(password, calls[0])

	def test_prepare_arguments_are_python_not_json(self):
		# A client without a courier, a company name with quotes and accents
		client = make_client([], site="client-quotes.localhost")
		client.db_set({"company_name": 'L\'Atelier "Été"', "company_abbr": "AE", "courier": None})
		kwargs = self.kwargs_of(remote.prepare(client))
		self.assertIsNone(kwargs["courier"])
		self.assertEqual(kwargs["company"], 'L\'Atelier "Été"')
		self.assertEqual(kwargs["features"], [])

	def test_create_site_carries_on_after_a_failed_step(self):
		# new-site ran earlier, then a step failed: the site exists and is marked as this client's
		client = make_client([], site="client-resume.localhost", online=0)
		client.db_set({"company_name": "Reprise", "company_abbr": "RP"})
		calls = self.create(client, sites=[client.site_name], mark=client.name, apps=["frappe", "erpnext"])
		self.assertEqual(
			[args[0] for args in calls], ["install-app", "execute", "dz-features", "enable-scheduler"]
		)
		client.reload()
		self.assertTrue(client.site_created)
		self.assertNotIn("échec", client.last_action)

	def test_create_site_refuses_a_site_made_for_someone_else(self):
		client = make_client([], site="client-taken.localhost", online=0)
		client.db_set({"company_name": "Pris", "company_abbr": "PR"})
		calls = self.create(client, sites=[client.site_name], mark="another-client.localhost")
		self.assertEqual(calls, [])
		client.reload()
		self.assertFalse(client.site_created)
		self.assertIn("échec", client.last_action)

	def test_create_site_for_a_producer_installs_dz_core_only(self):
		client = make_client([], site="client-miel.localhost", online=0)
		client.db_set(
			{
				"company_name": "Miel Atlas",
				"company_abbr": "MA",
				"sector": "Alimentaire et cosmétique",
				"tax_regime": "Régime réel",
			}
		)
		calls = self.create(client)
		self.assertEqual(calls[2], ["install-app", "dz_core"])
		self.assertEqual(calls[3][1], "dz_core.setup.new_client.prepare")
		kwargs = self.kwargs_of(calls[3])
		self.assertEqual(
			(kwargs["sector"], kwargs["tax_regime"]), ("Alimentaire et cosmétique", "Régime réel")
		)
		self.assertNotIn("courier", kwargs)
		self.assertFalse(any("dz_cod" in " ".join(args) for args in calls))

	def test_taking_the_online_pack_later_adds_dz_cod(self):
		client = make_client([], site="client-grows.localhost", online=1)
		client.db_set({"company_name": "Atelier Grandit", "company_abbr": "AG"})
		answer = json.dumps({"site": client.site_name, "configured": True, "features": {}})
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "installed_apps", return_value=["frappe", "erpnext", "dz_core"]),
			patch.object(remote, "run_bench", return_value=answer) as run,
		):
			remote.run_action(client.name, "apply_features")
		calls = [call.args[1] for call in run.call_args_list]
		self.assertEqual(calls[0], ["install-app", "dz_cod"])
		self.assertEqual(calls[1][1], "dz_cod.setup.new_client.prepare")
		self.assertIsNone(self.kwargs_of(calls[1])["courier"])  # was JSON null: bench refused it
		self.assertEqual(calls[2][0], "dz-features")
