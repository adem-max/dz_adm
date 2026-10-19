"""Actions the hub runs on a client's site (same bench, same server).

Each action is a background job (queue "long") that runs `bench` for the
client's site in a separate process, exactly like typing it in a terminal:

    python -m frappe.utils.bench_helper frappe --site <site> <command...>

Why a separate process: a site's config and cache can only be changed safely
from inside that site's own process (file locks and Redis keys are per site).
The output is kept in DZ Client "Journal de la dernière action".

Every client site runs dz_core; online sellers also get dz_cod on top. The
hub talks to dz_core first and to dz_cod only for what dz_cod adds:

- create_site: new site with ERPNext, then the client's apps (dz_core, or
  dz_cod which installs dz_core first), then the right prepare():
  dz_core.setup.new_client.prepare (sector, tax regime) or, for an online
  seller, dz_cod.setup.new_client.prepare (which runs dz_core's first and
  adds the COD part), then the options with dz_core's `dz-features`
- apply_features: adds dz_cod (and its prepare) when the client took the
  Vente en ligne pack since, then `dz-features --set <options>`. Dropping the
  pack never uninstalls dz_cod (that would delete its orders): its options
  are switched off and the log says so.
- suspend / reactivate: maintenance mode on / off (an unpaid client)
"""

import json
import re
import subprocess
import sys

import frappe
from frappe import _
from frappe.utils import get_bench_path, get_sites, now_datetime

from dz_hub.setup import BASE, CORE_APP, ONLINE, ONLINE_APP

SITE_NAME = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
TIMEOUT = {"create_site": 1800, "apply_features": 1800, "suspend": 120, "reactivate": 120}


class BenchError(Exception):
	pass


def check_site_format(site):
	if not site or not SITE_NAME.match(site) or ".." in site:
		frappe.throw(_("Nom de site invalide : {0}").format(site))


def check_site_name(site, must_exist=True):
	check_site_format(site)
	exists = site in get_sites()
	if must_exist and not exists:
		frappe.throw(_("Le site {0} n'existe pas sur ce serveur.").format(site))
	if not must_exist and exists:
		frappe.throw(_("Le site {0} existe déjà.").format(site))


def run_bench(site, args, timeout=300):
	"""Run one bench command for `site`. Returns its output; raises BenchError."""
	command = [sys.executable, "-m", "frappe.utils.bench_helper", "frappe", "--site", site, *args]
	result = subprocess.run(
		command,
		cwd=f"{get_bench_path()}/sites",
		capture_output=True,
		text=True,
		timeout=timeout,
		check=False,
	)
	output = (result.stdout or "") + (result.stderr or "")
	if result.returncode != 0:
		raise BenchError(output[-4000:])
	return output


def features_of(client):
	return sorted(row.feature for row in client.features if row.feature not in (BASE, ONLINE))


def installed_apps(site):
	output = run_bench(site, ["execute", "frappe.get_installed_apps"])
	return json.loads(output.strip().splitlines()[-1])


def prepare(client):
	"""bench execute arguments for the client's prepare(): dz_core's, or dz_cod's on top."""
	kwargs = {
		"company": client.company_name,
		"abbr": client.company_abbr,
		"sector": client.sector or "Confection",
		"tax_regime": client.tax_regime or "IFU",
	}
	if client.online_sales:
		kwargs.update({"courier": client.courier or None, "features": features_of(client)})
		return ["execute", "dz_cod.setup.new_client.prepare", "--kwargs", json.dumps(kwargs)]
	return ["execute", "dz_core.setup.new_client.prepare", "--kwargs", json.dumps(kwargs)]


def set_features(client):
	"""dz_core's command: the site's options = what the client pays for."""
	output = run_bench(client.site_name, ["dz-features", "--set", ",".join(features_of(client)), "--json"])
	answer = json.loads(output.strip().splitlines()[-1])
	return output, sorted(name for name, on in answer["features"].items() if on)


# ------------------------------------------------------------------ the actions


