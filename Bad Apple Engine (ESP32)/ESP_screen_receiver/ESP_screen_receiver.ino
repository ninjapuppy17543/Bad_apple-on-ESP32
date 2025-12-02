#include <Arduino.h>
#include <TFT_eSPI.h>

TFT_eSPI tft = TFT_eSPI();

#define BACKLIGHT_PIN 21

const int FRAME_W = 128;
const int FRAME_H = 96;
const int BYTES_PER_FRAME = (FRAME_W * FRAME_H) / 8;

uint8_t frameBuf[BYTES_PER_FRAME];

void drawFrameFast(const uint8_t *data) {
    static uint16_t lineBuf[FRAME_W];
    int bytesPerRow = FRAME_W / 8;

    for (int y = 0; y < FRAME_H; y++) {
        const uint8_t* rowData = data + y * bytesPerRow;

        // convert 1-bit to 16-bit color line
        for (int x = 0; x < FRAME_W; x++) {
            uint8_t byte = rowData[x >> 3];
            bool pixel = byte & (0x80 >> (x & 7));
            lineBuf[x] = pixel ? TFT_WHITE : TFT_BLACK;
        }

        // push whole row at once (MUCH faster)
        tft.pushImage(0, y, FRAME_W, 1, lineBuf);
    }
}


void setup() {
  pinMode(BACKLIGHT_PIN, OUTPUT);
  digitalWrite(BACKLIGHT_PIN, HIGH);

  Serial.begin(921600);

  tft.init();
  tft.setRotation(1);


  tft.fillScreen(TFT_BLACK);
  tft.setCursor(0,0);
  tft.setTextColor(TFT_WHITE);
  tft.println("Waiting for frames...");
}

void loop() {
  // Flush leftover serial bytes to ensure alignment
  while (Serial.available()) Serial.read();

  // Read EXACTLY one frame
  int bytesRead = Serial.readBytes(frameBuf, BYTES_PER_FRAME);

  if (bytesRead == BYTES_PER_FRAME) {
    drawFrameFast(frameBuf);
    Serial.write(0xAA);  // ACK
  }
}
