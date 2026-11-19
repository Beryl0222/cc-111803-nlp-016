import argparse
import json
from pathlib import Path

from .desk import assess


def load_case(case_path, registry_path, threads_path=None):
    case = json.loads(Path(case_path).read_text(encoding='utf-8'))
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    threads = json.loads(Path(threads_path).read_text(encoding='utf-8')) if threads_path else None
    return assess(case, registry, threads)


def main():
    parser = argparse.ArgumentParser(description='核对内容申诉、归属还原与限制执行情况')
    parser.add_argument('--case', type=Path, default=Path('fixtures/work.json'))
    parser.add_argument('--registry', type=Path, default=Path('fixtures/business.json'))
    parser.add_argument('--threads', type=Path, default=Path('fixtures/threads.json'))
    args = parser.parse_args()
    try:
        result = load_case(args.case, args.registry, args.threads)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
