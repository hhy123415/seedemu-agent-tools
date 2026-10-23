"""Provide an independent simulated payment checkout."""
import json
from urllib.parse import urlsplit
from seedemu.core import Server, Service
from ..FossBillingService import FossBillingServer
from .template import PaymentFileTemplates


class FakePaymentServer(Server):
    """Manage checkout and its registrar adapter."""

    def __init__(self):
        """Initialize demonstration settings."""
        super().__init__()
        self._forwarded_port = 18083
        self._registrar = 'fossbilling'
        self._secret = 'b02d-fake-payment-demo-secret'
        self._port = 8080
        self._browser_urls = {'localhost:18080': 'http://localhost:18083/pay',
                              '127.0.0.1:18080': 'http://127.0.0.1:18083/pay'}
        self._registrar_node = None
        self.appendClassName('FakePaymentService')
        self.setDisplayName('FakePayment Checkout')

    def setPortForwarding(self, host_port):
        """Set the host Web port; None disables forwarding."""
        if host_port is not None and (type(host_port) is not int or not 1 <= host_port <= 65535):
            raise ValueError('Host port must be an integer between 1 and 65535, or None')
        self._forwarded_port = host_port
        return self

    def setRegistrar(self, virtual_node):
        """Select the FOSSBilling virtual node."""
        if not isinstance(virtual_node, str) or not virtual_node:
            raise ValueError('A registrar virtual node is required')
        self._registrar = virtual_node
        return self

    def setSharedSecret(self, secret):
        """Set the shared checkout and adapter signing secret."""
        if not isinstance(secret, str) or not secret or secret != secret.strip() or any(c in secret for c in '\x00\r\n'):
            raise ValueError('Secret must be nonempty without surrounding whitespace or control delimiters')
        self._secret = secret
        return self

    def setPort(self, port):
        """Set the internal listening port."""
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Port must be an integer between 1 and 65535')
        self._port = port
        return self

    def setBrowserUrls(self, urls):
        """Map browser Hosts to checkout URLs; configure forwarding separately with setPortForwarding()."""
        if not isinstance(urls, dict):
            raise ValueError('Browser URLs must be a dictionary')
        checked = {}
        for host, url in urls.items():
            if not isinstance(host, str) or not isinstance(url, str):
                raise ValueError('Browser Hosts and URLs must be strings')
            source, target = urlsplit('http://' + host), urlsplit(url)
            if (not source.hostname or source.username or source.password or source.path or source.query or source.fragment
                    or source.port == 0 or target.scheme not in ('http', 'https') or not target.hostname
                    or target.username or target.password or target.port == 0 or target.path != '/pay'
                    or target.query or target.fragment or any(c.isspace() for c in host + url) or '\\' in host + url):
                raise ValueError('Expected host[:port] mapped to an HTTP(S) /pay URL')
            checked[host.lower()] = url
        self._browser_urls = checked
        return self

    def configure(self, emulator, node):
        """Derive internal payment and callback addresses from bindings."""
        registrar = emulator.getServerByVirtualNodeName(self._registrar)
        if not isinstance(registrar, FossBillingServer):
            raise ValueError('The registrar must use FossBillingService')
        billing = emulator.getBindingFor(self._registrar)
        if billing is node:
            raise ValueError('Checkout and registrar require distinct hosts')
        self._registrar_node = billing
        self._settings = {'port': self._port, 'browser_urls': dict(self._browser_urls),
                          'payment_url': f'http://{node.getInterfaces()[0].getAddress()}:{self._port}/pay',
                          'notify_origin': f'http://{billing.getInterfaces()[0].getAddress()}:8080'}

    def install(self, node):
        """Install checkout, adapter, and shared signing configuration."""
        if self._registrar_node is None:
            raise RuntimeError('Render the emulator before installing payment')
        billing = self._registrar_node
        node.addSoftware('python3')
        node.setFile('/opt/fake-payment/fake_payment.py', PaymentFileTemplates['fake_payment.py'])
        billing.setFile('/var/www/fossbilling/library/Payment/Adapter/FakePayment.php', PaymentFileTemplates['FakePayment.php'])
        for host, name in ((node, 'secret'), (billing, 'payment-secret')):
            host.setFile('/opt/fake-payment/payment-config.json', json.dumps(self._settings))
            host.setFile('/opt/fake-payment/' + name, self._secret + '\n')
            command = ('chown root:www-data /opt/fake-payment/payment-secret && chmod 640 /opt/fake-payment/payment-secret'
                       if host is billing else 'chmod 600 /opt/fake-payment/secret')
            host.addBuildCommandAtEnd(command)
            host.appendStartCommand(command)
        billing.setFile('/opt/fake-payment/setup-gateway.php', PaymentFileTemplates['setup-gateway.php'])
        billing.setFile('/opt/fake-payment/setup-gateway.sh', PaymentFileTemplates['setup-gateway.sh'])
        billing.appendStartCommand('sh /opt/fake-payment/setup-gateway.sh > /var/log/fake-payment-initialize.log 2>&1')
        node.appendStartCommand('python3 /opt/fake-payment/fake_payment.py > /var/log/fake-payment.log 2>&1', fork=True)
        if self._forwarded_port is not None:
            node.addPortForwarding(self._forwarded_port, self._port)

    def print(self, indent):
        """Return the instance description."""
        return ' ' * indent + 'FakePayment checkout server\n'


class FakePaymentService(Service):
    """Add simulated payments to FOSSBilling."""

    def __init__(self):
        """Declare registrar dependencies."""
        super().__init__()
        for name in ('Base', 'Routing', 'FossBillingService'):
            self.addDependency(name, False, False)

    def configure(self, emulator):
        """Configure one gateway instance per registrar."""
        registrars = set()
        for vnode, server in self._pending_targets.items():
            server.configure(emulator, emulator.getBindingFor(vnode))
            if id(server._registrar_node) in registrars:
                raise ValueError('Each registrar supports one FakePayment instance')
            registrars.add(id(server._registrar_node))
        super().configure(emulator)

    def _createServer(self):
        """Create a checkout instance."""
        return FakePaymentServer()

    def getName(self):
        """Return the service name."""
        return 'FakePaymentService'

    def print(self, indent):
        """Return the service description."""
        return ' ' * indent + 'FakePaymentServiceLayer\n'
