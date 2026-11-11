#!/bin/sh
# 임베딩 서버(TEI) 시작 스크립트.
#
# TEI_MODEL_ID      내려받아 띄울 모델 저장소. ONNX 변환본(`onnx/model.onnx`)이어야 하고
#                   ONNX(ort) 실행기로 뜬다. ONNX가 없으면 멈춘다. Candle 실행기는 같은 장비에서
#                   적재가 1.7배쯤 느려서 쓰지 않는다. 다른 모델은 먼저 ONNX로 변환해 올린다.
# EMBEDDING_MODEL   서버가 알리는 모델 이름(--served-model-name). 앱이 벡터와 함께 저장하는 이름이다.
#                   같은 가중치의 변환본이면 원본 이름을 그대로 둔다.
# EMBEDDING_MAX_TOKENS  입력 길이 한도.
#
# TEI에는 입력 길이 한도를 낮추는 옵션이 없고, 모델 설정의 한도(이 모델은 8192토큰)를 그대로 쓴다.
# 그 한도로는 준비 단계(warm-up)에서 메모리를 6GB 넘게 써 작은 장비에서 죽는다.
# 그래서 모델 파일을 볼륨에 받아 두고 `sentence_bert_config.json`의 `max_seq_length`만
# EMBEDDING_MAX_TOKENS로 바꾼 폴더를 TEI에 넘긴다. 한도를 넘는 입력은 TEI가 앞부분만 인코딩한다.
set -eu

SOURCE="${TEI_MODEL_ID:?TEI_MODEL_ID가 필요합니다}"
SERVED="${EMBEDDING_MODEL:?EMBEDDING_MODEL이 필요합니다}"
MAX_TOKENS="${EMBEDDING_MAX_TOKENS:?EMBEDDING_MAX_TOKENS가 필요합니다}"
DIR="/data/local/$(echo "$SOURCE" | tr '/' '_')"
BASE="https://huggingface.co/$SOURCE/resolve/main"

fetch() {  # fetch <저장소 경로> [저장 이름]
    target="$DIR/${2:-$1}"
    [ -s "$target" ] && return 0
    echo "내려받기: $SOURCE/$1"
    mkdir -p "$(dirname "$target")"
    curl -fL --retry 3 -o "$target.part" "$BASE/$1"
    mv "$target.part" "$target"
}

# ONNX 변환본만 쓴다. 다른 파일을 받기 전에 먼저 확인한다.
if [ ! -s "$DIR/onnx/model.onnx" ] && ! curl -sfIL -o /dev/null "$BASE/onnx/model.onnx"; then
    echo "ONNX 변환본이 필요합니다: $SOURCE 에 onnx/model.onnx가 없습니다." >&2
    echo "TEI_MODEL_ID에 ONNX로 변환한 저장소를 지정하세요." >&2
    exit 1
fi

for file in config.json tokenizer.json tokenizer_config.json modules.json \
    config_sentence_transformers.json 1_Pooling/config.json; do
    fetch "$file"
done
fetch sentence_bert_config.json sentence_bert_config.json.orig

# 가중치. 2GB가 넘는 가중치는 `model.onnx_data`에 따로 있다.
fetch onnx/model.onnx
if [ -s "$DIR/onnx/model.onnx_data" ] || curl -sfIL -o /dev/null "$BASE/onnx/model.onnx_data"; then
    fetch onnx/model.onnx_data
fi

sed -E "s/\"max_seq_length\": *[0-9]+/\"max_seq_length\": $MAX_TOKENS/" \
    "$DIR/sentence_bert_config.json.orig" > "$DIR/sentence_bert_config.json"
grep -q "\"max_seq_length\": $MAX_TOKENS" "$DIR/sentence_bert_config.json" || {
    echo "sentence_bert_config.json에서 max_seq_length를 찾지 못했습니다" >&2
    exit 1
}

exec text-embeddings-router --model-id "$DIR" --served-model-name "$SERVED" "$@"
