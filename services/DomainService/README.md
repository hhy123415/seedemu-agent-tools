# DomainService

DomainService provides composable domain registration, customer purchases, DNS hosting,
and simulated payments for the emulation network.

| Service | Purpose |
| --- | --- |
| `RegistryService` | Registry, TLDs, EPP registrar access, and parent-zone delegation publication |
| `FossBillingService` | Client portal, domain products, orders, and invoices |
| `DnsHostingService` | Primary/secondary authoritative DNS, dynamic update authorization, hosting APIs, and DNS products |
| `FakePaymentService` | Simulated checkout and FOSSBilling payment gateway |

[H12](../../examples/H12_domain_name_purchase/README.md) provides the complete purchase
environment. [H13](../../examples/H13_browser_agent/README.md) adds a browser and agent in
one container. H12 uses `domain_name_purchase.py`; H13 uses `browser_agent.py`. These generate
deployment files. Build and start manually from `output`, then run `setup.py` for
cross-container configuration and verification. See each example for cleanup instructions.

## DNS Extension

DNS hosting and update authorization are implemented together in
`DnsHostingService/DnsHostingService.py`. `DnsHostingService` inherits SeedEmu's native
`DomainNameService`. Its zone lookup override matches the parent except for changing
`zone.getName() == domain` to `zone == domain`; the parent is unchanged.

After building B02, H12 uses the native `Emulator.merge()` with `DnsHostingServiceMerger`
to preserve existing zones, nodes, and bindings in the subclass. H13 reuses H12. Merge before
creating authorizations. The subclass retains the layer name `DomainNameService`, so Registry
render dependencies and `emu.getLayer('DomainNameService')` remain valid.

```python
from seedemu.core import Emulator
from DomainService import DnsHostingService, DnsHostingServiceMerger

dns_extension = Emulator()
dns_extension.addLayer(DnsHostingService())
emu = emu.merge(dns_extension, [DnsHostingServiceMerger()])
```

`authorizeZoneUpdates()` validates zones and DNS virtual nodes and returns an independent
`DnsUpdateAuthorization`. During rendering, native `getMasterIp()` identifies the configured
primary and TSIG credentials are populated. Publishers read them through `getZones()` and
`getCredentials(zone)`. Reading credentials before DNS rendering raises an error; publishers
must declare a render dependency on the DNS layer.

Update authorization neither stores publisher objects nor calls Registry interfaces. Add
hosting configuration with the same service's `addHosting()`; no additional service layer or
`dns-hosting` virtual node is created. A native Hook appends hosting extension installation
and Registry host initialization after FOSSBilling rendering, preserving installation order
without a circular dependency.

Python source changes do not update existing images or containers. Follow the selected
[H12](../../examples/H12_domain_name_purchase/README.md) or
[H13](../../examples/H13_browser_agent/README.md) workflow to regenerate output, build,
start, and run setup. Each render generates new TSIG keys: deploy Registry and the relevant
TLD DNS containers from the same generation, rather than rebuilding only one side.
Interface checks establish code availability; live publication still requires verification
of parent delegation and primary/secondary synchronization after deployment.

## Usage

Use a Python environment that can import `DomainService` and `seedemu`. On an existing
emulator `emu`, configure the service:

```python
from DomainService import RegistryService
from seedemu.core import Binding, Filter

registry = RegistryService()
server = registry.install('registry')
server.setTlds(['com', 'net'])
server.setAdminAccount('admin@example.com', '123456')
server.setDatabasePassword('registry-demo-password')
server.setPortForwarding(18081)
emu.addLayer(registry)
emu.addBinding(Binding('registry', filter=Filter(asn=151, nodeName='host_1')))
# Finally call emu.render() and emu.compile(...).
```

The target host must exist and must not run conflicting applications. Rendering writes
installation, configuration, and startup operations. `setEppPort(port)` sets the EPP port,
defaulting to 700. The web panel listens on 8080; configure its host port with
`setPortForwarding(host_port)`. Use the inherited `setDisplayName()` to change display names.

Registry uses a pinned upstream commit, PHP 8.5, `.com`/`.net` initialization, local MariaDB
and Redis, the control panel, EPP TLS, DAS, and lifecycle jobs every five minutes. Defaults
are in `RegistryService/registry_defaults.py`; each Server can override credentials.
`setAdminAccount(email, password)` and `setDatabasePassword(password)` configure initial
installation, not password rotation on a running database.

