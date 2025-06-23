FROM python:3.12-slim

WORKDIR /app

COPY weatherboy.py .
COPY requirements.txt .
COPY ./templates .
COPY ./weather_data .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5170
CMD ["python", "weatherboy.py"]

