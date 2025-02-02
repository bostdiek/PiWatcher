# ----- Builder stage -----
FROM python:3.11-slim as builder
WORKDIR /app
COPY . .
RUN pip install --upgrade pip && pip install poetry
RUN poetry build

# ----- Final image -----
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/dist/*.whl /app/
RUN pip install /app/*.whl
CMD ["python", "piwatcher_base/viewer.py"]