`setTlds()` defines the initial TLD list; `getTlds()` returns a copy. Names such as `com` and
`.com` are normalized to lowercase and deduplicated. Only single-label ASCII names are
accepted; use Punycode for internationalized names. The upstream database limits labels to
31 characters, and the list must not be empty. Each TLD receives the pinned upstream defaults
for registration, renewal, transfer, and restore prices. Unselected upstream example TLDs
are excluded. Existing databases are not migrated.

## Port Forwarding and Web Access

Registry and FOSSBilling listen on container port `8080`; FakePayment's internal port is
configured with `setPort()`. Set host ports using `setPortForwarding(host_port)`, or pass
`None` to disable forwarding. Default host ports are Registry `18081`, FOSSBilling `18080`,
and FakePayment `18083`. Registry and FOSSBilling can share an internal port because they
run in different containers, but their host ports must differ on the same Docker host.

H12 configures these mappings in its entry point:

```python
# Registry: forward host port 18081 to port 8080 in the Registry container.
registry_server.setPortForwarding(18081)

# FOSSBilling: forward host port 18080 to port 8080 in the FOSSBilling container.
registrar.setPortForwarding(18080)
```

Mappings are added to each instance's actual bound host during installation. After generating,
building, starting, and completing `python setup.py`, use the Docker host's browser:

| Endpoint | URL | Purpose |
| --- | --- | --- |
| Registry control panel | <http://localhost:18081/> | Manage the registry, TLDs, and registrars |
| FOSSBilling client portal | <http://localhost:18080/> | Client login, purchases, orders, and invoices |
| FOSSBilling administration | <http://localhost:18080/admin> | Manage clients, TLD products, prices, and registrar settings |

FOSSBilling client and admin portals share port `18080` and differ by URL path; no extra
admin port is required. A Registry-only deployment provides only its control panel.
Initial demo accounts are listed below. Scenario overrides take precedence, and changing
defaults does not automatically update existing accounts.

| Account | Email | Demo password |
| --- | --- | --- |
| Registry administrator | `admin@example.com` | `123456` |
| FOSSBilling client | `user@example.com` | `Aa123456` |
| FOSSBilling administrator | `admin@example.com` | `Aa123456` |

FOSSBilling's `setPortForwarding(port)` configures both forwarding and the corresponding
local site URL. Requests through `localhost:port` or `127.0.0.1:port` retain that origin in
links and redirects; internal access and CLI use the bound host's internal address.
Passing `None` disables forwarding and the local URL override. Startup applies the URL
configuration after regeneration, build, and container startup.

Registry's EPP port `700` serves registrar protocol traffic, not a website. Generated Docker
configuration does not mean the websites are running; wait for initialization and setup.

## DNS Authorization

Registry can run independently without DNS publication. When `DomainNameService` exists,
it renders first. Configure authorization before rendering:

```python
dns = emu.getLayer('DomainNameService')
authorization = dns.authorizeZoneUpdates(
    ['com', 'net'],
)
server.setDnsAuthorization(authorization)
```

`zones` contains zone names only, either TLDs or subdomains, optionally with trailing dots.
DNS discovers hosting nodes through `getZoneServerNames()`. A single node is the primary;
with multiple nodes, rendering uses `getMasterIp()` to identify exactly one primary and
uses the remaining nodes as secondaries. This normally follows `setMaster()` and the default
NS/SOA configuration. Virtual node names need not be repeated.

Each node must already host the relevant zone, and all zones on selected nodes must be
included in the authorization. Registry's `setDnsAuthorization(authorization)` validates that
authorized zones belong to its managed TLDs; a subset is allowed. Installation validates
again in case TLD settings changed. This method does not create DNS nodes, zones, or root
delegations; the scenario must configure those when adding a TLD.

DNS owns update authorization and primary/secondary configuration, populating targets and
keys in the authorization object. Registry reads credentials during installation and writes
them to its bound host, without repeating AS or host names. Authorization allows only
NS/A/AAAA delegation updates below the zone, protecting its apex and nameserver records;
it does not grant arbitrary record-type writes.

Each TLD has separate publication and zone-transfer TSIG keys. Transfers are disabled for
a primary without secondaries; otherwise transfers and notifications are signed. Every
render creates new credentials, so update Registry and the relevant DNS nodes together.
Publisher settings are written to `/opt/registry/dns-publication-<tld>.json`; the combined
manifest is `/opt/registry/dns-publications.json`, keyed by zone names such as `com.`.

Authorization alone does not start the publisher. Call
`enableDnsPublication(['com', 'net'])` on Registry to enable periodic publication for the
authorized TLDs, with a default interval of 30 seconds.

## File Organization

Registry uses a separate template directory and a file-content dictionary:

