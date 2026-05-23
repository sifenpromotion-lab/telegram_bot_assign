FROM python:3.11-slim

# Install fonts for image generation
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fontconfig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Poppins font
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf" \
         -O /usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-LightItalic.ttf" \
         -O /usr/share/fonts/truetype/google-fonts/Poppins-LightItalic.ttf && \
    fc-cache -f -v

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

EXPOSE 8000

CMD ["python", "bot.py"]
