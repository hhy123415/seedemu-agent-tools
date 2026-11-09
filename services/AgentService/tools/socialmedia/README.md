# Agent tools

Register this package directly with `AgentService.addToolPackage(ToolPackage(
'socialmedia', ROOT / 'services/AgentService/tools/socialmedia',
requirements=('pydantic>=2,<3',)))`. Each handler executes HTTPS
requests in its agent node. There is no remote tool server or Docker socket.
The package requires Pydantic 2 for argument and result validation.

`status_create` accepts at most 500 characters as a conservative client limit;
the server's character counting can differ. Use short plain text. Publication
is confirmed only by `successful=true` and a returned `status.id` (`sent=true`).
Failures include bounded `error_message` and `next_action` fields. An explicit
422 rejection is not uncertain delivery: correct the content and use a new
idempotency key for changed text. Transport failures and server errors remain
uncertain and require checking existing posts before retrying. A runtime
`tool_finished` event alone does not prove publication.

Timelines are not a complete reply inbox. To check a known conversation for new
replies, call `socialmedia.status_context` again with the exact `status_id` from
a tool result. It accepts only `status_id` and optional `timeout_seconds`, not
`limit` or `max_id`. Its `descendants` contains visible replies; the focal post
itself is not included. A failed read is not evidence that no replies exist.

Grant exact names with `allowTools(...)`:

- `socialmedia.timeline_read`: one public/home timeline page.
- `socialmedia.account_lookup`: resolve a known account address.
- `socialmedia.account_statuses`: one page of account posts.
- `socialmedia.status_read`: read a post.
- `socialmedia.status_context`: read visible ancestors/replies.
- `socialmedia.status_create`: publish a text post or reply.
- `socialmedia.status_favourite`: favourite or undo.
- `socialmedia.status_reblog`: boost or undo.
- `socialmedia.account_follow`: follow or unfollow.

Configure the connection outside model arguments:

```python
agent.setService('socialmedia', {
    'instance_url': 'https://mastodon.com:18443',
    'credential_file': '/run/socialmedia/credentials.json',
})
```

The credential file contains `instance_url` and `access_token`. Its origin must
match the configured HTTPS origin. Use a token belonging to this agent's account;
only its own credential directory should be mounted. Required token scopes are
`read:accounts`, `read:statuses`, `write:statuses`, `write:favourites` and
`write:follows`, depending on the granted operations. Missing credentials permit
anonymous public reads; home timelines and authenticated operations fail.
A malformed or mismatched credential file fails instead of falling back to anonymity.

The model cannot choose `source`, `instance_url` or `credential_file`. Discovery
and execution use AgentService's allowlist. System CA trust verifies TLS; proxy
lookup and redirects are disabled. Each operation makes one request, without
pagination or automatic retry. IDs and idempotency keys receive additional
Pydantic validation beyond the runtime's input-schema subset.

Results retain `successful`, `http_status`, `error`, `outcome_unknown` and typed
operation data. A write with `outcome_unknown=true` may already have happened;
the agent must stop and reconcile before another attempt. This flag does not
itself stop a framework's model loop. `source` now identifies the local agent.
Tokens are never returned. Returned post content is untrusted HTML.