```text
DomainService/
└── RegistryService/
    ├── RegistryService.py       # Interfaces and instance settings
    ├── registry_defaults.py     # Default simulation settings
    ├── registry_install.py      # Dependencies, templates, and startup order
    └── template/
        ├── RegistryFileTemplates.py
        └── files_registry/     # SQL, PHP, shell, and Nginx templates
```

Templates define file structure; Server instances supply account settings. PHP and SQL
strings are escaped separately, and web database passwords are written as quoted dotenv
values. `DomainService` exports classes such as `RegistryService` and `RegistryServer`;
DNS authorization is provided by the emuvista subclass's
`DnsHostingService.authorizeZoneUpdates()`.

Registry templates include `database.sql`, `database.sh`, `initialize-tlds.php`,
`configure-web.php`, `configure-component.php`, `registry.conf`, `web.sh`, and
`create-epp-registrar.php` for registrar accounts and reserved domains. Short startup commands,
admin creation scripts, INI, cron, and EPP/DAS fragments are written directly in
`registry_install.py`, preserving generated files and startup ordering.

## FOSSBilling Registrar Service

Like Registry, this service separates `FossBillingService.py`, defaults, installation
functions, and `template/files_fossbilling/`. It pins FOSSBilling 0.8.7 and the EPP installer.

```python
from DomainService import FossBillingService

registrar_service = FossBillingService()
registrar = registrar_service.install('fossbilling')
registrar.setRegistry('registry')
registrar.setTlds(['com', 'net'])
registrar.setTldPrice('com', registration='11.99', renewal='11.99', transfer='11.99')
registrar.setAdminAccount('admin@example.com', 'Aa123456')
registrar.setClientAccount('user@example.com', 'Aa123456')
registrar.setReservedDomains(['google.com', 'twitter.com', 'example.com'])
emu.addLayer(registrar_service)
emu.addBinding(Binding('fossbilling', filter=Filter(asn=150, nodeName='host_1')))
registrar.setPortForwarding(18080)
```

`setRegistry()` accepts a Registry virtual node and optional `username`, `password`, and
`prefix`. Rendering derives addresses from bindings and the EPP port from Registry to
configure the connection and source-IP allowlist. Registry and FOSSBilling require distinct
hosts; multiple registrars need distinct accounts and prefixes. Omitting `setTlds()` inherits
Registry's TLDs; an explicit list must be a subset. Initial prices default to 11.99; existing
prices and products are preserved. `setClientAccount(..., profile={...})` overrides default
contact data; see `fossbilling_defaults.py` for fields.

After database initialization and before EPP starts, Registry creates registrar accounts,
allowlists, and reserved domains. FOSSBilling connects to that Registry EPP process; no
second EPP service is needed. Existing account password/prefix mismatches and reserved domains
owned by another registrar are rejected. This is not a runtime password-rotation interface.
Changed bound IPs require regeneration and deployment. EPP uses simulation self-signed
certificates and the corresponding adapter verification settings.

The generated `initialize-fossbilling.py` runs at container startup. It waits for the local
database and web server, reads `setup-config.json` and `epp-connection.json`, then handles
initial installation, URLs, TLD bindings, client creation, installer removal, and cron.
Success creates `/run/fossbilling-initialized`; failure creates
`/run/fossbilling-initialization.failed`. Logs are in `/var/log/fossbilling-initialize.log`.
`setup_fossbilling.py` only waits for initialization and verifies EPP and client login.
Existing administrators and prices are preserved. An existing demo client's password must
match; only missing contact data is filled. Checkout activates orders after committing the
transaction.

Generated initialization settings contain simulation credentials and are restricted to
root. Build directories and emulator snapshots also contain these settings. See
[H12](../../examples/H12_domain_name_purchase/README.md) for runtime commands.

## Rebuild and Initialize

From `examples/H12_domain_name_purchase`, use the virtual environment with SeedEmu dependencies:

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

The entry point always includes Registry, FOSSBilling, DNS Hosting, and FakePayment and only
generates deployment files. Build and start manually inside `output`. Services initialize
locally at startup; setup waits and performs cross-container configuration and verification.
Retry setup after cross-container failures. For local initialization failures, inspect logs,
fix the issue, and restart the affected container first. The Python entry point does not
invoke Docker build or startup. See the [startup guide](../../examples/H12_domain_name_purchase/README.md).

## DNS Hosting and Registry Delegation Publication

`DnsHostingService` integrates pinned BIND API and FOSSBilling DNS Hosting releases. The
entry point is [`domain_name_purchase.py`](../../examples/H12_domain_name_purchase/domain_name_purchase.py).
Run the generation, build, startup, and setup sequence above from the H12 directory.

