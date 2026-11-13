FROM python:3.12-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
# rapidocr pulls opencv-python, which needs libGL; the headless build does not.
RUN pip install rapidocr onnxruntime \
 && pip uninstall -y opencv-python \
 && pip install opencv-python-headless
# Download the PP-OCR models at build time so the container starts offline.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"
WORKDIR /app
COPY app.py receipt.py ./
EXPOSE 18086
CMD ["python", "app.py"]
