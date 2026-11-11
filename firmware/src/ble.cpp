#include "ble.h"

#include <NimBLEDevice.h>

#include "config.h"

namespace {
NimBLEServer* server = nullptr;
NimBLECharacteristic* chMeas = nullptr;
NimBLECharacteristic* chCtrl = nullptr;
NimBLECharacteristic* chStatus = nullptr;
NimBLECharacteristic* chBattery = nullptr;
QueueHandle_t queue = nullptr;
volatile bool isConnected = false;
char name[24];

class ServerCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s) override {
    isConnected = true;
    Serial.println("[ble] připojeno");
  }
  void onDisconnect(NimBLEServer* s) override {
    isConnected = false;
    Serial.println("[ble] odpojeno");
    NimBLEDevice::startAdvertising();
  }
};

class CtrlCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override {
    NimBLEAttValue v = c->getValue();
    if (v.length() == 0) return;
    BleCommand cmd{};
    cmd.op = v.data()[0];
    cmd.len = (uint8_t)std::min<size_t>(sizeof(cmd.data), v.length() - 1);
    memcpy(cmd.data, v.data() + 1, cmd.len);
    xQueueSend(queue, &cmd, 0);
  }
};
}  // namespace

namespace ble {

const char* deviceName() { return name; }

void begin() {
  queue = xQueueCreate(8, sizeof(BleCommand));
  uint64_t mac = ESP.getEfuseMac();
  snprintf(name, sizeof name, "LaserPlan-%02X%02X", (uint8_t)(mac >> 32), (uint8_t)(mac >> 40));

  NimBLEDevice::init(name);
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCb());

  NimBLEService* svc = server->createService(LP_SERVICE_UUID);
  chMeas = svc->createCharacteristic(LP_MEASUREMENT_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  chCtrl = svc->createCharacteristic(LP_CONTROL_UUID, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  chStatus = svc->createCharacteristic(LP_STATUS_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  chCtrl->setCallbacks(new CtrlCb());
  BleMeasurement m{};
  m.status = 4;
  chMeas->setValue((uint8_t*)&m, sizeof m);
  svc->start();

  // Standardní služba baterie (zobrazí ji i telefon)
  NimBLEService* bas = server->createService("180F");
  chBattery = bas->createCharacteristic("2A19", NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  uint8_t pct = 100;
  chBattery->setValue(&pct, 1);
  bas->start();

  // Informace o zařízení
  NimBLEService* dis = server->createService("180A");
  dis->createCharacteristic("2A29", NIMBLE_PROPERTY::READ)->setValue("DIY");
  dis->createCharacteristic("2A24", NIMBLE_PROPERTY::READ)->setValue(LP_MODEL);
  dis->createCharacteristic("2A26", NIMBLE_PROPERTY::READ)->setValue(LP_FW_VERSION);
  dis->start();

  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(LP_SERVICE_UUID);
  adv->setScanResponse(true);      // jméno jde do scan response (128bit UUID je dlouhé)
  adv->start();
  Serial.printf("[ble] vysílám jako %s\n", name);
}

bool connected() { return isConnected; }

bool popCommand(BleCommand& out) { return queue && xQueueReceive(queue, &out, 0) == pdTRUE; }

void sendMeasurement(const BleMeasurement& m) {
  if (!chMeas) return;
  chMeas->setValue((uint8_t*)&m, sizeof m);
  if (isConnected) chMeas->notify();
}

void sendStatus(const BleStatus& s) {
  if (!chStatus) return;
  chStatus->setValue((uint8_t*)&s, sizeof s);
  if (isConnected) chStatus->notify();
}

void setBattery(uint8_t percent) {
  if (!chBattery) return;
  chBattery->setValue(&percent, 1);
  if (isConnected) chBattery->notify();
}

}  // namespace ble