The scenario retains the `.com`/`.net` Registry and FOSSBilling services and uses two existing
AS170 hosts: `host_0` for primary DNS and `host_1` for secondary DNS. The hosting API shares
the primary host. Web endpoints retain ports 18080/18081. DNS Hosting is purchased and managed
inside the FOSSBilling client portal, without a separate port-18082 website. BIND APIs listen
on each node's internal IPv4 address at port 7650, with no host port forwarding.

### Scenario Configuration

Install the primary and secondary in order on the merged `DnsHostingService`, binding them
to distinct existing hosts:

```python
dns = emu.getLayer('DomainNameService')

# Install the primary first so ns1/ns2 match primary/secondary addresses.
dns.install('hosted-dns-primary').addZone('example.com.').setMaster()
dns.install('hosted-dns-secondary').addZone('example.com.')
emu.addBinding(Binding('hosted-dns-primary', filter=Filter(asn=170, nodeName='host_0')))
emu.addBinding(Binding('hosted-dns-secondary', filter=Filter(asn=170, nodeName='host_1')))

hosting = dns.addHosting('hosted-dns-primary', 'hosted-dns-secondary', domain='example.com')
hosting.setRegistrar('fossbilling')
```

Each pair hosts only the selected static service domain, without other custom includes.
Customer zones created through BIND API are managed separately. Primary/secondary addresses,
registrar source IP, and product nameservers come from actual bindings, not fixed
`10.170.0.71/72` addresses. Each FOSSBilling instance supports one hosting pair; instances
cannot share DNS nodes. `domain` accepts a second-level ASCII domain, which must first be
reserved using FOSSBilling's `setReservedDomains()`. The example reserves `google.com`,
`twitter.com`, and `example.com` in the registrar configuration.

On the Registry instance:

```python
registry_server.enableDnsPublication(['com', 'net'], interval=30)
```

Only managed and authorized TLDs can be published. The publisher reads the existing EPP
database configuration and each `dns-publication-<tld>.json`, then sends signed NS/glue updates
to the corresponding parent zone. Each TLD uses a separate state file and process lock.
Failed updates do not save successful state and are retried in later cycles. Domains without
nameservers, under clientHold/serverHold, or outside their validity period are not published.
The publisher handles only nameservers and in-domain glue, not customer website A/AAAA records.

### Initialization and Data Boundaries

Setup performs these steps in order:

1. Wait for Registry and FOSSBilling initialization and verify EPP and client login.
2. Wait for Registry nameserver registration and read-only verification of the host records,
   IPv4 addresses, and status of `ns1.example.com` and `ns2.example.com`.
3. Read API credentials generated at DNS container startup, check ports, and verify
   authentication through the extension client.
4. Activate the DNS extension and configure the Bind product and category.

Existing Registry hosts are checked for ownership, parent domain, addresses, and status;
conflicts roll back rather than overwrite data. Registering host objects does not set domain
NS delegation or alter website records in the static zone. Existing product prices remain;
if no product exists, setup creates a free simulation product. Select among multiple products
with `python setup.py --dns-product-id ID`. Credentials are not printed or passed on command
lines. Initialization does not activate or retry existing customer orders or retry payments.

A domain purchase still requires separate nameserver configuration, DNS Hosting activation,
and website record configuration. Verify Registry domain/nameserver state, parent delegation,
primary/secondary authoritative zones, and recursive resolution separately. Static service
domains, configured products, or successful API authentication do not prove customer-domain
resolution.

## FakePayment

`FakePaymentService` adds an independent checkout and FOSSBilling payment adapter for simulation
only, without real funds. Its scenario entry point is
`examples/H12_domain_name_purchase/domain_name_purchase.py`.

Selecting fakePayment displays confirmation and results in an embedded area of the invoice
page. The browser stays on FOSSBilling. On confirmation, checkout verifies the signature and
calls back to FOSSBilling. Refresh the invoice to check payment status; verify order activation
and domain registration separately.

Use the H12 generation, build, startup, and setup sequence above. Setup checks Registry and
FOSSBilling readiness/login, configures DNS Hosting products, and verifies FakePayment.
The default checkout Compose service is `hnode_160_host_1`; override it with `--payment-service`.
To verify only the gateway, run `FakePaymentService/setup_fake_payment.py` with
`--container <FOSSBilling-container>` and `--payment-container <checkout-container>`.
It compares configuration and signing secrets, then probes checkout from the registrar,
without creating invoices or automatically paying orders.