def do_create_site(client):
	check_site_name(client.site_name, must_exist=False)
	settings = frappe.get_single("DZ Hub Settings")
	root_password = settings.get_password("mariadb_root_password", raise_exception=False)
	if not root_password:
		frappe.throw(_("Renseignez le mot de passe root MariaDB dans DZ Hub Settings."))
	if not (client.company_name and client.company_abbr):
		frappe.throw(_("Renseignez la société du client et son abréviation."))

	admin_password = client.get_password("admin_password", raise_exception=False) or frappe.generate_hash(
		length=16
	)
	log = run_bench(
		client.site_name,
		[
			"new-site",
			client.site_name,
			"--mariadb-root-password",
			root_password,
			"--admin-password",
			admin_password,
			"--install-app",
			"erpnext",
		],
		timeout=TIMEOUT["create_site"],
	)
	# dz_cod declares required_apps = ["erpnext", "dz_core"]: it installs dz_core first
	app = ONLINE_APP if client.online_sales else CORE_APP
	log += run_bench(client.site_name, ["install-app", app], timeout=TIMEOUT["create_site"])
	log += run_bench(client.site_name, prepare(client), timeout=TIMEOUT["create_site"])
	output, applied = set_features(client)
	log += output
	log += run_bench(client.site_name, ["enable-scheduler"])
	client.db_set({"admin_password": admin_password, "site_created": 1})
	return log, applied


def do_apply_features(client):
	check_site_name(client.site_name)
	log = ""
	apps = installed_apps(client.site_name)
	if CORE_APP not in apps:
		raise BenchError(
			f"{CORE_APP} n'est pas installé sur {client.site_name} : "
			f"bench --site {client.site_name} install-app {CORE_APP}, puis migrate."
		)
	if client.online_sales and ONLINE_APP not in apps:
		# The client took the Vente en ligne pack after the site was made
		log += run_bench(client.site_name, ["install-app", ONLINE_APP], timeout=TIMEOUT["create_site"])
		log += run_bench(client.site_name, prepare(client), timeout=TIMEOUT["create_site"])
	elif not client.online_sales and ONLINE_APP in apps:
		log += f"{ONLINE_APP} reste installé (ses commandes sont gardées) ; ses options sont coupées.\n"
	output, applied = set_features(client)
	return log + output, applied


def do_suspend(client):
	check_site_name(client.site_name)
	return run_bench(client.site_name, ["set-maintenance-mode", "on"]), None


def do_reactivate(client):
	check_site_name(client.site_name)
	return run_bench(client.site_name, ["set-maintenance-mode", "off"]), None


ACTIONS = {
	"create_site": (do_create_site, "Création du site"),
	"apply_features": (do_apply_features, "Fonctions appliquées"),
	"suspend": (do_suspend, "Suspension"),
	"reactivate": (do_reactivate, "Réactivation"),
}
NEW_STATUS = {"suspend": "Suspendu", "reactivate": "Actif"}


@frappe.whitelist()
def start(client, action):
	"""Button on DZ Client: queue the action and return at once."""
	frappe.only_for("System Manager")
	if action not in ACTIONS:
		frappe.throw(_("Action inconnue : {0}").format(action))
	frappe.get_doc("DZ Client", client).check_permission("write")
	frappe.enqueue(
		run_action,
		queue="long",
		timeout=TIMEOUT[action] + 60,
		enqueue_after_commit=True,
		client=client,
		action=action,
		user=frappe.session.user,
	)
	return _("{0} lancée en arrière-plan pour {1}.").format(_(ACTIONS[action][1]), client)


def run_action(client, action, user=None):
	"""Background job: run the action, record the result on the client."""
	doc = frappe.get_doc("DZ Client", client)
	function, title = ACTIONS[action]
	values = {"last_action": f"{title} - {now_datetime():%Y-%m-%d %H:%M}"}
	frappe.db.savepoint("dz_hub_action")
	try:
		log, applied = function(doc)
		values["apply_log"] = log[-8000:]
		if applied is not None:
			values.update({"applied_features": ", ".join(applied) or "-", "applied_on": now_datetime()})
		if action in NEW_STATUS:
			values["status"] = NEW_STATUS[action]
		failed = False
	except Exception as error:
		frappe.db.rollback(save_point="dz_hub_action")  # undo only this action's changes
		values["apply_log"] = str(error)[-8000:]
		values["last_action"] += " (échec)"
		failed = True
	doc.db_set(values)
	frappe.db.commit()
	if user:
		# dz_client.js shows the message and reloads the form
		frappe.publish_realtime(
			"dz_client_updated",
			{"client": client, "title": _(title), "failed": failed},
			user=user,
			after_commit=True,
		)
