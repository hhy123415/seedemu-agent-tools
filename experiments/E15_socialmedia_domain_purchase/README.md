# E15: Mastodon and domain purchase

E15 uses the shared H00 topology with Mastodon, CAService, Registry,
FOSSBilling, DNS hosting and FakePayment. Alice and Bob use AgentService with
E99's LangChain adapter. No Tinode, EmailBundle or separate tool-service is deployed.

## Generate and start

Before replacing an existing deployment, stop it using its old generated Compose
file. Keep volumes; do not add `-v`:

```bash
docker compose -f output/docker-compose.yml down
```

Keep `.env` with `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` configured.
Run from this directory:

```bash
../../.venv/bin/python experiment.py
cd output
docker compose --progress plain build
docker compose up -d --remove-orphans
```

`--output`, `--env-file` and `--platform amd|arm` select generation settings.
There is no Tinode archive argument. Old Tinode packages and database volumes
are not deleted by generation. CA state is retained in `.runtime/ca.com`.
Creating a new CA requires Docker; an existing saved CA is restored.
Do not delete the CA state when reusing the deployment.

## Services and credentials

| Component | Internal address | Host access |
| --- | --- | --- |
| Mastodon | `mastodon.com:18443` / `10.161.0.9` | `https://mastodon.com:18443/` |
| CA | `ca.com:443` / `10.161.0.4` | Internal ACME CA |
| FOSSBilling | `10.150.0.71:8080` | `http://localhost:18080/` |
| Registry | `10.151.0.71:8080` | `http://localhost:18081/` |
| FakePayment | `10.160.0.71:8080` | `http://localhost:18083/` |
| Alice / Bob agents | `10.161.0.80` / `10.161.0.81` | Monitor below |
| Recursive DNS | `10.150.0.54` | Internal |

For browser access, map `mastodon.com` to `127.0.0.1` in the host's hosts file,
and trust `.runtime/ca.com/.step/certs/root_ca.crt` in the browser/host trust store.
CAService installs trust on AS161 nodes for agent HTTPS requests.
Mastodon obtains its certificate from `https://ca.com/acme/acme/directory`.
No separate DNSSEC extension is required.

Mastodon demo logins are `alice@mastodon.com` / `alice123456`,
`bob@mastodon.com` / `bob123456`, and `admin@mastodon.com` / `admin123456`.
These are separate from FOSSBilling accounts in `domains.example.yaml`.

## Agents and tools

Socialmedia tools live in
[AgentService/tools/socialmedia](../../services/AgentService/tools/socialmedia/).
The old AgentService chat tool package has been removed.
Each agent is allowed:

- `network.identity`, `network.resolve`, `world.catalog`, `world.probe`
- `socialmedia.timeline_read`, `socialmedia.account_lookup`, `socialmedia.account_statuses`,
  `socialmedia.status_context`, `socialmedia.status_create`
- `dns.lookup`, `domain_purchase.purchase`, `domain_purchase.status`
- `domain_purchase.set_nameservers`, `domain_purchase.hosting_purchase`, `domain_purchase.hosting_status`

Alice asks for beginner-friendly personal website tutorials in one public help
thread. Bob answers there, explains website preparation, and introduces FOSSBilling
domain and DNS Hosting services. Both continue the same help thread.
Both read recent posts and thread context, reply using `in_reply_to_id`, avoid
repeated answers and courtesy loops, and send at most one post per round. These
are prompt instructions, not runtime-enforced limits.

Domain purchase/hosting tools are available to Alice only. Bob receives the
`fossbilling_admin` service configuration for future admin tools; no admin login
or query tool is implemented yet. His prompt includes initial domain pricing and
DNS Hosting nameservers, explicitly distinguished from live backend data.

During Mastodon startup, SocialMediaService creates/reuses a limited token
for each account. Each agent receives only its own credential directory through
a read-only named volume (`e15-socialmedia-alice` / `e15-socialmedia-bob`).
Token files are owned by the agent UID 10001 with mode 0600 and are not baked
into images. Tools may report missing credentials until Mastodon initialization
finishes. Check `/var/log/mastodon-initialize.log` in the Mastodon container if needed.

From `output/`, test without invoking the model:

```bash
docker compose exec --user emuvista-agent hnode_161_agent_alice agentctl call socialmedia.account_lookup '{"acct":"bob"}'
docker compose exec --user emuvista-agent hnode_161_agent_bob agentctl call socialmedia.timeline_read '{"timeline":"public","limit":5}'
```

Check `successful` and `outcome_unknown`. Do not blindly repeat an uncertain
write; inspect your own posts first and reuse the same idempotency key for the
same submission. Model `.env` stays mounted read-only, outside the images.

From the E15 directory, start the monitor:

```bash
../../.venv/bin/python monitor.py
# http://localhost:8090/
```

Validation is limited to generation and configuration checks unless explicitly
reported otherwise. A successful build does not establish live messaging or purchase success.

## Domain purchase and DNS lookup

The [domain_purchase package](../../services/AgentService/tools/domain_purchase/README.md)
uses Alice's FOSSBilling customer account from `domains.example.yaml` (client-alice). It creates a one-year domain order and confirms only FakePayment
simulation payments within the specified maximum. Domain registration itself does
not create DNS hosting or records; DNS Hosting has separate tools.
Alice seeks website-building help and chooses her next steps.
Bob explains the steps and relevant domain services. No fixed purchase
sequence or mandatory purchase outcome is prescribed.

Each agent has a separate `e15-domain-purchases-alice` or
`e15-domain-purchases-bob` volume storing purchase progress. Retain these volumes
when rebuilding. Repeated purchase calls for the same account/domain return the
journal rather than submitting again. Use `domain_purchase.status` after a timeout;
if no order ID was obtained, reconcile through the portal. An over-limit invoice
remains unpaid and is not automatically retried when you raise the limit.

Examples from `output/` (the purchase command creates an order and submits a
simulated payment; replace the domain with your intended unregistered name):

```bash
docker compose exec --user emuvista-agent hnode_161_agent_alice agentctl call dns.lookup '{"name":"www.alice.com","record_type":"A"}'
docker compose exec --user emuvista-agent hnode_161_agent_alice agentctl call domain_purchase.purchase '{"domain":"alice-tool-demo.com","max_amount_minor":1500}'
docker compose exec --user emuvista-agent hnode_161_agent_alice agentctl call domain_purchase.status '{"domain":"alice-tool-demo.com"}'
```

The [DNS tool](../../services/AgentService/tools/dns/README.md) uses the agent's
resolver unless a server IP is specified. NXDOMAIN, empty NOERROR and timeout are
different results. A newly purchased domain does not necessarily have an A record.

Validation for these additions: mocked customer checkout/payment/status, payment
limit, lost checkout acknowledgement, duplicate suppression, DNS response parsing
and authorization checks; temporary deployment generation and agent-volume
inspection. No live purchase or DNS resolution was performed by this change.
No AgentService runtime or repository test files were modified.
