<?php
declare(strict_types=1);

/** FOSSBilling 0.8.7 模拟支付适配器。 / Simulation payment adapter for FOSSBilling 0.8.7. */
class Payment_Adapter_FakePayment implements FOSSBilling\InjectionAwareInterface
{
    protected ?Pimple\Container $di = null;

    /** 保存网关参数。 / Store gateway settings. */
    public function __construct(private array $config) {}

    /** 设置依赖容器。 / Set the dependency container. */
    public function setDi(Pimple\Container $di): void { $this->di = $di; }

    /** 读取依赖容器。 / Return the dependency container. */
    public function getDi(): ?Pimple\Container { return $this->di; }

    /** 声明单次仿真付款能力。 / Declare support for one-time simulation payments. */
    public static function getConfig(): array
    {
        return [
            'supports_one_time_payments' => true,
            'supports_subscriptions' => false,
            'description' => 'B02d 本地仿真支付，不涉及真实资金。',
            // 使用发行包自带的图标并提供结账所需字段。 / Use the bundled icon and supply all fields required by checkout.
            'logo' => [
                'logo' => 'default.png',
                'height' => '50px',
                'width' => '100px',
            ],
            'form' => [],
        ];
    }

    /** 读取服务生成的地址配置。 / Read service-generated endpoint settings. */
    private function settings(): array
    {
        return json_decode(file_get_contents('/opt/b02d/payment-config.json'), true, 512, JSON_THROW_ON_ERROR);
    }

    /** 读取共享签名密钥。 / Read the shared signing secret. */
    private function secret(): string
    {
        return trim(file_get_contents('/opt/b02d/payment-secret'));
    }

    /** 生成已签名的收银台表单。 / Generate a signed checkout form. */
    public function getHtml(FOSSBilling\Api\Proxy $api_admin, int $invoice_id, bool $subscription): string
    {
        if ($subscription) {
            throw new Payment_Exception('fakePayment 仅支持单次付款');
        }
        $invoice = $this->di['db']->load('Invoice', $invoice_id);
        if (!$invoice instanceof Model_Invoice || $invoice->status === Model_Invoice::STATUS_PAID) {
            throw new Payment_Exception('发票不存在或已付款');
        }
        $service = $this->di['mod_service']('Invoice');
        $amount = number_format((float) $service->getTotalWithTax($invoice), 2, '.', '');
        $currency = strtoupper((string) $invoice->currency);
        $url = parse_url((string) $this->config['notify_url']);
        if (!is_array($url) || !isset($url['path'])) {
            throw new Payment_Exception('网关回调地址无效');
        }
        $settings = $this->settings();
        $notify = $settings['notify_origin'] . $url['path'];
        if (isset($url['query'])) {
            $notify .= '?' . $url['query'];
        }
        $values = [(string) $invoice_id, $amount, $currency, $notify];
        $signature = hash_hmac('sha256', implode('|', $values), $this->secret());
        $fields = array_combine(['invoice', 'amount', 'currency', 'notify', 'signature'], [...$values, $signature]);
        // 根据明确配置的浏览器入口选择收银台，否则使用仿真网络地址。
        // Select checkout by explicitly configured browser origin, otherwise use the simulation address.
        $host = strtolower($_SERVER['HTTP_HOST'] ?? '');
        $paymentUrl = $settings['browser_urls'][$host] ?? $settings['payment_url'];
        $html = '<form method="post" action="' . htmlspecialchars($paymentUrl, ENT_QUOTES) . '">';
        foreach ($fields as $key => $value) {
            $html .= '<input type="hidden" name="' . htmlspecialchars($key, ENT_QUOTES) . '" value="'
                . htmlspecialchars($value, ENT_QUOTES) . '">';
        }
        return $html . '<button type="submit">前往 fakePayment 模拟付款</button></form>';
    }

    /** 校验回调并沿用发票支付流程。 / Verify callbacks and use the invoice payment workflow. */
    public function processTransaction($api_admin, $id, $data, $gateway_id): void
    {
        $post = $data['post'] ?? [];
        $keys = ['invoice_id', 'amount', 'currency', 'txn_id', 'status'];
        foreach ([...$keys, 'signature'] as $key) {
            if (!isset($post[$key]) || !is_scalar($post[$key])) {
                throw new Payment_Exception('fakePayment 回调字段缺失');
            }
        }
        $values = array_map(static fn($key) => (string) $post[$key], $keys);
        $expected = hash_hmac('sha256', implode('|', $values), $this->secret());
        if (!hash_equals($expected, (string) $post['signature']) || $post['status'] !== 'completed') {
            throw new Payment_Exception('fakePayment 回调签名或状态错误');
        }
        $invoiceId = filter_var($post['invoice_id'], FILTER_VALIDATE_INT);
        if (!$invoiceId || $post['txn_id'] !== 'fake-' . $invoiceId) {
            throw new Payment_Exception('fakePayment 交易号错误');
        }
        $invoice = $this->di['db']->load('Invoice', $invoiceId);
        if (!$invoice instanceof Model_Invoice) {
            throw new Payment_Exception('发票不存在');
        }
        $tx = $api_admin->invoice_transaction_get(['id' => $id]);
        if (!empty($tx['invoice_id']) && (int) $tx['invoice_id'] !== $invoiceId) {
            throw new Payment_Exception('交易与发票不匹配');
        }
        if ($invoice->status === Model_Invoice::STATUS_PAID) {
            return;
        }
        if (!$api_admin->invoice_transaction_claim_for_processing(['id' => $id])) {
            return;
        }
        $service = $this->di['mod_service']('Invoice');
        $service->validatePaymentAmount((float) $post['amount'], $service->getTotalWithTax($invoice));
        if (strtoupper((string) $post['currency']) !== strtoupper((string) $invoice->currency)) {
            throw new Payment_Exception('付款币种不匹配');
        }
        $api_admin->invoice_transaction_update([
            'id' => $id, 'invoice_id' => $invoiceId, 'txn_id' => $post['txn_id'],
            'txn_status' => 'completed', 'amount' => $post['amount'], 'currency' => $post['currency'],
        ]);
        $api_admin->client_balance_add_funds([
            'id' => $invoice->client_id, 'amount' => $post['amount'],
            'description' => 'fakePayment ' . $post['txn_id'],
            'type' => 'fakePayment', 'rel_id' => $post['txn_id'],
        ]);
        if (!$invoice->approved) {
            $service->approveInvoice($invoice, ['use_credits' => false]);
        }
        $api_admin->invoice_pay_with_credits(['id' => $invoiceId]);
    }
}
