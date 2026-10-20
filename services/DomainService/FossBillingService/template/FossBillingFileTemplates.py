"""按名称读取 FOSSBilling 模板。 / Load FOSSBilling templates by name."""
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parent / 'files_fossbilling'
FossBillingFileTemplates = {path.name: path.read_text(encoding='utf-8')
                            for path in sorted(_TEMPLATE_DIR.iterdir()) if path.is_file()}
