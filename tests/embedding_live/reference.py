"""임베딩 기준 문장과 기준 벡터. 실행 방식(TEI 버전, Candle·ONNX)을 바꿔도
같은 벡터가 나오는지 본다.

문장은 직접 쓴 것이다(YES24 표본이 아니다). 그래서 기준 벡터를 저장소에 둘 수 있다.
문서 5개는 길이를 섞었고 마지막 하나는 입력 한도(512토큰)를 넘는다. 질의 2개는 접두어 경로를 본다.

기준 벡터 다시 만들기(기준으로 삼을 서버를 띄운 상태에서):
  uv run python -m tests.embedding_live.reference --write
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from app.central.external.tei import TeiEmbedder
from app.core.config import get_settings

REFERENCE_FILE = Path(__file__).parent / "data" / "reference_vectors.json"

DOCUMENTS = (
    "구름 위의 고래\n김하늘 글\n그림책",
    "우리 동네 도서관에 가요\n박서준 글/이수아 그림\n어린이 사회\n"
    "토요일 아침, 지우는 할머니 손을 잡고 동네 작은도서관에 "
    "갑니다. 책을 고르고 빌리는 방법을 배우며 "
    "도서관이 모두의 공간이라는 것을 알게 됩니다.",
    "밤하늘 별자리 도감: 계절마다 찾는 별\n정우진 저\n자연과학\n"
    "봄, 여름, 가을, 겨울 밤하늘에서 쉽게 찾을 수 있는 별자리를 사진과 그림으로 소개한다. "
    "맨눈으로 보는 방법부터 쌍안경과 작은 망원경을 고르는 요령, 별자리에 얽힌 옛이야기까지 담았다. "
    "아이와 함께 처음 별을 보는 가족에게 알맞은 안내서다.",
    "마음이 지친 날의 산책\n최민영 지음\n에세이\n"
    "회사와 집을 오가던 저자가 퇴근길에 한 정거장 먼저 내려 "
    "걷기 시작하면서 생긴 작은 변화를 적었다. "
    "골목의 오래된 가게, 계절마다 바뀌는 가로수, 낯선 사람과 "
    "나눈 짧은 인사가 하루를 다르게 만든다. "
    "거창한 결심 없이도 마음을 돌보는 법을 조용히 건넨다. 책 "
    "곳곳에 저자가 직접 찍은 사진이 실려 있다.",
    "공룡 화석을 찾아서\n한도윤 글\n어린이 과학\n"
    + " ".join(
        f"{i}번째 장에서는 고생물학자들이 사막과 해안 절벽에서 "
        f"화석을 찾고 발굴하는 과정을 따라간다."
        for i in range(1, 61)
    ),
)
QUERIES = ("공룡을 좋아하는 아이에게 읽어 줄 책", "지친 마음을 달래 주는 가벼운 에세이")


async def encode(embedder: TeiEmbedder) -> dict[str, list[list[float]]]:
    return {
        "documents": await embedder.encode_documents(list(DOCUMENTS)),
        "queries": await embedder.encode_queries(list(QUERIES)),
    }


async def _write() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
    ) as http:
        embedder = TeiEmbedder(http, settings)
        await embedder.check()
        info = (await http.get("/info")).json()
        vectors = await encode(embedder)
    REFERENCE_FILE.parent.mkdir(exist_ok=True)
    document = {
        "model_name": embedder.name,
        "made_with": {"model_id": info["model_id"], "tei_version": info["version"]},
        "max_input_length": info["max_input_length"],
        **{kind: [[round(x, 7) for x in v] for v in vecs] for kind, vecs in vectors.items()},
    }
    REFERENCE_FILE.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"기준 벡터를 저장했습니다: {REFERENCE_FILE} ({info['model_id']}, TEI {info['version']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="임베딩 기준 벡터를 만든다")
    parser.add_argument("--write", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(_write())
