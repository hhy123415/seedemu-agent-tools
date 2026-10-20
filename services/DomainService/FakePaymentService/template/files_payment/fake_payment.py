#!/usr/bin/env python3
"""仿真收银台：验证请求签名，确认后回调 FOSSBilling。 / Simulation checkout: verify request signatures and notify FOSSBilling after confirmation."""
from decimal import Decimal, InvalidOperation
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


def signature(secret, *values):
    """计算字段顺序固定的 HMAC。 / Compute an HMAC over ordered fields."""
    return hmac.new(secret, '|'.join(values).encode(), hashlib.sha256).hexdigest()


class Handler(BaseHTTPRequestHandler):
    """处理健康检查和模拟付款表单。 / Handle health checks and simulated payment forms."""

    def do_GET(self):
        """提供健康检查；付款只能使用 POST。 / Provide health checks; payments require POST."""
        if self.path == '/health':
            return self.reply(200, 'ok')
        return self.reply(404, 'not found')

    def do_POST(self):
        """验证金额、回调来源和签名，用户确认后才发起回调。 / Validate amount, callback origin, and signature; notify only after confirmation."""
        if self.path != '/pay':
            return self.reply(404, 'not found')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.reply(400, 'invalid content length')
        if size < 0 or size > 8192:
            return self.reply(413, 'request too large')
        try:
            fields = parse_qs(self.rfile.read(size).decode(), keep_blank_values=True)
        except UnicodeDecodeError:
            return self.reply(400, 'invalid form encoding')
        values = {key: fields.get(key, [''])[0] for key in ('invoice', 'amount', 'currency', 'notify', 'signature', 'action')}
        invoice, amount, currency, notify = (values[key] for key in ('invoice', 'amount', 'currency', 'notify'))
        try:
            origin = urlsplit(self.server.payment_settings['notify_origin'])
            callback = urlsplit(notify)
            valid_origin = (callback.scheme == origin.scheme and callback.netloc == origin.netloc
                            and not callback.username and not callback.password and not callback.fragment
                            and callback.path.startswith('/'))
            number = Decimal(amount)
            if not number.is_finite() or number <= 0:
                raise InvalidOperation
        except (ValueError, InvalidOperation):
            return self.reply(400, 'invalid payment request')
        if not invoice.isascii() or not invoice.isdecimal() or not currency.isascii() or len(currency) != 3 or not currency.isalpha() or not valid_origin:
            return self.reply(400, 'invalid payment request')
        expected = signature(self.server.payment_secret, invoice, amount, currency, notify)
        if not hmac.compare_digest(values['signature'].encode(), expected.encode()):
            return self.reply(403, 'invalid signature')
        if values['action'] != 'confirm':
            form = ''.join(f'<input type="hidden" name="{key}" value="{escape(values[key], quote=True)}">'
                           for key in ('invoice', 'amount', 'currency', 'notify', 'signature'))
            return self.reply(200, f'<h1>fakePayment</h1><p>Invoice #{invoice}: {escape(amount)} {escape(currency)}</p>'
                              f'<form method="post" action="/pay">{form}<button name="action" value="confirm">模拟支付成功</button></form>', 'text/html')
        payload = {'invoice_id': invoice, 'amount': amount, 'currency': currency,
                   'txn_id': f'fake-{invoice}', 'status': 'completed'}
        payload['signature'] = signature(self.server.payment_secret, *payload.values())
        try:
            with urlopen(Request(notify, urlencode(payload).encode(), method='POST'), timeout=15) as response:
                response.read(4096)
                if response.status != 200:
                    raise ValueError('Callback rejected')
        except Exception:
            return self.reply(502, 'FOSSBilling callback failed; check invoice status before retrying')
        self.reply(200, f'<h1>模拟付款已提交</h1><p>发票 #{invoice}；请返回 FOSSBilling 检查发票、订单及域名状态。</p>', 'text/html')

    def reply(self, status, body, content_type='text/plain'):
        """发送 UTF-8 响应。 / Send a UTF-8 response."""
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(address, settings, secret):
    """为独立实例创建 HTTP 服务。 / Create an HTTP server for an isolated instance."""
    server = ThreadingHTTPServer(address, Handler)
    server.payment_settings = settings
    server.payment_secret = secret
    return server


if __name__ == '__main__':
    settings = json.loads(Path('/opt/b02d/payment-config.json').read_text())
    secret = Path('/opt/b02d/secret').read_text().strip().encode()
    create_server(('0.0.0.0', settings['port']), settings, secret).serve_forever()
