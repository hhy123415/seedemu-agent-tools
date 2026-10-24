"""读取 Registry 的 SQL、PHP、Shell 和 Nginx 模板文件，统一组织为按文件名索引的模板字典。

Load SQL, PHP, shell, and Nginx templates into a dictionary keyed by filename.
"""
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parent / 'files_registry'


def get_file_content(filename):
    """以 UTF-8 读取相对于模板目录的文件。 / Read a file relative to the template directory as UTF-8."""
    return (_TEMPLATE_DIR / filename).read_text(encoding='utf-8')


RegistryFileTemplates = {
    'publish-registry.php': get_file_content('publish-registry.php'),
    'create-epp-registrar.php': get_file_content('create-epp-registrar.php'),
    'database.sql': get_file_content('database.sql'),
    'initialize-tlds.php': get_file_content('initialize-tlds.php'),
    'database.sh': get_file_content('database.sh'),
    'configure-web.php': get_file_content('configure-web.php'),
    'registry.conf': get_file_content('registry.conf'),
    'web.sh': get_file_content('web.sh'),
    'configure-component.php': get_file_content('configure-component.php'),
}
