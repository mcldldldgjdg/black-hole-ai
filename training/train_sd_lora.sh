#!/bin/bash
set -e
cd "$(dirname "$0")"
EPOCHS="${EPOCHS:-2}"

docker run --rm --gpus all --shm-size=4g --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD/data:/work/data" \
  bhs-sd-lora \
  accelerate launch --num_cpu_threads_per_process 2 --mixed_precision fp16 /opt/sd-scripts/train_network.py \
    --pretrained_model_name_or_path=/work/data/models/v1-5-pruned-emaonly.safetensors \
    --train_data_dir=/work/data/sd/img \
    --output_dir=/work/data/out/sd \
    --output_name=bhs_interior \
    --save_model_as=safetensors \
    --caption_extension=.txt \
    --resolution=512,512 --enable_bucket --min_bucket_reso=320 --max_bucket_reso=768 --bucket_reso_steps=64 \
    --network_module=networks.lora --network_dim=32 --network_alpha=16 \
    --optimizer_type=AdamW --learning_rate=1e-4 --unet_lr=1e-4 --text_encoder_lr=5e-5 \
    --lr_scheduler=cosine_with_restarts --lr_warmup_steps=100 \
    --train_batch_size=2 --max_train_epochs="$EPOCHS" --save_every_n_epochs=2 \
    --mixed_precision=fp16 --save_precision=fp16 \
    --gradient_checkpointing --sdpa --cache_latents \
    --max_data_loader_n_workers=2 --seed=42 \
    --logging_dir=/work/data/out/sd/logs
