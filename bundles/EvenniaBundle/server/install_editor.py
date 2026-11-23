"""Register the packaged editor without replacing the persistent game's URL routes."""
from pathlib import Path
import shutil
import sys

game = Path(sys.argv[1])
shutil.copytree(Path(__file__).parent / 'topology_editor', game / 'topology_editor',
                dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
urls = game / 'web/urls.py'
marker = '# EmuVista hierarchical topology editor'
content = urls.read_text()
if marker not in content:
    with urls.open('a') as stream:
        stream.write('\n\n' + marker + '\n'
                     'from topology_editor.urls import urlpatterns as topology_editor_patterns\n'
                     'urlpatterns = topology_editor_patterns + urlpatterns\n')

settings = game / 'server/conf/settings.py'
marker = '# EmuVista bundled map startup hook'
if marker not in settings.read_text():
    with settings.open('a') as stream:
        stream.write('\n\n' + marker + '\n'
                     'if isinstance(AT_SERVER_STARTSTOP_MODULE, str):\n'
                     '    AT_SERVER_STARTSTOP_MODULE = [AT_SERVER_STARTSTOP_MODULE]\n'
                     'AT_SERVER_STARTSTOP_MODULE = list(AT_SERVER_STARTSTOP_MODULE or [])\n'
                     'if "topology_editor.bootstrap" not in AT_SERVER_STARTSTOP_MODULE:\n'
                     '    AT_SERVER_STARTSTOP_MODULE.append("topology_editor.bootstrap")\n')
