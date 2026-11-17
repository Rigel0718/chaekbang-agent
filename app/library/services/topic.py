"""제품 경로의 주제로 찾기. AI 사서의 소장 도서 검색 tool이 이 함수만 부른다.

- 낱말이 있으면 추천 실험의 기본 설정(`TopicSettings()`)으로 순위를 만들고 앞 10권을 낸다. 여기서
  순위 설정을 다시 고르지 않는다. 벡터 질의는 기본 설정대로 낱말을 이은 것이다. 이용자 문장은 받지
  않는다.
- 낱말이 없으면 키워드 없는 둘러보기(`search_collection`)다.
- 인코더가 없거나 인코딩이 실패하면(꺼짐, 시간 제한, 다른 모델, 쉬는 중) 키워드 순위만으로 내려간다.
  결과는 같은 낱말의 키워드 검색과 같은 책, 같은 순서다. 로그에는 실패 종류만 남긴다.
- 실패를 여기서 받는 이유: `find_by_topic`은 실험이 그대로 부르는 함수라, 실험 중의 인코딩 실패가
  조용히 키워드만으로 바뀌면 안 된다.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import Embedder, EmbeddingError, EmbeddingFailure
from app.library.recommendation.search import (
    SEARCH_LIMIT,
    Candidate,
    clean_keywords,
    get_candidates,
    search_collection,
)
from app.library.recommendation.topic import KEYWORD, TopicSettings, find_by_topic, keyword_ranking

logger = logging.getLogger(__name__)

# 대화 코드가 AI 사서 실행에 넘기는 실행 값의 이름: 질의 인코더(`Embedder | None`)
QUERY_ENCODER = "query_encoder"


@dataclass(frozen=True)
class TopicResult:
    candidates: list[Candidate]
    keyword_matched: bool  # 키워드 순위에 한 권이라도 있음(둘러보기도 참)
    vector_used: bool  # 벡터 순위를 썼음(내려가면 거짓)

    @property
    def keyword_missing(self) -> bool:
        """낱말이 맞는 책이 없어 벡터 순위의 책만 나왔다."""
        return self.vector_used and not self.keyword_matched and bool(self.candidates)


async def _ordered(session: AsyncSession, library_id: int, ids: Sequence[int]) -> list[Candidate]:
    found = await get_candidates(session, library_id, ids)
    return [found[i] for i in ids if i in found]


async def search_by_topic(
    session: AsyncSession,
    library_id: int,
    keywords: Sequence[str],
    *,
    encoder: Embedder | None,
    within: Select | None = None,
) -> TopicResult:
    if not clean_keywords(keywords):
        browse = await search_collection(session, library_id, keywords, within=within)
        return TopicResult(browse, keyword_matched=True, vector_used=False)
    if encoder is not None:
        try:
            ranked = await find_by_topic(
                session,
                encoder,
                library_id=library_id,
                text=" ".join(keywords),
                keywords=keywords,
                within=within,
                settings=replace(TopicSettings(), limit=SEARCH_LIMIT),
            )
        except EmbeddingError as exc:
            level = logging.DEBUG if exc.failure is EmbeddingFailure.PAUSED else logging.WARNING
            logger.log(level, "topic search without vectors: %s", exc.failure.value)
        else:
            ids = [item.library_book_id for item in ranked]
            matched = any(KEYWORD in item.ranks for item in ranked)
            return TopicResult(await _ordered(session, library_id, ids), matched, True)
    ids = await keyword_ranking(session, library_id, keywords, within=within, depth=SEARCH_LIMIT)
    return TopicResult(await _ordered(session, library_id, ids), bool(ids), vector_used=False)
