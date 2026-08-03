# sidecar/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY sidecar_main.py /app/sidecar_main.py

# Stdlib only (json, urllib) - no pip install needed, keeps the image
# demo-minimal and the build fast.
CMD ["python", "sidecar_main.py"]
