#!/bin/bash
set -e
cd "$(dirname "$0")"
RUN="docker run --rm --gpus all --shm-size=4g --user $(id -u):$(id -g) -e HOME=/tmp -e HF_HOME=/work/data/hf -v $PWD:/work bhs-llm-lora"

if [ ! -f data/models/qwen2.5-3b-instruct/config.json ]; then
  $RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-3B-Instruct', local_dir='/work/data/models/qwen2.5-3b-instruct', allow_patterns=['*.json', '*.safetensors', '*.txt', 'merges.txt'])"
fi

curl -s localhost:11434/api/generate -d '{"model":"qwen2.5vl:3b","keep_alive":0}' >/dev/null || true
curl -s localhost:11434/api/generate -d '{"model":"qwen2.5:3b","keep_alive":0}' >/dev/null || true

$RUN python /work/train_llm_lora.py
$RUN python /work/merge_llm.py
$RUN python /opt/llama.cpp/convert_hf_to_gguf.py /work/data/out/llm/merged --outtype f16 --outfile /work/data/out/llm/bhs-designer-f16.gguf
rm -rf data/out/llm/merged

docker cp data/out/llm/bhs-designer-f16.gguf ollama-bhs:/root/.ollama/bhs-designer-f16.gguf
docker exec ollama-bhs sh -c '/usr/lib/ollama/llama-quantize /root/.ollama/bhs-designer-f16.gguf /root/.ollama/bhs-designer-q4.gguf Q4_K_M \
  && rm /root/.ollama/bhs-designer-f16.gguf \
  && ollama show qwen2.5:3b --modelfile | grep -v "^FROM" > /root/.ollama/Modelfile.bhs \
  && sed -i "1i FROM /root/.ollama/bhs-designer-q4.gguf" /root/.ollama/Modelfile.bhs \
  && ollama create bhs-designer -f /root/.ollama/Modelfile.bhs \
  && rm /root/.ollama/bhs-designer-q4.gguf'
echo "Готово. Чтобы сайт использовал дообученную модель: OLLAMA_MODEL=bhs-designer ./start.sh"
