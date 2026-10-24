"""读取 DNS 托管模板。 / Load DNS hosting templates."""
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parent / 'files_dns'
DnsFileTemplates = {path.name: path.read_text(encoding='utf-8')
                    for path in sorted(_TEMPLATE_DIR.iterdir()) if path.is_file()}
