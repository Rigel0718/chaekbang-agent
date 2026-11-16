"""라벨 검수 화면. 초안(Claude)을 사람이 브라우저에서 확인하거나 고친다. 이 PC에서만 연다.

    uv run python -m evals.recommendation.review topic        # http://127.0.0.1:8765

- 질의마다 초안이 1 이상인 책을 소개 전문과 함께, 0인 책을 접은 목록으로 보여 준다.
- 0·1·2를 누르면 바로 라벨 파일에 쓰고 단 쪽이 `user`가 된다. "보이는 책 모두 확인"은 그 질의의
  1 이상인 책을 지금 값 그대로 `user`로 바꾼다.
- 책 소개가 YES24 값이라 페이지를 파일로 남기지 않고, 127.0.0.1에서만 받는다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from evals.recommendation.draft import SETS, load_items
from evals.recommendation.label import Card
from evals.recommendation.labels import BEFORE, GRADES, USER, Labels, labels_file
from evals.recommendation.sample import SAMPLE_SIZES, pick_sample, sample_line

HOST = "127.0.0.1"
PORT = 8765


class ReviewError(ValueError):
    pass


def review_label(labels: Labels, item_id: str, key: str, grade: int) -> None:
    """사람이 확인하거나 고친 라벨 하나를 쓴다. 단계는 그대로, 단 쪽은 `user`."""
    if grade not in GRADES:
        raise ReviewError(f"라벨은 0·1·2다: {grade}")
    labels.put(item_id, key, grade, labels.stage(item_id, key) or BEFORE, USER)


def _book(labels: Labels, item_id: str, card: Card) -> dict:
    return {
        "key": card.key,
        "title": card.title,
        "author": card.author,
        "category": card.category,
        "shelf": card.shelf,
        "description": card.description,
        "grade": labels.grade(item_id, card.key),
        "by": labels.labeler(item_id, card.key),
        "stage": labels.stage(item_id, card.key),
    }


def page_data(
    labels: Labels,
    items: Sequence[tuple[Any, Sequence[Card]]],
    sample: Sequence[tuple[str, str]] | None = None,
) -> list[dict]:
    """페이지에 넣을 값: 항목(질의, 또는 기준 책들)과 후보 카드, 지금 라벨과 단 쪽.

    sample((항목 id, 책 키) 목록)이 있으면 그 책만 넣고 항목에 표본 표시를 한다. 표본에 든 책이
    없는 항목은 빠진다.
    """
    wanted = None if sample is None else set(sample)
    data = []
    for query, cards in items:
        books = [
            _book(labels, query.id, card)
            for card in cards
            if wanted is None or (query.id, card.key) in wanted
        ]
        if wanted is not None and not books:
            continue
        data.append(
            {
                "id": query.id,
                "text": query.text,
                "children": query.children,
                "sample": wanted is not None,
                "bases": [
                    {
                        "title": base.title,
                        "author": base.author,
                        "category": base.category,
                        "description": base.description,
                    }
                    for base in getattr(query, "bases", ())
                ],
                "books": books,
            }
        )
    return data


PAGE_FILE = Path(__file__).with_name("review.html")


def render_page(data: Sequence[dict]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return PAGE_FILE.read_text(encoding="utf-8").replace("__DATA__", payload)


def make_handler(
    labels: Labels,
    items: Sequence[tuple[Any, Sequence[Card]]],
    sample: Sequence[tuple[str, str]] | None = None,
) -> type[BaseHTTPRequestHandler]:
    keys = {query.id: {card.key for card in cards} for query, cards in items}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: HTTPStatus, body: str, kind: str = "text/plain") -> None:
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path != "/":
                self._send(HTTPStatus.NOT_FOUND, "없는 주소")
                return
            self._send(HTTPStatus.OK, render_page(page_data(labels, items, sample)), "text/html")

        def do_POST(self) -> None:
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                item_id, key, grade = body["item"], body["key"], body["grade"]
                if self.path != "/label" or key not in keys.get(item_id, ()):
                    raise ReviewError("후보가 아닌 책")
                review_label(labels, item_id, key, grade)
            except (ReviewError, KeyError, TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send(HTTPStatus.OK, "ok")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.review")
    parser.add_argument("set", choices=SETS)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument(
        "--sample", action="store_true", help="고정 표본만 본다(라벨은 Claude가 달고 사람은 표본만)"
    )
    args = parser.parse_args()
    labels = Labels(labels_file(args.set))
    extra = {item_id: list(entries) for item_id, entries in labels.items.items()}
    items = asyncio.run(load_items(get_settings().database_url, args.set, None, extra))
    if not items:
        print("실험 기관이 없습니다. `uv run python scripts/seed_experiment.py`")
        return 1
    sample = pick_sample(labels, SAMPLE_SIZES[args.set]) if args.sample else None
    if sample is not None:
        print(f"표본 {len(sample)}건(등급별 고르게, 해시 순서). 모두 누르면 끝난다.")
    # 한 번에 한 요청만 처리해 라벨 파일 쓰기가 겹치지 않게 한다
    server = HTTPServer((HOST, args.port), make_handler(labels, items, sample))
    print(f"검수 화면: http://{HOST}:{args.port}  (끝내려면 Ctrl+C)\n라벨 파일: {labels.path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n단 쪽별 라벨 수: {labels.by_counts()}")
        if sample is not None:
            print(sample_line(labels, SAMPLE_SIZES[args.set]))
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
