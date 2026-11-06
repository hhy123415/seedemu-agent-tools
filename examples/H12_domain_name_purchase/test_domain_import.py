"""Offline import checks; run directly with emuvista/.venv/bin/python."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
from domain_name_purchase import build_emulator
from DomainService import DomainDataService, DnsService, NamingoRegistryService, FossBillingRegistrarService


HERE = Path(__file__).resolve().parent


class DomainImportTest(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load((HERE / 'domains.example.yaml').read_text())
        for client in self.document['clients'].values():
            client['password'] = 'test-only-password'
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def load(self, document=None):
        path = Path(self.temp.name) / 'domains.yaml'
        path.write_text(yaml.safe_dump(document if document is not None else self.document))
        return DomainDataService().importFile(path)

    def build(self, data):
        with patch('builtins.print'), patch('domain_name_purchase.DomainDataService', return_value=data), \
                patch.object(data, 'importFile', return_value=data):
            emu = build_emulator()
        return emu

    def render(self, emu):
        with patch('builtins.print'):
            emu.render()

    def files(self, emu, vnode):
        return dict(file.get() for file in emu.getBindingFor(vnode).getFiles())

    def test_h12_import_artifacts_and_ownership(self):
        emu = self.build(self.load())
        self.render(emu)
        registry = self.files(emu, 'registry')
        registrar = self.files(emu, 'fossbilling')
        primary = self.files(emu, 'hosted-dns-primary')
        secondary = self.files(emu, 'hosted-dns-secondary')
        rows = json.loads(registry['/opt/registry/import-domains.json'])
        self.assertEqual([d['name'] for d in rows], ['alice.com', 'bob.net'])
        self.assertNotIn('client', rows[0])
        customers = json.loads(registrar['/opt/fossbilling/import-domains.json'])
        self.assertEqual(customers[0]['client']['email'], 'alice@example.com')
        dns = emu.getLayer('DomainNameService')
        for name in ('alice.com', 'bob.net'):
            path = f'/etc/bind/zones/{name}.'
            self.assertIn(f'$ORIGIN {name}.', primary[path])
            self.assertIn('@ IN NS ns1.example.com.', primary[path])
            self.assertEqual(primary[path], secondary[path])
            self.assertEqual(primary[path].count(' IN SOA '), 1)
            self.assertEqual(primary[path].count(' IN NS '), 2)
            self.assertEqual(dns.getMasterIp()[name + '.'], ['10.170.0.71'])
            self.assertCountEqual(dns.getZoneServerNames(name + '.'),
                                  ['hosted-dns-primary', 'hosted-dns-secondary'])
            self.assertEqual(primary[path], '\n'.join(dns.getZone(name + '.').getRecords()))
        self.assertIn('type slave; masters { 10.170.0.71; }', secondary['/etc/bind/named.conf.zones'])
        self.assertNotIn('zone "alice.com', primary['/etc/bind/named.conf.local'])
        self.assertNotIn('/opt/registry/import-domains.json', primary)
        self.assertFalse(any('alice.com.' in record for record in
                             emu.getLayer('DomainNameService').getZone('com.').getRecords()))

    def test_explicit_native_zones_share_master_registration(self):
        from seedemu.core import Emulator, Binding, Filter
        from seedemu.layers import Base
        base = Base()
        system = base.createAutonomousSystem(150)
        system.createNetwork('net')
        system.createHost('primary').joinNetwork('net', address='10.150.0.71')
        system.createHost('secondary').joinNetwork('net', address='10.150.0.72')
        dns = DnsService()
        primary = dns.install('primary').addZone('test.com.', createNsAndSoa=False)
        self.assertFalse(primary.isMaster())
        primary.setMaster()
        self.assertTrue(primary.isMaster())
        dns.install('secondary').addZone('test.com.', createNsAndSoa=False)
        dns.getZone('test.com.').addRecord('@ IN SOA ns.test.com. hostmaster.test.com. (1 900 900 1800 60)')
        emu = Emulator()
        emu.addLayer(base)
        emu.addLayer(dns)
        for name in ('primary', 'secondary'):
            emu.addBinding(Binding(name, filter=Filter(asn=150, nodeName='^' + name + '$')))
        self.render(emu)
        self.assertEqual(dns.getMasterIp()['test.com.'], ['10.150.0.71'])
        self.assertIn('type slave; masters { 10.150.0.71; }',
                      self.files(emu, 'secondary')['/etc/bind/named.conf.zones'])

    def test_missing_contact_does_not_dispatch_any_domain(self):
        self.document['domains'][1]['registrant'] = 'missing'
        emu = self.build(self.load())
        with self.assertRaises(KeyError):
            self.render(emu)
        self.assertFalse(emu.getServerByVirtualNodeName('registry')._imported_domains)
        self.assertFalse(emu.getServerByVirtualNodeName('fossbilling')._imported_domains)

    def test_registry_mismatch_is_rejected(self):
        emu = self.build(self.load())
        emu.getServerByVirtualNodeName('fossbilling').setRegistry('another-registry')
        with self.assertRaisesRegex(ValueError, 'different Registry'):
            self.render(emu)
        self.assertFalse(emu.getServerByVirtualNodeName('registry')._imported_domains)

    def test_duplicate_domain_is_rejected(self):
        self.document['domains'].append(deepcopy(self.document['domains'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate domain'):
            self.load()

    def test_apex_ns_cannot_override_shared_nameservers(self):
        self.document['domains'][1]['dns']['records'].append(
            dict(name='@', type='NS', value='wrong.example.com.'))
        emu = self.build(self.load())
        with self.assertRaisesRegex(ValueError, 'apex NS'):
            self.render(emu)
        self.assertFalse(emu.getServerByVirtualNodeName('registry')._imported_domains)

    def test_multiple_service_instances_receive_only_their_domains(self):
        from types import SimpleNamespace
        dns = DnsService()
        dns.install('dns-one').setMaster()
        dns.install('dns-two')
        registry_layer, registrar_layer = NamingoRegistryService(), FossBillingRegistrarService()
        servers = {}
        for suffix in ('a', 'b'):
            servers['registry-' + suffix] = registry_layer.install('registry-' + suffix)
            servers['registrar-' + suffix] = registrar_layer.install('registrar-' + suffix).setRegistry('registry-' + suffix)
        for item, suffix in zip(self.document['domains'], ('a', 'b')):
            item['registration']['registry'] = 'registry-' + suffix
            item['registrar']['server'] = 'registrar-' + suffix
        self.document['hosting-nameservers'] = {'ns1.example.com': 'dns-one', 'ns2.example.com': 'dns-two'}
        addresses = {'dns-one': '192.0.2.1', 'dns-two': '192.0.2.2'}
        emulator = SimpleNamespace(getLayer=lambda name: dns,
            getServerByVirtualNodeName=servers.__getitem__,
            getBindingFor=lambda name: SimpleNamespace(getInterfaces=lambda: [
                SimpleNamespace(getAddress=lambda: addresses[name])]))
        self.load().configure(emulator)
        self.assertEqual([d['name'] for d in servers['registry-a']._imported_domains], ['alice.com'])
        self.assertEqual([d['name'] for d in servers['registrar-b']._imported_domains], ['bob.net'])


if __name__ == '__main__':
    unittest.main()
