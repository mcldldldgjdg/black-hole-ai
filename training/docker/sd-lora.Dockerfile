FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v0.8.7 https://github.com/kohya-ss/sd-scripts /opt/sd-scripts
WORKDIR /opt/sd-scripts
RUN pip install --no-cache-dir -r requirements.txt
WORKDIR /work