| Service | Host URL | Usage |
| --- | --- | --- |
| FOSSBilling client portal | `http://localhost:18080/` | Log in, purchase services, and open invoices |
| FOSSBilling administration | `http://localhost:18080/admin` | Manage products, invoices, and gateways |
| Registry control panel | `http://localhost:18081/` | Manage registry data |
| FakePayment health check | `http://localhost:18083/health` | Returns `ok` when ready |
| FakePayment checkout | `http://localhost:18083/pay` | Signed POST endpoint for the embedded invoice form |

`/pay` accepts POST only; opening it in the address bar returns 404. DNS Hosting is managed
inside the client portal. A submitted payment or successful setup does not establish that
the invoice is paid, the order is active, the domain is registered, or DNS is published.
Check each outcome separately.

### Custom Bindings and Ports

```python
from DomainService import FakePaymentService

fake_payment_service = FakePaymentService()
checkout = fake_payment_service.install('fake-payment')
checkout.setRegistrar('fossbilling').setPort(8080)
checkout.setBrowserUrls({'localhost:18080': 'http://localhost:18083/pay',
                         '127.0.0.1:18080': 'http://127.0.0.1:18083/pay'})
emu.addLayer(fake_payment_service)
emu.addBinding(Binding('fake-payment', filter=Filter(asn=160, nodeName='host_1')))
checkout.setPortForwarding(18083)
```

Internal payment and callback URLs come from bound nodes rather than fixed topology IPs.
Each registrar supports one FakePayment instance; checkout and registrar require separate
hosts. `setup-gateway.sh` enables the gateway after local FOSSBilling initialization, logging
to `/var/log/fake-payment-initialize.log`. Host-side setup only verifies the gateway and does
not rewrite its database records.

`setPort()` sets the container port; `setPortForwarding()` sets the host mapping;
`setBrowserUrls()` maps the FOSSBilling browser Host to a browser-accessible checkout URL.
Update both forwarding and browser URLs when changing host ports. Unmatched Hosts use the
simulation payment URL; `setBrowserUrls({})` uses internal addresses only.

`setSharedSecret()` replaces the demo signing secret and writes the same value to both
containers. Do not commit secrets. The default is for simulation only. Address, port, or
secret changes require regeneration and rebuilding.

Setup first checks all required components. If deployed containers lack DNS Hosting or payment
components, rebuild the complete scenario before running setup. Setup cannot install missing
image components.

To clean the current example's containers, networks, and data volumes, run from H12:

```bash
docker compose -f output/docker-compose.yml down --remove-orphans --volumes
```

This removes the same Compose project's containers, including orphans, networks, writable
container layers, and managed volumes. Images, generated files, external volumes, and host
bind-mount directories remain. Adjust the Compose path for custom output. Cleanup does not
build or initialize services automatically.

## H13: Browser and Agent in One Container

[H13](../../examples/H13_browser_agent/README.md) combines the complete domain services with
browser-agent. It joins AS154/net0 through `Docker.attachCustomContainer()` without consuming
an existing host. The agent UI is at `http://localhost:18089/`; the agent and Chromium are
installed in that container image.

List egress destinations in H13's `egress_urls.txt`, one URL, domain, or IP per line. Startup
configures DNS and routes automatically. After initial generation, build, and startup, address
changes require only restarting browser-agent, not editing network scripts or rebuilding.
From H13, run `python browser_agent.py`, build and start inside `output`, then return to H13
and run `python setup.py`. Cleanup uses
`docker compose -f output/docker-compose.yml down --remove-orphans --volumes`; adjust the
path for custom output. H12 and H13 share the default project name and application ports,
so run them as alternatives.

## Build Caches and Installation Failures

Dependency installation uses Docker BuildKit caches. Registry, FOSSBilling, and DNS Hosting
install base packages, the PHP repository, system services, PHP extensions, source downloads,
and Composer dependencies in separate layers. Each apt layer refreshes indexes before
installing its packages, avoiding stale indexes for newly requested packages.

apt downloads use the shared `/var/cache/apt` cache; Composer uses `/var/cache/composer`.
Locks prevent concurrent cache modifications, so parallel builds may wait. apt uses its
native retries and connection timeouts. Repository setup and Composer run directly and
return a nonzero status on failure, preserving the tools' original output.

H13 also caches pip downloads and separates system dependencies, desktop components, Python
packages, Chromium system dependencies, and browser installation. Agent source and model
profiles are copied afterward; source changes do not themselves reinstall dependencies.

New Dockerfile instructions rebuild affected layers. Successful layers are reused when
instructions and base images are unchanged. Download caches can survive failed installation
steps but do not fix persistent proxy or repository failures. Compose cleanup does not remove
images or BuildKit caches; deleting build caches requires downloading dependencies again.
The compiler generates base software layers, whose cache behavior remains managed by Docker.
