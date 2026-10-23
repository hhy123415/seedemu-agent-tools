# H12: Domain Purchase and DNS Hosting

This example deploys Registry, FOSSBilling, primary/secondary DNS Hosting, and FakePayment
for domain purchases, simulated payments, and DNS configuration. The scenario defines host
bindings, ports, accounts, TLDs, and products; the service packages generate installation
and startup operations.

## Layout

```text
H12_domain_name_purchase/
├── domain_name_purchase.py
├── setup.py
└── output/
```

## Startup and Initialization

Use a Python environment that can import `seedemu` and `DomainService`, with Docker Compose
available. Run from this example directory:

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

The scenario always includes all four services. `domain_name_purchase.py` only generates
deployment files in `output`; build and start the containers manually from that directory.
Existing image layers may use the build cache. Uncached dependency installation requires
network access.

Services initialize locally when their containers start:

- FOSSBilling waits for its database and web server, performs the initial installation,
  configures the site URL, EPP/TLDs, demo client, and cron, then removes the installer.
- Registry registers hosting nameserver hosts after creating the registrar and reserved
  domains. Existing records are checked without being overwritten.
- FakePayment enables the local payment gateway after FOSSBilling initialization succeeds.

`setup.py` performs the remaining operations:

1. Check all required components and wait for Registry and FOSSBilling initialization.
2. Verify EPP authentication and client login.
3. Wait for and verify nameserver host records, read generated primary/secondary BIND API
   credentials, verify connectivity, and configure the DNS Hosting product.
4. Verify payment configuration, shared signing secrets, checkout connectivity, and the
   enabled gateway without rewriting gateway configuration.

A failed step stops subsequent operations and returns a nonzero exit status. Setup does
not build or start containers or initialize their local databases. For initialization
failures, inspect the relevant container logs:
`/var/log/fossbilling-initialize.log`, `/var/log/registry-hosts-example.com.log`, and
`/var/log/fake-payment-initialize.log`. Fix the issue, restart the affected container to
rerun initialization, and run setup again.

Existing administrators, clients, and product prices are preserved. A client password or
nameserver ownership mismatch raises an error without overwriting data. Cross-container
verification or product configuration failures can be retried with `python setup.py`.
These workflows do not pay invoices or retry customer orders automatically.

## Generation Options

The Python entry point generates configuration without building or starting Docker.
Both generation and setup accept `--output PATH`; use the same directory for both.
Generation supports `--platform amd` and `--platform arm`. Setup's `--timeout` controls
the Registry wait timeout, which defaults to 240 seconds.

## Web Endpoints

After startup and initialization, open these URLs in the Docker host's browser:

| Endpoint | URL |
| --- | --- |
| FOSSBilling client portal | <http://localhost:18080/> |
| FOSSBilling administration | <http://localhost:18080/admin> |
| Registry control panel | <http://localhost:18081/> |
| FakePayment health check | <http://localhost:18083/health> |

The demo FOSSBilling administrator is `admin@example.com` and the client is
`user@example.com`, both with password `Aa123456`. The Registry administrator is
`admin@example.com` with password `123456`. Change initial settings in the scenario entry point.

Select fakePayment on a FOSSBilling invoice to confirm a simulated payment and view its
result inside the invoice page. Refresh the invoice afterward to check payment status.
The checkout `/pay` endpoint accepts signed POST requests only; opening it in the address
bar returns 404. DNS Hosting is purchased and managed through the client portal, with no
separate management website. The [H13 example](../H13_browser_agent/README.md) provides
the browser and agent chat interface.

Configure host ports with `setPortForwarding(host_port)`; pass `None` to disable forwarding.
FOSSBilling derives its local URL from the forwarded port, preserving localhost in links
and redirects for localhost requests. Update `setBrowserUrls()` when changing payment
endpoints. See the [service documentation](../../services/DomainService/README.md).

## DNS Hosting and Resolution

The default products cover `.com` and `.net`; the scenario reserves `google.com`,
`twitter.com`, and `example.com`. Hosting nameservers are `ns1.example.com` and
`ns2.example.com`, at `10.170.0.71` and `10.170.0.72`. Their BIND APIs listen on internal
port 7650 without host port forwarding.

Customer domains require registration, nameserver configuration, DNS Hosting activation,
and records such as A/AAAA separately. The Registry publisher updates parent-zone NS/glue
records, waiting 30 seconds after each cycle. Recursive caches may retain older results.
Query authoritative and recursive DNS separately to distinguish record configuration
from delegation or cache problems:

```bash
dig @10.170.0.71 www.your-domain.com A +norecurse
dig @10.153.0.53 www.your-domain.com A
```

Run these commands in a container with access to the simulation network and substitute
the actual domain. Successful setup does not prove purchase or resolution success:
check invoices, orders, Registry registration, parent delegation, and authoritative records.

## Container Selection and Products

Setup locates containers by these Compose service names; override them with the listed options:

| Service | Compose service | Override |
| --- | --- | --- |
| Registry | `hnode_151_host_1` | `--registry-service` |
| FOSSBilling | `hnode_150_host_1` | `--fossbilling-service` |
| Primary DNS | `hnode_170_host_0` | `--primary-dns-service` |
| Secondary DNS | `hnode_170_host_1` | `--secondary-dns-service` |
| Checkout | `hnode_160_host_1` | `--payment-service` |

Update service selections when changing host bindings. Use `--dns-product-id ID` when
multiple DNS products exist. Existing prices are preserved; if no product exists, setup
creates a free simulation hosting product.

## Cleanup and Data

```bash
docker compose -f output/docker-compose.yml down --remove-orphans --volumes
```

This removes the project's containers, networks, and managed volumes, including orphaned
containers. Images, build caches, and generated files remain. For a custom output directory,
replace `output/docker-compose.yml` with the corresponding path. External volumes and host
bind-mount directories are not removed. Nonpersistent container data is lost on removal.

H12 and H13 both default to the Compose project `output` and use the same application ports;
deploy one at a time. Generation does not clean data automatically. Check which data must
be preserved before switching deployments. Scripts forward underlying command output and
necessary error messages.
