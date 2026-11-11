#!/bin/sh
# 임베딩 서버(TEI) 시작 스크립트.
#
# TEI에는 입력 길이 한도를 낮추는 옵션이 없고, 모델 설정의 한도(이 모델은 8192토큰)를 그대로 쓴다.
# 그 한도로는 준비 단계(warm-up)에서 메모리를 6GB 넘게 써 작은 장비에서 죽는다.
# 그래서 모델 파일을 볼륨에 받아 두고 `sentence_bert_config.json`의 `max_seq_length`만
# EMBEDDING_MAX_TOKENS로 바꾼 폴더를 TEI에 넘긴다. 한도를 넘는 입력은 TEI가 앞부분만 인코딩한다.
set -eu

MODEL="${EMBEDDING_MODEL:?EMBEDDING_MODEL이 필요합니다}"
MAX_TOKENS="${EMBEDDING_MAX_TOKENS:?EMBEDDING_MAX_TOKENS가 필요합니다}"
DIR="/data/local/$(echo "$MODEL" | tr '/' '_')"
BASE="https://huggingface.co/$MODEL/resolve/main"

mkdir -p "$DIR/1_Pooling"
for file in config.json tokenizer.json tokenizer_config.json modules.json \
    config_sentence_transformers.json 1_Pooling/config.json \
    sentence_bert_config.json.orig model.safetensors; do
    if [ ! -s "$DIR/$file" ]; then
        echo "내려받기: $MODEL/${file%.orig}"
        curl -fL --retry 3 -o "$DIR/$file.part" "$BASE/${file%.orig}"
        mv "$DIR/$file.part" "$DIR/$file"
    fi
done

sed -E "s/\"max_seq_length\": *[0-9]+/\"max_seq_length\": $MAX_TOKENS/" \
    "$DIR/sentence_bert_config.json.orig" > "$DIR/sentence_bert_config.json"
grep -q "\"max_seq_length\": $MAX_TOKENS" "$DIR/sentence_bert_config.json" || {
    echo "sentence_bert_config.json에서 max_seq_length를 찾지 못했습니다" >&2
    exit 1
}

exec text-embeddings-router --model-id "$DIR" --served-model-name "$MODEL" "$@"
