#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "firmware_config.h"
#include "plant_model.h"

static float state[MODEL_STATE_COUNT] = {};
static float virtualInput = VIRTUAL_INPUT_VALUE;
static uint32_t nextTickUs = 0;
static uint32_t lastTelemetryUs = 0;
static char commandBuffer[96];
static size_t commandLength = 0;

static void derivative(const float *values, float input, float *result) {
  for (uint8_t row = 0; row < MODEL_STATE_COUNT; ++row) {
    float sum = MODEL_B[row] * input;
    for (uint8_t column = 0; column < MODEL_STATE_COUNT; ++column) {
      sum += MODEL_A[row][column] * values[column];
    }
    result[row] = sum;
  }
}

static bool advancePlant(float input) {
  const float dt = static_cast<float>(SAMPLE_PERIOD_US) / 1000000.0f;
  float k1[MODEL_STATE_COUNT];
  float k2[MODEL_STATE_COUNT];
  float k3[MODEL_STATE_COUNT];
  float k4[MODEL_STATE_COUNT];
  float temporary[MODEL_STATE_COUNT];

  derivative(state, input, k1);
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    temporary[index] = state[index] + 0.5f * dt * k1[index];
  }
  derivative(temporary, input, k2);
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    temporary[index] = state[index] + 0.5f * dt * k2[index];
  }
  derivative(temporary, input, k3);
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    temporary[index] = state[index] + dt * k3[index];
  }
  derivative(temporary, input, k4);
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    state[index] += (dt / 6.0f) * (k1[index] + 2.0f * k2[index] +
                                   2.0f * k3[index] + k4[index]);
    if (!isfinite(state[index])) {
      return false;
    }
  }
  return true;
}

static float plantOutput(float input) {
  float output = MODEL_D * input;
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    output += MODEL_C[index] * state[index];
  }
  return output;
}

static float readPlantInput() {
#if MODEL_MODE_VIRTUAL
  return virtualInput;
#else
  const int raw = analogRead(ADC_PIN);
  const float fraction = static_cast<float>(raw) / 4095.0f;
  return INPUT_MIN + fraction * (INPUT_MAX - INPUT_MIN);
#endif
}

static void writePlantOutput(float output) {
#if MODEL_MODE_VIRTUAL
  (void)output;
#else
  if (!IO_CONFIG_VALID) {
    analogWrite(PWM_PIN, 0);
    return;
  }
  const float bounded = fminf(fmaxf(output, OUTPUT_MIN), OUTPUT_MAX);
  const float fraction = (bounded - OUTPUT_MIN) / (OUTPUT_MAX - OUTPUT_MIN);
  analogWrite(PWM_PIN, static_cast<int>(fraction * 255.0f));
#endif
}

static void sendError(const char *message) {
  Serial.print("{\"type\":\"error\",\"message\":\"");
  Serial.print(message);
  Serial.println("\"}");
}

static void sendTelemetry(uint32_t timestampUs, float input, float output) {
  Serial.printf(
      "{\"type\":\"telemetry\",\"timestamp_us\":%lu,\"input\":%.7g,"
      "\"output\":%.7g,\"mode\":\"%s\",\"states\":[",
      static_cast<unsigned long>(timestampUs), input, output,
      MODEL_MODE_VIRTUAL ? "virtual" : "io");
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    if (index != 0) {
      Serial.print(',');
    }
    Serial.print(state[index], 7);
  }
  Serial.println("]}");
}

static void handleCommand(const char *line) {
#if MODEL_MODE_VIRTUAL
  const char *type = strstr(line, "\"type\"");
  if (type == nullptr) {
    return;
  }
  const char *typeValue = strchr(type, ':');
  if (typeValue == nullptr || strstr(typeValue, "\"set_input\"") == nullptr) {
    return;
  }
  const char *value = strstr(line, "\"value\"");
  if (value == nullptr) {
    sendError("set_input command requires a numeric value");
    return;
  }
  const char *separator = strchr(value, ':');
  if (separator == nullptr) {
    sendError("invalid set_input command");
    return;
  }
  char *end = nullptr;
  const float parsed = strtof(separator + 1, &end);
  if (end == separator + 1 || !isfinite(parsed)) {
    sendError("set_input value must be finite");
    return;
  }
  virtualInput = parsed;
#else
  (void)line;
#endif
}

static void readCommands() {
#if MODEL_MODE_VIRTUAL
  while (Serial.available() > 0) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\n') {
      commandBuffer[commandLength] = '\0';
      handleCommand(commandBuffer);
      commandLength = 0;
    } else if (character != '\r') {
      if (commandLength + 1 < sizeof(commandBuffer)) {
        commandBuffer[commandLength++] = character;
      } else {
        commandLength = 0;
        sendError("serial command exceeded maximum length");
      }
    }
  }
#endif
}

void setup() {
  Serial.begin(115200);
  for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
    state[index] = MODEL_X0[index];
  }
#if !MODEL_MODE_VIRTUAL
  if (!IO_CONFIG_VALID) {
    sendError("real-I/O configuration is invalid; PWM remains disabled");
    return;
  }
  pinMode(PWM_PIN, OUTPUT);
  analogWrite(PWM_PIN, 0);
  analogReadResolution(12);
#endif
  nextTickUs = micros();
  lastTelemetryUs = nextTickUs;
}

void loop() {
#if !MODEL_MODE_VIRTUAL
  if (!IO_CONFIG_VALID) {
    delay(100);
    return;
  }
#endif
  readCommands();
  const uint32_t now = micros();
  if (static_cast<int32_t>(now - nextTickUs) < 0) {
    return;
  }
  nextTickUs += SAMPLE_PERIOD_US;
  if (static_cast<int32_t>(now - nextTickUs) >=
      static_cast<int32_t>(SAMPLE_PERIOD_US)) {
    nextTickUs = now + SAMPLE_PERIOD_US;
  }

  const float input = readPlantInput();
  if (!advancePlant(input)) {
    for (uint8_t index = 0; index < MODEL_STATE_COUNT; ++index) {
      state[index] = 0.0f;
    }
    writePlantOutput(0.0f);
    sendError("plant state became non-finite; state reset and output stopped");
    return;
  }
  const float output = plantOutput(input);
  if (!isfinite(output)) {
    writePlantOutput(0.0f);
    sendError("plant output became non-finite; output stopped");
    return;
  }
  writePlantOutput(output);
  if (static_cast<uint32_t>(now - lastTelemetryUs) >= TELEMETRY_INTERVAL_US) {
    lastTelemetryUs = now;
    sendTelemetry(now, input, output);
  }
}
