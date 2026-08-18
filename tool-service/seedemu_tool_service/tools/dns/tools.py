"""DNS-domain tool implementations."""

import base64
import re
from ipaddress import ip_address

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.dns.models import (
    DNSCompareDifference,
    DNSCompareResult,
    DNSCompareServerResult,
    DNSLookupDetails,
    DNSLookupResult,
    DNSRecord,
    DNSRecordType,
    DNSReverseLookupResult,
    DNSTraceResult,
    DNSTraceStep,
    DNSUpdateOperation,
    DNSUpdateResult,
)

_HEADER_PATTERN = re.compile(r"status:\s*([A-Z]+)")
_FLAGS_PATTERN = re.compile(r";; flags:\s*([^;]+);")
_QUERY_TIME_PATTERN = re.compile(r";; Query time:\s*(\d+)\s*msec")
_SERVER_PATTERN = re.compile(r";; SERVER:\s*([^\s]+)")
_TIMEOUT_PATTERN = re.compile(
    r"timed?\s*out|no servers could be reached|communications error",
    re.IGNORECASE,
)
_TRACE_RECEIVED_PATTERN = re.compile(
    r";; Received\s+\d+\s+bytes\s+from\s+(.+?)\s+in\s+(\d+)\s+ms"
)


class DNSTools:
    """Bound-method tools for DNS inspection and operations."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend

    @staticmethod
    def _parse_record_sections(output: str) -> dict[str, list[DNSRecord]]:
        """Parse resource records from the answer, authority, and additional sections."""

        sections: dict[str, list[DNSRecord]] = {
            "ANSWER": [],
            "AUTHORITY": [],
            "ADDITIONAL": [],
        }
        current_section: str | None = None

        for line in output.splitlines():
            section_match = re.fullmatch(r";; (ANSWER|AUTHORITY|ADDITIONAL) SECTION:", line)
            if section_match:
                current_section = section_match.group(1)
                continue
            if not line.strip():
                current_section = None
                continue
            if current_section is None or line.startswith(";"):
                continue

            fields = line.split(None, 4)
            if len(fields) != 5:
                continue
            try:
                ttl = int(fields[1])
            except ValueError:
                continue

            sections[current_section].append(
                DNSRecord(
                    name=fields[0],
                    ttl=ttl,
                    record_class=fields[2],
                    record_type=fields[3],
                    value=fields[4],
                )
            )

        return sections

    @staticmethod
    def _parse_trace_steps(output: str) -> list[DNSTraceStep]:
        """Split dig +trace output into ordered DNS responses."""

        steps: list[DNSTraceStep] = []
        records: list[DNSRecord] = []

        for line in output.splitlines():
            received_match = _TRACE_RECEIVED_PATTERN.fullmatch(line.strip())
            if received_match:
                steps.append(
                    DNSTraceStep(
                        records=records,
                        responding_server=received_match.group(1),
                        response_time_ms=int(received_match.group(2)),
                    )
                )
                records = []
                continue

            if not line.strip() or line.startswith(";"):
                continue
            fields = line.split(None, 4)
            if len(fields) != 5:
                continue
            try:
                ttl = int(fields[1])
            except ValueError:
                continue
            records.append(
                DNSRecord(
                    name=fields[0],
                    ttl=ttl,
                    record_class=fields[2],
                    record_type=fields[3],
                    value=fields[4],
                )
            )

        # Preserve useful records even when dig terminates before printing a
        # final "Received" line.
        if records:
            steps.append(DNSTraceStep(records=records))

        return steps

    @staticmethod
    def _canonical_name(name: str, records: list[DNSRecord]) -> str | None:
        """Follow an answer-section CNAME chain and return its final target."""

        aliases = {
            record.name.rstrip(".").lower(): record.value.rstrip(".")
            for record in records
            if record.record_type == "CNAME"
        }
        current = name.rstrip(".")
        visited: set[str] = set()
        while current.lower() in aliases and current.lower() not in visited:
            visited.add(current.lower())
            current = aliases[current.lower()]
        return current if visited else None

    @staticmethod
    def _response_status(stdout: str, stderr: str) -> str | None:
        """Extract a DNS response code, including dig's timeout-only output."""

        header_match = _HEADER_PATTERN.search(stdout)
        if header_match:
            return header_match.group(1)
        if _TIMEOUT_PATTERN.search(f"{stdout}\n{stderr}"):
            return "timeout"
        return None

    def lookup(
        self,
        source: str,
        name: str,
        record_type: DNSRecordType = "A",
        include_details: bool = False,
        include_raw_output: bool = False,
        server: str | None = None,
        timeout_seconds: int = 3,
    ) -> DNSLookupResult:
        """Resolve DNS records from an emulated source node using dig."""

        command = ["dig", f"+time={timeout_seconds}", "+tries=1"]
        if server is not None:
            command.append(f"@{server}")
        command.extend([name, record_type])

        result = self._backend.execute(source, command)
        flags_match = _FLAGS_PATTERN.search(result.stdout)
        flags = flags_match.group(1).split() if flags_match else []
        sections = self._parse_record_sections(result.stdout)
        answer_records = sections["ANSWER"]
        response_status = self._response_status(result.stdout, result.stderr)
        query_time_match = _QUERY_TIME_PATTERN.search(result.stdout)
        server_match = _SERVER_PATTERN.search(result.stdout)
        return DNSLookupResult(
            command_successful=result.exit_code == 0,
            response_status=response_status,
            authoritative="aa" in flags,
            truncated="tc" in flags,
            canonical_name=self._canonical_name(name, answer_records),
            answers=[
                record.value
                for record in answer_records
                if record.record_type == record_type
            ],
            exit_code=result.exit_code,
            stderr=result.stderr,
            details=DNSLookupDetails(
                flags=flags,
                answer_records=answer_records,
                authority_records=sections["AUTHORITY"],
                additional_records=sections["ADDITIONAL"],
                recursion_available="ra" in flags,
                authenticated_data="ad" in flags,
                query_time_ms=(
                    int(query_time_match.group(1)) if query_time_match else None
                ),
                responding_server=server_match.group(1) if server_match else None,
            )
            if include_details
            else None,
            raw_output=result.stdout if include_raw_output else None,
        )

    def reverse_lookup(
        self,
        source: str,
        address: str,
        server: str | None = None,
        timeout_seconds: int = 3,
    ) -> DNSReverseLookupResult:
        """Resolve PTR records for a strictly validated IPv4 or IPv6 address."""

        parsed_address = ip_address(address)
        command = ["dig", f"+time={timeout_seconds}", "+tries=1"]
        if server is not None:
            command.append(f"@{server}")
        command.extend(["-x", str(parsed_address)])

        result = self._backend.execute(source, command)
        response_status = self._response_status(result.stdout, result.stderr)
        records = self._parse_record_sections(result.stdout)["ANSWER"]
        return DNSReverseLookupResult(
            ptr_names=[
                record.value for record in records if record.record_type == "PTR"
            ],
            reverse_name=parsed_address.reverse_pointer,
            response_status=response_status,
            records=records,
            successful=result.exit_code == 0 and response_status == "NOERROR",
        )

    def compare(
        self,
        source: str,
        name: str,
        servers: list[str | None],
        record_type: DNSRecordType = "A",
        timeout_seconds: int = 3,
    ) -> DNSCompareResult:
        """Compare the same DNS query across resolvers from one source node."""

        server_results: list[DNSCompareServerResult] = []
        answer_sets: list[set[str]] = []
        statuses: list[str | None] = []

        for server in servers:
            lookup_result = self.lookup(
                source=source,
                name=name,
                record_type=record_type,
                include_details=True,
                server=server,
                timeout_seconds=timeout_seconds,
            )
            details = lookup_result.details
            answer_records = (
                [
                    record
                    for record in details.answer_records
                    if record.record_type == record_type
                ]
                if details is not None
                else []
            )
            timed_out = lookup_result.response_status == "timeout"
            server_results.append(
                DNSCompareServerResult(
                    server=server,
                    command_successful=lookup_result.command_successful,
                    response_status=lookup_result.response_status,
                    answers=lookup_result.answers,
                    answer_records=answer_records,
                    ttls=[record.ttl for record in answer_records],
                    latency_ms=details.query_time_ms if details is not None else None,
                    timed_out=timed_out,
                )
            )
            answer_sets.append(set(lookup_result.answers))
            statuses.append(lookup_result.response_status)

        all_answers = set().union(*answer_sets)
        common_answers = set.intersection(*answer_sets)
        differences = [
            DNSCompareDifference(
                answer=answer,
                present_on=[
                    server
                    for server, answers in zip(servers, answer_sets, strict=True)
                    if answer in answers
                ],
                missing_from=[
                    server
                    for server, answers in zip(servers, answer_sets, strict=True)
                    if answer not in answers
                ],
            )
            for answer in sorted(all_answers)
            if any(answer not in answers for answers in answer_sets)
        ]
        ttls = [ttl for result in server_results for ttl in result.ttls]

        return DNSCompareResult(
            source=source,
            name=name,
            record_type=record_type,
            results=server_results,
            answers_consistent=(
                len(set(statuses)) == 1
                and all(answers == answer_sets[0] for answers in answer_sets[1:])
            ),
            common_answers=sorted(common_answers),
            differences=differences,
            min_ttl=min(ttls) if ttls else None,
            max_ttl=max(ttls) if ttls else None,
            timed_out_servers=[result.server for result in server_results if result.timed_out],
        )

    def trace(
        self,
        source: str,
        name: str,
        record_type: DNSRecordType = "A",
        server: str | None = None,
        timeout_seconds: int = 3,
    ) -> DNSTraceResult:
        """Follow DNS delegations from an emulated source node using dig +trace."""

        command = ["dig", "+trace", f"+time={timeout_seconds}", "+tries=1"]
        if server is not None:
            command.append(f"@{server}")
        command.extend([name, record_type])

        result = self._backend.execute(source, command)
        steps = self._parse_trace_steps(result.stdout)
        final_answers = (
            [
                record
                for record in steps[-1].records
                if record.record_type == record_type
            ]
            if steps
            else []
        )

        return DNSTraceResult(
            source=source,
            name=name,
            record_type=record_type,
            server=server,
            successful=result.exit_code == 0,
            exit_code=result.exit_code,
            stderr=result.stderr,
            steps=steps,
            final_answers=final_answers,
            raw_output=result.stdout,
        )

    def update(
        self,
        source: str,
        zone: str,
        name: str,
        record_type: DNSRecordType = "A",
        operation: DNSUpdateOperation = "replace",
        ttl: int = 300,
        value: str | None = None,
    ) -> DNSUpdateResult:
        """Replace or delete an RRset, letting nsupdate discover the primary server."""

        lines = [
            f"zone {zone.rstrip('.')}.",
            f"update delete {name} {record_type}",
        ]
        if operation == "replace":
            lines.append(f"update add {name} {ttl} {record_type} {value}")
        lines.extend(["send", ""])
        update_script = "\n".join(lines)

        # Docker's high-level exec API does not attach stdin here. Base64 keeps all
        # agent-provided data out of shell syntax; the fixed shell snippet only decodes it.
        encoded_script = base64.b64encode(update_script.encode()).decode("ascii")
        command = [
            "sh",
            "-c",
            'printf %s "$1" | base64 -d | nsupdate',
            "sh",
            encoded_script,
        ]
        result = self._backend.execute(source, command)
        return DNSUpdateResult(
            source=source,
            zone=zone,
            name=name,
            record_type=record_type,
            operation=operation,
            ttl=ttl if operation == "replace" else None,
            value=value if operation == "replace" else None,
            successful=result.exit_code == 0,
            exit_code=result.exit_code,
            stderr=result.stderr,
        )

    def batch_lookup(self) -> None:
        """Resolve multiple DNS names and record types in one invocation."""

        raise NotImplementedError("dns.batch_lookup is a concept-only tool")

    def zone_transfer(self) -> None:
        """Transfer a DNS zone from an authoritative server using AXFR or IXFR."""

        raise NotImplementedError("dns.zone_transfer is a concept-only tool")

    def validate_dnssec(self) -> None:
        """Validate the DNSSEC chain of trust for a DNS query."""

        raise NotImplementedError("dns.validate_dnssec is a concept-only tool")

    def check_delegation(self) -> None:
        """Check DNS delegation consistency between parent and child zones."""

        raise NotImplementedError("dns.check_delegation is a concept-only tool")

    def observe_cache(self) -> None:
        """Observe DNS resolver cache behavior across repeated queries."""

        raise NotImplementedError("dns.observe_cache is a concept-only tool")

    def diagnose_resolver(self) -> None:
        """Inspect the capabilities and health of a DNS resolver."""

        raise NotImplementedError("dns.diagnose_resolver is a concept-only tool")

    def batch_update(self) -> None:
        """Apply multiple RFC 2136 DNS changes in one transaction."""

        raise NotImplementedError("dns.batch_update is a concept-only tool")
