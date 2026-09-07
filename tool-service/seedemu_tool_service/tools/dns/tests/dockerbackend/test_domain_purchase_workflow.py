"""End-to-end B02a domain purchase through Agent-facing Docker tools.

Run this test against a freshly started B02a deployment.  It intentionally owns
``example.com`` and therefore must not share a Registry database with a prior
B02a topology test that already registered that domain.
"""

import json
import time
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

import anyio

from seedemu_tool_service.backends import DockerRuntimeBackend
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools
from seedemu_tool_service.tools.dns.domain_registration.tools import RegistrarMetadataError

SOURCE = "as150h-host_1-10.150.0.72"
DNS_SERVICE_ID = "b02a.source-owned-dns"
REGISTRAR_URL = "https://10.150.0.74:443"
ZONE = "example.com"
NAME = "www.example.com"
ANSWER = "11.160.0.80"
COM_SERVER = "10.152.0.71"
RECURSIVE_RESOLVERS = ("10.152.0.53", "10.153.0.53")
OWNER_DNS = ["11.160.0.53", "11.160.0.54"]


class _HiddenFields(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("type") == "hidden":
            name = values.get("name")
            value = values.get("value")
            if name is not None and value is not None:
                self.fields[name] = value


def _hidden_fields(html: str) -> dict[str, str]:
    parser = _HiddenFields()
    parser.feed(html)
    assert parser.fields, "Loom form did not expose its CSRF fields"
    return parser.fields


def _invoke(registry: ToolRegistry, name: str, arguments: dict):
    return anyio.run(registry.invoke, name, arguments)


def _registrar_request(
    registry: ToolRegistry,
    session_id: str | None,
    path: str,
    *,
    method: str = "GET",
    fields: list[tuple[str, str]] | None = None,
):
    arguments = {
        "source": SOURCE,
        "registrar_url": REGISTRAR_URL,
        "session_id": session_id,
        "method": method,
        "path": path,
        "authentication": "required",
    }
    if fields is not None:
        arguments.update({
            "content_type": "application/x-www-form-urlencoded",
            "body": urlencode(fields),
        })
    return _invoke(registry, "domain.registrar_request", arguments)


def _wait_for_registrar(registry: ToolRegistry):
    """Wait for Loom's HTTPS, database bootstrap, and source auth endpoint."""
    last_error: Exception | None = None
    for _ in range(30):
        try:
            return _registrar_request(registry, None, "/")
        except RegistrarMetadataError as error:
            last_error = error
            time.sleep(2)
    raise AssertionError("Loom did not become ready within 60 seconds") from last_error


def test_agent_configures_dns_buys_example_com_and_resolves_it() -> None:
    """Exercise discovery, Loom purchase, EPP delegation, and DNS resolution."""

    registry = ToolRegistry()
    backend = DockerRuntimeBackend()
    register_dns_tools(registry, backend)

    directory = _invoke(registry, "domain.registrar_find", {})
    loom = [item for item in directory.registrars if item.registrar_url == REGISTRAR_URL]
    assert len(loom) == 1, "B02a must expose exactly one Loom frontend"

    configured = _invoke(registry, "dns.configure", {
        "source": SOURCE,
        "dns_service_id": DNS_SERVICE_ID,
        "zone": ZONE,
        "changes": [{
            "name": NAME,
            "record_type": "A",
            "operation": "replace",
            "ttl": 300,
            "value": ANSWER,
        }],
    })
    assert configured.successful, configured.stderr
    assert configured.primary_authoritative and configured.secondary_authoritative
    assert configured.primary_soa == configured.secondary_soa

    session_id = None
    try:
        ready = _wait_for_registrar(registry)
        session_id = ready.session_id
        order_form = _registrar_request(
            registry, session_id, f"/orders/register/{ZONE}"
        )
        assert order_form.authenticated
        assert order_form.http_status == 200, order_form.stderr
        csrf = list(_hidden_fields(order_form.body).items())
        order = _registrar_request(
            registry,
            session_id,
            f"/orders/register/{ZONE}",
            method="POST",
            fields=csrf + [
                ("reg-years", "1"),
                ("authInfo", "B02a-Example-Auth-1"),
                ("nameserver[]", "ns1.example.com"),
                ("nameserver_ipv4[]", OWNER_DNS[0]),
                ("nameserver_ipv6[]", ""),
                ("nameserver[]", "ns2.example.com"),
                ("nameserver_ipv4[]", OWNER_DNS[1]),
                ("nameserver_ipv6[]", ""),
            ],
        )
        assert order.http_status == 302, order.body
        assert order.location and order.location.startswith("/invoice/")
        invoice_id = urlsplit(order.location).path.rstrip("/").rsplit("/", 1)[-1]

        payment_form = _registrar_request(
            registry, session_id, f"/invoice/{invoice_id}/pay"
        )
        assert payment_form.http_status == 200, payment_form.stderr
        assert 'value="balance"' in payment_form.body
        payment = _registrar_request(
            registry,
            session_id,
            "/balance-payment",
            method="POST",
            fields=list(_hidden_fields(payment_form.body).items())
            + [("paymentMethod", "balance")],
        )
        assert payment.http_status == 200, payment.stderr
        payment_result = json.loads(payment.body)
        assert payment_result.get("success") is True, payment_result

        services = _registrar_request(
            registry, session_id, "/api/records/services?order=id,desc&page=1,10"
        )
        assert services.http_status == 200
        service_records = json.loads(services.body).get("records", [])
        purchased = [
            record
            for record in service_records
            if json.loads(record.get("config") or "{}").get("domain") == ZONE
        ]
        assert len(purchased) == 1, service_records
        assert purchased[0].get("status") == "active", purchased[0]
    finally:
        if session_id is not None:
            _invoke(registry, "domain.registrar_request", {
                "source": SOURCE,
                "registrar_url": REGISTRAR_URL,
                "session_id": session_id,
                "path": "/",
                "close_session": True,
                "authentication": "required",
            })

    whois = None
    rdap = None
    rdap_domain = None
    for _ in range(20):
        whois = backend.execute(
            SOURCE, ["whois", "-h", "whois.registrar.com", ZONE]
        )
        rdap = backend.execute(
            SOURCE,
            ["curl", "-fsS", "--max-time", "5", f"http://rdap.registrar.com/domain/{ZONE}"],
        )
        try:
            rdap_domain = json.loads(rdap.stdout).get("ldhName")
        except (json.JSONDecodeError, AttributeError):
            rdap_domain = None
        if (
            whois.exit_code == 0
            and "Domain Name: EXAMPLE.COM" in whois.stdout
            and rdap.exit_code == 0
            and rdap_domain == ZONE
        ):
            break
        time.sleep(2)
    assert whois is not None and whois.exit_code == 0, whois.stderr if whois else ""
    assert "Domain Name: EXAMPLE.COM" in whois.stdout, whois.stdout
    assert rdap is not None and rdap.exit_code == 0, rdap.stderr if rdap else ""
    assert rdap_domain == ZONE, rdap.stdout

    delegation = None
    for _ in range(30):
        delegation = _invoke(registry, "dns.check_delegation", {
            "source": SOURCE,
            "zone": ZONE,
            "parent_server": COM_SERVER,
            "child_servers": OWNER_DNS,
            "timeout_seconds": 3,
        })
        if delegation.consistent:
            break
        time.sleep(3)
    assert delegation is not None and delegation.consistent, delegation.issues
    assert delegation.parent_ns_names == ["ns1.example.com.", "ns2.example.com."]
    assert delegation.missing_glue_names == []

    pending_resolvers = set(RECURSIVE_RESOLVERS)
    resolver_results = {}
    for _ in range(60):
        for resolver in tuple(pending_resolvers):
            lookup = _invoke(registry, "dns.lookup", {
                "source": SOURCE,
                "name": NAME,
                "record_type": "A",
                "server": resolver,
                "include_details": True,
            })
            resolver_results[resolver] = lookup
            if (
                lookup.command_successful
                and lookup.response_status == "NOERROR"
                and lookup.answers == [ANSWER]
            ):
                pending_resolvers.remove(resolver)
        if not pending_resolvers:
            break
        time.sleep(3)

    assert not pending_resolvers, {
        resolver: resolver_results.get(resolver)
        for resolver in sorted(pending_resolvers)
    }
    for resolver in RECURSIVE_RESOLVERS:
        lookup = resolver_results[resolver]
        assert lookup.command_successful, (resolver, lookup)
        assert lookup.response_status == "NOERROR", (resolver, lookup)
        assert lookup.answers == [ANSWER], (resolver, lookup)
