FROM python:3.12-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
# CPU by default. For an NVIDIA GPU build with --build-arg ORT="onnxruntime-gpu[cuda,cudnn]",
# which brings the CUDA and cuDNN libraries as pip packages; the host only needs the driver.
ARG ORT=onnxruntime
ENV PIP_INDEX_URL=${PIP_INDEX_URL} PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
# rapidocr pulls opencv-python, which needs libGL; the headless build does not.
RUN pip install rapidocr "${ORT}" \
 && pip uninstall -y opencv-python \
 && pip install opencv-python-headless
# Download the PP-OCR models at build time so the container starts offline.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"
WORKDIR /app
COPY app.py receipt.py ./
EXPOSE 18086
CMD ["python", "app.py"]
