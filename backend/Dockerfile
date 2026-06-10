FROM python:3.12-slim

WORKDIR /app

# Install system libraries required by pymupdf (PDF/SVG conversion)
# libmupdf-dev provides the native MuPDF library that pymupdf wraps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    mupdf-tools \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*   # clean up to keep image small

# Copy requirements first — Docker caches this layer
# If only code changes (not requirements), pip install won't re-run
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

EXPOSE 8000

# --reload enables live code reload in development (works with docker-compose volume mount)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
