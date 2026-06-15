#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

const char* ssid = "POCO X7 Pro";
const char* password = "123456789";

// Replace with your real PC Wi-Fi IP
const char* serverUrl = "http://10.145.57.129:5000/api/presence";

const char* deviceId = "esp8266_01";

// Room A sensors
const int ROOM_A_SENSOR_1 = D1; // outside side
const int ROOM_A_SENSOR_2 = D2; // inside side

// Room B sensors
const int ROOM_B_SENSOR_1 = D5; // outside side
const int ROOM_B_SENSOR_2 = D6; // inside side

const unsigned long SEQUENCE_TIMEOUT = 3000;
const unsigned long DEBOUNCE_DELAY = 100;

struct RoomCounter {
  String room;
  int sensor1Pin;
  int sensor2Pin;

  int lastSensor1State;
  int lastSensor2State;

  int firstSensor; 
  unsigned long firstTriggerTime;
  unsigned long lastTriggerTime;
};

RoomCounter rooms[] = {
  {"room_A", ROOM_A_SENSOR_1, ROOM_A_SENSOR_2, HIGH, HIGH, 0, 0, 0},
  {"room_B", ROOM_B_SENSOR_1, ROOM_B_SENSOR_2, HIGH, HIGH, 0, 0, 0}
};

const int roomCount = sizeof(rooms) / sizeof(rooms[0]);


void connectToWiFi() {
  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("ESP8266 IP address: ");
  Serial.println(WiFi.localIP());
}


void sendPresenceEvent(String room, String direction, String sensorId) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Reconnecting...");
    connectToWiFi();
  }

  WiFiClient client;
  HTTPClient http;

  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");

  String json = "{";
  json += "\"device_id\":\"" + String(deviceId) + "\",";
  json += "\"sensor_id\":\"" + sensorId + "\",";
  json += "\"room\":\"" + room + "\",";
  json += "\"direction\":\"" + direction + "\",";
  json += "\"detected\":true";
  json += "}";

  Serial.println();
  Serial.println("Sending event:");
  Serial.println(json);

  int httpCode = http.POST(json);

  Serial.print("HTTP response code: ");
  Serial.println(httpCode);

  String response = http.getString();
  Serial.println(response);

  http.end();
}


void handleSensorTrigger(RoomCounter &room, int triggeredSensor) {
  unsigned long now = millis();

  // Avoid multiple triggers too fast
  if (now - room.lastTriggerTime < DEBOUNCE_DELAY) {
    return;
  }

  room.lastTriggerTime = now;

  Serial.print(room.room);
  Serial.print(" sensor triggered: ");
  Serial.println(triggeredSensor);

  // No sequence started yet
  if (room.firstSensor == 0) {
    room.firstSensor = triggeredSensor;
    room.firstTriggerTime = now;
    return;
  }

  // If sequence took too long, restart
  if (now - room.firstTriggerTime > SEQUENCE_TIMEOUT) {
    room.firstSensor = triggeredSensor;
    room.firstTriggerTime = now;
    return;
  }

  // Sensor 1 then Sensor 2 = enter
  if (room.firstSensor == 1 && triggeredSensor == 2) {
    Serial.print(room.room);
    Serial.println(" ENTER detected");

    sendPresenceEvent(
      room.room,
      "enter",
      room.room + "_sensor_1_then_2"
    );

    room.firstSensor = 0;
    return;
  }

  // Sensor 2 then Sensor 1 = exit
  if (room.firstSensor == 2 && triggeredSensor == 1) {
    Serial.print(room.room);
    Serial.println(" EXIT detected");

    sendPresenceEvent(
      room.room,
      "exit",
      room.room + "_sensor_2_then_1"
    );

    room.firstSensor = 0;
    return;
  }

  // Same sensor triggered twice, restart sequence
  room.firstSensor = triggeredSensor;
  room.firstTriggerTime = now;
}


void setup() {
  Serial.begin(9600);

  for (int i = 0; i < roomCount; i++) {
    pinMode(rooms[i].sensor1Pin, INPUT_PULLUP);
    pinMode(rooms[i].sensor2Pin, INPUT_PULLUP);

    rooms[i].lastSensor1State = digitalRead(rooms[i].sensor1Pin);
    rooms[i].lastSensor2State = digitalRead(rooms[i].sensor2Pin);
  }

  connectToWiFi();
}


void loop() {
  for (int i = 0; i < roomCount; i++) {
    int currentSensor1State = digitalRead(rooms[i].sensor1Pin);
    int currentSensor2State = digitalRead(rooms[i].sensor2Pin);

    // INPUT_PULLUP logic:
    // HIGH = not triggered
    // LOW  = triggered / button pressed

    if (rooms[i].lastSensor1State == HIGH && currentSensor1State == LOW) {
      handleSensorTrigger(rooms[i], 1);
    }

    if (rooms[i].lastSensor2State == HIGH && currentSensor2State == LOW) {
      handleSensorTrigger(rooms[i], 2);
    }

    rooms[i].lastSensor1State = currentSensor1State;
    rooms[i].lastSensor2State = currentSensor2State;
  }

  delay(20);
}