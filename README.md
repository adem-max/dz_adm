# DZ COD Hub

The vendor's own site to manage [dz-cod](https://github.com/adem-max/dz-cod)
clients: who they are, which site is theirs, which optional features they pay
for, their monthly invoices, and suspension when they don't pay.

**Private.** Install it only on your hub site, never on a client site.

## What it does

- **DZ Client** (one per client): the ERPNext Customer to bill, the site name,
  the chosen optional features (base is always included), the state
  (Actif / Suspendu / Résilié).
- **Billing with ERPNext**: each feature (and the base) is a service Item with a
  monthly Subscription Plan (*Abonnements DZ COD*, price 0 until you set it).
  Saving a client creates or updates its Subscription: one Sales Invoice a
  month from the start date, one line per plan, due after *Délai de paiement*
  (DZ Hub Settings).
- **Report "Clients en retard"**: clients with an overdue invoice (minus the
  tolerance days in DZ Hub Settings).
- **Buttons on a client** (background jobs, result in *Journal de la dernière action*):
  - *Créer le site*: new site with ERPNext and dz_cod, company, warehouses,
    first courier and features (`dz_cod.setup.new_client.prepare`). Local
    bench only: DNS, nginx and SSL stay manual (dz-cod docs/DEPLOY.md §7).
  - *Appliquer au site*: `bench --site <site> dz-cod-features --set …`.
    An orange banner shows when the site does not have what the client pays for.
  - *Suspendre* / *Réactiver*: maintenance mode on / off. A running site picks
    the change up within about a minute.
  - *Mettre à jour l'abonnement*: rebuild the Subscription from the features.

## Install (on the server that runs the client sites)

```bash
cd ~/frappe-bench
bench get-app <this repo>                    # dz_cod must already be on the bench
bench new-site hub.yourdomain --install-app erpnext
# setup wizard: your company, Algeria, DZD
bench --site hub.yourdomain install-app dz_cod_hub
```

Create sites with bench running (`bench start` or supervisor): Frappe v16 needs
its Redis during `new-site`, and a site made without it is incomplete.

Then in the hub: **DZ Hub Settings** → company that bills, payment delay,
tolerance, MariaDB root password (only for *Créer le site*); **Subscription
Plan** → set each monthly price.

Requirements: background workers running as the bench user (they run `bench`
for the client sites); dz_cod on the same bench (the hub reads
`dz_cod/features.py`). The hub acts on sites of its own server only. Keep free
disk space: each client site is a full ERPNext database.

## Daily use

1. New client: Customer → DZ Client (site, features, company + abbreviation,
   first courier) → *Créer le site* (or, for a site made by hand, *Appliquer au site*).
2. Change of offer: edit the features → save (the Subscription follows) →
   *Appliquer au site*.
3. Each month ERPNext makes the invoices (daily job). Record payments as usual.
4. *Clients en retard* → open the client → *Suspendre*; after payment → *Réactiver*.

## Tests

On a separate hub test site, never your real hub (tests write and roll back data):

```bash
bench --site hub-test.localhost set-config allow_tests 1
bench --site hub-test.localhost run-tests --app dz_cod_hub
```

The `bench` calls are mocked in the tests: no site is created or changed.
