FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "transformers==4.46.3" "peft==0.13.2" "accelerate==1.1.1" "bitsandbytes==0.44.1" "datasets==3.1.0" "sentencepiece" "protobuf"
RUN git clone --depth 1 --branch b4999 https://github.com/ggml-org/llama.cpp /opt/llama.cpp \
 && pip install --no-cache-dir /opt/llama.cpp/gguf-py
WORKDIR /work
