import json
from typing import Literal
from urllib.parse import urlencode

from pydantic import TypeAdapter, ValidationError

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.socialmedia.models import (
    AccountInfo,
    AccountFollowResult,
    AccountLookupResult,
    RelationshipInfo,
    StatusContextInfo,
    StatusContextResult,
    StatusCreateResult,
    StatusInfo,
    TimelineReadResult,
)

# Read request settings from argv, perform one HTTPS request, and write a JSON
# result to stdout. Passing settings separately keeps user data out of the code.
_REQUEST_SCRIPT = r"""
import json, socket, ssl, sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Report redirects as HTTP results instead of forwarding credentials
        # or a write to a different endpoint.
        return None

# Decode the request configuration and initialize the result before attempting I/O.
cfg = json.loads(sys.argv[1])
out = {"http_status": None, "error": None, "data": None, "outcome_unknown": False}
sent = False
try:
    headers = {"Accept": "application/json"}
    if cfg["credential_file"]:
        # Load the token and compare its recorded origin with the request origin.
        # Reject a mismatch before adding the token to the Authorization header.
        with open(cfg["credential_file"]) as stream:
            credentials = json.load(stream)
        if credentials["instance_url"].rstrip("/") != cfg["instance_url"]:
            raise ValueError("credential origin mismatch")
        token = credentials["access_token"]
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError("invalid credential")
        headers["Authorization"] = "Bearer " + token
    if cfg["idempotency_key"]:
        headers["Idempotency-Key"] = cfg["idempotency_key"]
    # Leave GET requests bodyless; encode supplied write data as JSON bytes.
    body = None
    if cfg["body"] is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(cfg["body"]).encode()
    # Verify HTTPS using the system trust store, disable proxy lookup,
    # and reject automatic redirect following.
    context = ssl.create_default_context()
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    request = Request(cfg["instance_url"] + cfg["path"], data=body,
                      headers=headers, method=cfg["method"])
    # This marks the start of an attempt, not confirmed delivery of request bytes.
    # Once attempted, a failed write is conservatively treated as uncertain.
    sent = True
    try:
        response = opener.open(request, timeout=cfg["timeout_seconds"])
    except HTTPError as error:
        # urllib raises for non-success statuses, but they are still observable
        # HTTP responses. Preserve the status without exposing the response body.
        response = error
    with response:
        out["http_status"] = response.code
        if not 200 <= response.code < 300:
            out["error"] = "http_error"
        else:
            # One extra byte detects overflow without accepting a partial JSON
            # document as a complete result. No automatic pagination is performed.
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                out["error"] = "response_too_large"
            else:
                try:
                    out["data"] = json.loads(raw)
                except (ValueError, UnicodeError):
                    out["error"] = "invalid_response"
except (URLError, TimeoutError, socket.timeout, ConnectionError):
    out["error"] = "transport_error"
except Exception:
    # Do not echo exception text: file contents or request details could contain
    # secrets. Errors before the request attempt include missing/invalid files.
    out["error"] = "client_error" if not sent else "transport_error"
# Flag failed write attempts as uncertain because a missing usable response
# does not establish whether the server committed the post.
if cfg["method"] == "POST" and sent and out["error"]:
    out["outcome_unknown"] = True
print(json.dumps(out))
"""


