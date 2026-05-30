"""新闻情感标注 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="新闻情感标注 — 对新闻文章进行情感/事件类型分类"
    )
    parser.add_argument("--limit", type=int, default=200, help="每次标注上限")
    parser.add_argument("--no-save", action="store_true", help="不持久化结果")
    parser.add_argument("--print-context", action="store_true", help="输出最新标注摘要")
    return parser


def main():
    args = build_parser().parse_args()

    from logic_layer.news_sentiment.service import NewsSentimentService

    service = NewsSentimentService()
    service.init_storage()

    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
            return

        result = service.run_labeling(limit=args.limit, save=not args.no_save)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
