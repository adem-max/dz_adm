"""Hub tests: features and plans, a client's subscription, overdue clients, and
the actions on client sites (the `bench` subprocess is mocked: no site is
created, changed or suspended by these tests).

Run on a hub TEST site (never the real hub):
    bench --site hub-test.localhost run-tests --app dz_cod_hub
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from dz_cod.features import FEATURES
from dz_cod_hub import remote
from dz_cod_hub.dz_cod_hub.report.clients_en_retard import clients_en_retard  # noqa: F401 (import check)
from dz_cod_hub.setup import BASE, setup_all

SITE = "client-test.localhost"


def customer(name="Client Hub Test"):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert()
	return name


def make_client(features=("phone_checks",), site=SITE):
	client = frappe.new_doc("DZ Client")
	client.update({"customer": customer(), "site_name": site, "start_date": today()})
	for feature in features:
		client.append("features", {"feature": feature})
	return client.insert()


def plans(subscription):
	return sorted(row.plan for row in frappe.get_doc("Subscription", subscription).plans)


def plan_of(code):
	return frappe.db.get_value("DZ Feature", code, "subscription_plan")


class TestSetup(IntegrationTestCase):
	def test_one_feature_and_plan_per_dz_cod_feature_plus_base(self):
		setup_all()
		codes = set(frappe.get_all("DZ Feature", pluck="name"))
		self.assertEqual(codes, {BASE, *FEATURES})
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
		self.assertEqual(plans(client.subscription), sorted([plan_of(BASE), plan_of("phone_checks")]))

		client.reload()
		client.set("features", [])
		for code in ("courier_api", "labels_reports"):
			client.append("features", {"feature": code})
		client.save()
		self.assertEqual(
			plans(client.subscription),
			sorted([plan_of(BASE), plan_of("courier_api"), plan_of("labels_reports")]),
		)

	def test_base_cannot_be_chosen_twice(self):
		client = make_client([BASE, "phone_checks"], site="client-base.localhost")
		self.assertEqual([row.feature for row in client.features], ["phone_checks"])

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
		self.assertEqual(len(frappe.get_doc("Sales Invoice", invoices[0]).items), 2)

	def test_overdue_invoice_lists_the_client(self):
		from dz_cod_hub.dz_cod_hub.report.clients_en_retard.clients_en_retard import get_rows

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
			self.assertEqual(remote.run_bench("client1.localhost", ["dz-cod-features", "--list"]), "ok")
		command = run.call_args.args[0]
		self.assertEqual(command[-4:], ["--site", "client1.localhost", "dz-cod-features", "--list"])
		self.assertNotIn("shell", run.call_args.kwargs)

	def test_apply_features_records_what_the_site_answered(self):
		client = make_client(["phone_checks", "labels_reports"], site="client-apply.localhost")
		on = {"courier_api": False, "phone_checks": True, "n8n_webhooks": False, "labels_reports": True}
		answer = json.dumps({"site": client.site_name, "configured": True, "features": on})
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "run_bench", return_value=answer) as run,
		):
			remote.run_action(client.name, "apply_features")
		args = run.call_args.args[1]
		self.assertEqual(args[:3], ["dz-cod-features", "--set", "labels_reports,phone_checks"])
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

	def test_create_site_runs_the_steps_in_order(self):
		frappe.db.set_single_value("DZ Hub Settings", "mariadb_root_password", "secret")
		client = make_client(["courier_api"], site="client-new.localhost")
		client.db_set({"company_name": "Client Nouveau", "company_abbr": "CN", "courier": "Yalidine"})
		with (
			patch("frappe.db.commit"),
			patch.object(remote, "check_site_name"),
			patch.object(remote, "run_bench", return_value="") as run,
		):
			remote.run_action(client.name, "create_site")
		steps = [call.args[1][0] for call in run.call_args_list]
		self.assertEqual(steps, ["new-site", "install-app", "execute", "enable-scheduler"])
		kwargs = json.loads(run.call_args_list[2].args[1][-1])
		self.assertEqual(kwargs["features"], ["courier_api"])
		self.assertEqual(kwargs["company"], "Client Nouveau")
		client.reload()
		self.assertTrue(client.site_created)
		self.assertTrue(client.get_password("admin_password"))