class SocialMediaTools:
    """Execute each social media operation and return its typed result."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend


    def timeline_read(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str | None = None,
        timeout_seconds: int = 15,
        timeline: Literal["public", "home"] = "public",
        limit: int = 20,
        max_id: str | None = None,
    ) -> TimelineReadResult:
        "Read one page; never follow pagination links to another origin."
        query = {"limit": limit}
        if max_id is not None:
            query["max_id"] = max_id
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/timelines/{timeline}?{urlencode(query)}",
            method="GET",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=False)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(list[StatusInfo]).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=False)
        return TimelineReadResult(
            **metadata, statuses=data or [], next_max_id=data[-1].id if data else None
        )

    def status_create(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str,
        timeout_seconds: int = 15,
        status: str,
        visibility: Literal["public", "unlisted", "private", "direct"] = "public",
        in_reply_to_id: str | None = None,
        idempotency_key: str,
    ) -> StatusCreateResult:
        "Submit one text post without retries or scheduling."
        body = {"status": status, "visibility": visibility}
        if in_reply_to_id is not None:
            body["in_reply_to_id"] = in_reply_to_id
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path="/api/v1/statuses",
            method="POST",
            body=body,
            idempotency_key=idempotency_key,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=True)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(StatusInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=True)
        return StatusCreateResult(**metadata, status=data)

    def account_lookup(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str,
        timeout_seconds: int = 15,
        acct: str,
    ) -> AccountLookupResult:
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path="/api/v1/accounts/lookup?" + urlencode({"acct": acct}),
            method="GET",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=False)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(AccountInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=False)
        return AccountLookupResult(**metadata, account=data)

    def account_statuses(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str | None = None,
        timeout_seconds: int = 15,
        account_id: str,
        limit: int = 20,
        max_id: str | None = None,
    ) -> TimelineReadResult:
        query = {"limit": limit}
        if max_id is not None:
            query["max_id"] = max_id
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/accounts/{account_id}/statuses?{urlencode(query)}",
            method="GET",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=False)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(list[StatusInfo]).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=False)
        return TimelineReadResult(
            **metadata, statuses=data or [], next_max_id=data[-1].id if data else None
        )

    def status_read(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str | None = None,
        timeout_seconds: int = 15,
        status_id: str,
    ) -> StatusCreateResult:
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/statuses/{status_id}",
            method="GET",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=False)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(StatusInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=False)
        return StatusCreateResult(**metadata, status=data)

    def status_context(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str | None = None,
        timeout_seconds: int = 15,
        status_id: str,
    ) -> StatusContextResult:
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/statuses/{status_id}/context",
            method="GET",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=False)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(StatusContextInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=False)
        return StatusContextResult(**metadata, context=data)

    def status_favourite(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str,
        timeout_seconds: int = 15,
        status_id: str,
        enabled: bool = True,
    ) -> StatusCreateResult:
        action = "favourite" if enabled else "unfavourite"
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/statuses/{status_id}/{action}",
            method="POST",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=True)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(StatusInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=True)
        return StatusCreateResult(**metadata, status=data)

    def status_reblog(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str,
        timeout_seconds: int = 15,
        status_id: str,
        enabled: bool = True,
    ) -> StatusCreateResult:
        action = "reblog" if enabled else "unreblog"
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/statuses/{status_id}/{action}",
            method="POST",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=True)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(StatusInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=True)
        return StatusCreateResult(**metadata, status=data)

    def account_follow(
        self,
        *,
        source: str,
        instance_url: str,
        credential_file: str,
        timeout_seconds: int = 15,
        account_id: str,
        enabled: bool = True,
    ) -> AccountFollowResult:
        action = "follow" if enabled else "unfollow"
        instance_url = instance_url.rstrip("/")
        cfg = dict(
            source=source,
            instance_url=instance_url,
            credential_file=credential_file,
            timeout_seconds=timeout_seconds,
            path=f"/api/v1/accounts/{account_id}/{action}",
            method="POST",
            body=None,
            idempotency_key=None,
        )
        result = self._backend.execute(source, ["python3", "-c", _REQUEST_SCRIPT, json.dumps(cfg)])
        metadata = dict(
            source=source,
            instance_url=instance_url,
            successful=False,
            http_status=None,
            error=None,
            outcome_unknown=False,
        )
        data = None
        if result.exit_code != 0:
            metadata.update(error="execution_error", outcome_unknown=True)
        else:
            try:
                response = json.loads(result.stdout)
                metadata.update(
                    http_status=response["http_status"],
                    error=response["error"],
                    outcome_unknown=response["outcome_unknown"],
                )
                if metadata["error"] is None:
                    if (
                        not isinstance(metadata["http_status"], int)
                        or not 200 <= metadata["http_status"] < 300
                    ):
                        raise ValueError("missing successful HTTP status")
                    data = TypeAdapter(RelationshipInfo).validate_python(response["data"])
                    metadata["successful"] = True
            except (ValueError, KeyError, TypeError, ValidationError):
                metadata.update(error="invalid_response", outcome_unknown=True)
        return AccountFollowResult(**metadata, relationship=data)
