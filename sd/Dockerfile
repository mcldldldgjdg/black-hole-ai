FROM ghcr.io/ai-dock/stable-diffusion-webui:latest

RUN umask 002 \
 && /opt/environments/python/webui/bin/pip install --no-cache-dir --no-deps "mediapipe==0.10.9" \
 && /opt/environments/python/webui/bin/pip install --no-cache-dir absl-py flatbuffers sounddevice \
 && /opt/environments/python/webui/bin/python -c "import mediapipe as mp, numpy, google.protobuf as pb; mp.solutions.drawing_utils; print('mediapipe', mp.__version__, 'numpy', numpy.__version__, 'protobuf', pb.__version__)"
