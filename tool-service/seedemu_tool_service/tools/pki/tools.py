"""PKI-domain tool implementations."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.pki.models import CertificateInspectionResult


class PKITools:
    """Bound-method tools for PKI inspection and operations."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend

    def inspect_certificate_file(
        self,
        source: str,
        path: str,
    ) -> CertificateInspectionResult:
        """Inspect an X.509 certificate file inside an emulated node."""

        command = [
            "openssl",
            "x509",
            "-in",
            path,
            "-noout",
            "-subject",
            "-issuer",
            "-serial",
            "-dates",
            "-fingerprint",
            "-sha256",
        ]
        result = self._backend.execute(source, command)
        return CertificateInspectionResult(
            source=source,
            path=path,
            successful=result.exit_code == 0,
            details=result.stdout,
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
