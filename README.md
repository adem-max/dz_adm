# DZ Hub

The vendor's own site to manage every Daftar client: who they are, which
site is theirs, what they pay for (packs and options), their monthly
invoices, and suspension when they don't pay.

(Called "DZ COD Hub", app `dz_cod_hub`, until 19 October 2026, when it only
knew online sellers. Repo: adem-max/dz_adm, public like the other two.)

Brand (22 October 2026): the company is **Sijil**, the ERP it sells is
**Daftar** ("Daftar by Sijil"); see dafter-core DECISIONS.md. Nothing renamed yet.

**Vendor only.** Install it only on your hub site, never on a client site.

## How it fits

```
dz_core  (dafter-core)  every client: Pack Atelier          <- the hub talks to this
dz_cod   (dafter-cod)   online sellers: Pack Vente en ligne  <- added on top when sold
dz_hub   (this repo)    your site: clients, offers, billing, actions on client sites
```

The hub never runs inside a client site: it runs `bench` commands against
each client site on the same server. It does not install dz_core or dz_cod
on the hub site either; it only needs their code on the bench, to read what
can be sold (`dz_core.features.bench_catalog`) and to set sites up.

## What it does

- **DZ Feature**: what you sell, created on install and migrate.
  - two **packs**: *Pack Atelier* (dz_core, every client, always billed) and
    *Vente en ligne* (dz_cod, online sellers);
  - one **option** per optional feature the apps declare (their
    `dz_features` hook; today dz_cod's four: courier API, phone checks, n8n
    webhooks, labels and reports). A new feature in an app becomes a new
    option on the next migrate.
- **DZ Client** (one per client): the ERPNext Customer to bill, the site
  name, *Vente en ligne* ticked or not, the options, sector and tax regime
  (passed to dz_core's setup), state (Actif / Suspendu / Résilié). An option
  from dz_cod needs *Vente en ligne*.
- **Billing with ERPNext**: each pack and option is a service Item with a
  monthly Subscription Plan (*Abonnements DZ*, price 0 until you set it).
  Saving a client creates or updates its Subscription: one Sales Invoice a
  month from the start date, one line per plan, due after *Délai de paiement*
  (DZ Hub Settings).
- **Report "Clients en retard"**: clients with an overdue invoice (minus the
  tolerance days in DZ Hub Settings).
- **Buttons on a client** (background jobs, result in *Journal de la dernière action*):
  - *Créer le site*: new site with ERPNext, then dz_core (or dz_cod, which
    installs dz_core first), then `dz_core.setup.new_client.prepare` with the
    client's sector and tax regime (or dz_cod's, which runs dz_core's and
    adds orders, warehouses, the first courier), then the options with
    `dz-features`. Local bench only: DNS, nginx and SSL stay manual
    (dafter-core docs/DEPLOY.md §7). The new site is marked with the
    client's name (`dz_hub_client` in its site_config): if a step after
    `new-site` fails, fix the cause and click again, it carries on. The site's
    Administrator password is kept on the client, encrypted.
  - *Appliquer au site*: `bench --site <site> dz-features --set …`. When the
    client took *Vente en ligne* after their site was made, it first installs
    dz_cod and runs its setup. Untaking it never uninstalls dz_cod (that
    would delete their orders): its options are switched off. An orange
    banner shows when the site does not have the options the client pays for.
  - *Suspendre* / *Réactiver*: maintenance mode on / off. A running site picks
    the change up within about a minute.
  - *Mettre à jour l'abonnement*: rebuild the Subscription from the offer.

## Install (on the server that runs the client sites)

```bash
cd ~/frappe-bench
bench get-app https://github.com/adem-max/dafter-core     # must be on the bench
bench get-app https://github.com/adem-max/dafter-cod      # for online sellers
bench get-app https://github.com/adem-max/dz_adm          # this repo
bench new-site hub.yourdomain --install-app erpnext
# setup wizard: your company, Algeria, DZD
bench --site hub.yourdomain install-app dz_hub
```

Create sites with bench running (`bench start` or supervisor): Frappe v16 needs
its Redis during `new-site`, and a site made without it is incomplete.

Then in the hub: **DZ Hub Settings** → company that bills, payment delay,
tolerance, MariaDB root password (only for *Créer le site*); **Subscription
Plan** → set each monthly price.

Requirements: background workers running as the bench user (they run `bench`
for the client sites); dz_core (and dz_cod) on the same bench. The hub acts
on sites of its own server only. Keep free disk space: each client site is a
full ERPNext database.

### Moving from dz_cod_hub

A hub site that ran the old app keeps its clients, subscriptions and prices:
the doctypes are taken over by dz_hub, and two patches rename the billing
records (*Abonnements DZ COD* → *Abonnements DZ*, `DZCOD-…` → `DZ-…`,
`COD - …` → `DZ - …`, *Base COD* → *Pack Atelier*) and tick *Vente en ligne*
on the existing clients (the old hub only made dz_cod sites). On the dev
bench (19 October 2026), after a backup:

```bash
bench --site hub.localhost remove-from-installed-apps dz_cod_hub
# swap the app folder, pip install -e apps/dz_hub, dz_hub in sites/apps.txt
bench --site hub.localhost execute frappe.db.sql --args "[\"update tabDocType set module='DZ Hub' where module='DZ COD Hub'\"]"
bench --site hub.localhost execute frappe.db.sql --args "[\"update tabReport set module='DZ Hub' where module='DZ COD Hub'\"]"
bench --site hub.localhost execute frappe.installer.add_to_installed_apps --args "['dz_hub']"
bench --site hub.localhost migrate          # new fields, the two patches, the packs
```

(The `Module Def` "DZ COD Hub" is deleted and "DZ Hub" given `app_name = dz_hub`
the same way if `install-app` was tried first.)

## Daily use

1. New client: Customer → DZ Client (site, *Vente en ligne* or not, options,
   company + abbreviation, sector, tax regime, first courier for online
   sellers) → *Créer le site* (or, for a site made by hand, *Appliquer au site*).
2. Change of offer: edit the client → save (the Subscription follows) →
   *Appliquer au site*.
3. Each month ERPNext makes the invoices (daily job). Record payments as usual.
4. *Clients en retard* → open the client → *Suspendre*; after payment → *Réactiver*.

## Tests

On a separate hub test site, never your real hub (tests write and roll back data):

```bash
bench --site hub-test.localhost set-config allow_tests 1
bench --site hub-test.localhost run-tests --app dz_hub     # 22 tests
```

The `bench` calls are mocked in the tests: no site is created or changed.

A fresh test site gets a company and the offer before the tests
(`dz_hub/tests/utils.py`, hook `before_tests`). Every push runs pre-commit and
the tests on a fresh site on GitHub (`.github/workflows/ci.yml`), with
dafter-core and dafter-cod taken at the branch of the same name when there is
one, else main.
