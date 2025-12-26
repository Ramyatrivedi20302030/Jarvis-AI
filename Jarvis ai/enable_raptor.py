import json
import sys
from pathlib import Path

CONFIG_FILE = 'config.json'

def enable_raptor(enable=True):
    p = Path(CONFIG_FILE)
    if not p.exists():
        print('config.json not found in project root')
        sys.exit(1)
    config = json.loads(p.read_text(encoding='utf-8'))
    config['enable_raptor_mini_for_all_clients'] = bool(enable)
    p.write_text(json.dumps(config, indent=2), encoding='utf-8')

if __name__ == '__main__':
    enable_raptor(True)
    print('Raptor mini preview enabled in config.json')
