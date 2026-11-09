# SocialMediaService

The current backend is Mastodon; this package does not yet select other platforms.

Install Mastodon inside an existing SeedEmu host using the normal Service/Server
and Binding APIs. The host runs a local PostgreSQL database and Redis, and serves
Rails and streaming requests through Nginx with ACME-issued or self-signed TLS certificates.

```python
from SocialMediaService import SocialMediaService

mastodon = SocialMediaService()
server = mastodon.install('mastodon')
server.setDomain('mastodon.com')
server.setPort(18443).setPortForwarding(18443)
server.addAccount('admin', 'Admin123456', email='admin@mastodon.com', admin=True)
server.addAccount('alice', 'Alice123456', email='alice@mastodon.com')
server.addAccount('bob', 'Bob123456', email='bob@mastodon.com')
emu.addLayer(mastodon)
emu.addBinding(Binding('mastodon', filter=Filter(asn=151, nodeName='mastodon')))
```

The scenario owns physical nodes, DNS records, CA setup and trust distribution.
Set `server.setAcmeUrl('https://ca.mastodon.com/acme/acme/directory')` to use
an ACME CA. The node must trust that CA before service startup, and the CA must
resolve and reach the instance on port 80 for HTTP-01 validation. Certbot uses
webroot authentication, retains its state in `/etc/letsencrypt`, checks renewal
hourly and reloads Nginx after renewal. The certificate covers the configured domain.

Without an ACME URL, the service retains its self-signed fallback for the domain
and `localhost` under `/var/lib/mastodon/tls`. Such certificates expire after
365 days and are not automatically renewed. Switching to ACME preserves existing
Mastodon identity and application data.

The service owns dependency installation, database initialization, initial users,
application processes, Nginx, certificate generation and persistent data.
Application keys are generated at runtime. Explicit account passwords are included in generated build files; use the example passwords only for local experiments.
The default HTTPS port is 443 and host forwarding is disabled. When forwarding,
use the same canonical port inside and outside the simulation.

See [H14](../../examples/H14_socialmedia/README.md) for the complete DNS/CA-issued HTTPS example,
startup commands, browser access and validation boundaries.

`addAccount(username, password, *, email, admin=False)` declares a confirmed initial user with an explicit
password and login email. The username determines the public handle
`@username@domain`; the email is used to log in and may use a different domain. `admin=True` grants the Owner role.
At startup, declared emails and passwords are synchronized for existing users as well. Existing roles are preserved.
The service has no implicit initial accounts; the scenario declares them.
Public registration is enabled at startup. Web signups still require email confirmation;
the default file-based mail delivery does not send messages to external inboxes.

Experiments register the socialmedia tool package directly with AgentService's `addToolPackage()`.
See [agent tools](../AgentService/tools/socialmedia/README.md) for the nine operations, per-agent connection
configuration and credential requirements. E15 uses Mastodon with CAService and AgentService socialmedia tools.
# Optional API token export

After `addAccount()`, call `server.exportToken('alice',
scopes=['read:accounts', 'read:statuses', 'write:statuses'],
path='/var/lib/mastodon/agent-alice.json')` to opt that account into API access.
Startup creates/reuses a token after account initialization and writes a private
JSON file containing `instance_url` and `access_token`. The URL follows the
service's configured domain and canonical HTTPS port. Export paths must be
distinct JSON files directly in `/var/lib/mastodon`, excluding `accounts.json`.
No tokens are exported by default. The scenario is responsible for copying the
file into the intended consumer's credential volume with appropriate ownership.
Changing scopes creates a separate application/token; existing tokens are not
automatically revoked. Treat scope reduction as requiring explicit revocation.
