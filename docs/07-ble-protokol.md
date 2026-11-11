# 7. Bluetooth LE protokol

Přístroj se hlásí jako **`LaserPlan-XXXX`** a nabízí vlastní službu plus standardní služby
*Battery* (0x180F) a *Device Information* (0x180A). Všechna čísla jsou **little-endian**.

| Položka | UUID |
|---|---|
| Služba LaserPlan | `4c500001-6c61-7365-7270-6c616e000000` |
| Měření (read, notify) | `4c500002-6c61-7365-7270-6c616e000000` |
| Ovládání (write, write without response) | `4c500003-6c61-7365-7270-6c616e000000` |
| Stav (read, notify) | `4c500004-6c61-7365-7270-6c616e000000` |

## Měření – 12 bajtů

| Offset | Typ | Význam |
|---|---|---|
| 0 | uint16 | pořadové číslo měření |
| 2 | int32 | vzdálenost v **desetinách mm** (už s offsetem zvolené reference) |
| 6 | uint16 | kvalita signálu (dle modulu) |
| 8 | uint8 | stav: 0 OK, 1 chyba, 2 slabý signál, 3 mimo rozsah, 4 bez odpovědi, 5 modul nenalezen |
| 9 | uint8 | bit0 = zadní reference, bit1 = průběžné měření |
| 10 | uint16 | surový kód chyby modulu |

## Stav – 16 bajtů

| Offset | Typ | Význam |
|---|---|---|
| 0 | uint8 | baterie % |
| 1 | uint16 | napětí baterie mV |
| 3 | uint8 | bit0 USB, bit1 laser napájen, bit2 paprsek, bit3 průběžně, bit4 zadní reference, bit5 rychlé měření |
| 4 | int32 | offset zadní hrany (setiny mm) |
| 8 | int32 | offset přední hrany (setiny mm) |
| 12 | uint8 | jednotky displeje (0 m, 1 ft) |
| 13 | uint8 | ovladač laseru (0 žádný, 1 JRT, 2 ASCII, 3 simulace) |
| 14, 15 | uint8 | verze firmwaru (hlavní, vedlejší) |

## Příkazy (zápis do „Ovládání“)

| Bajt | Parametr | Akce |
|---|---|---|
| `01` | – | změř |
| `02` / `03` | – | paprsek zap / vyp |
| `04` / `05` | – | průběžné měření zap / vyp |
| `06` | uint8 | reference: 0 přední, 1 zadní hrana |
| `07` | int32 | offset zadní hrany (setiny mm) |
| `08` | – | pípni |
| `09` | uint8 | jednotky na displeji |
| `0A` | int32 | offset přední hrany (setiny mm) |
| `0B` | uint8 | ovladač laseru (restart) |
| `0C` | – | vypnout napájení laser modulu |
| `0D` | uint8 | rychlé měření (1 = MĚŘIT měří hned) |

## Příklad (JavaScript, Web Bluetooth)

```js
const SVC = '4c500001-6c61-7365-7270-6c616e000000';
const dev = await navigator.bluetooth.requestDevice({ filters: [{ services: [SVC] }] });
const svc = await (await dev.gatt.connect()).getPrimaryService(SVC);
const meas = await svc.getCharacteristic('4c500002-6c61-7365-7270-6c616e000000');
meas.addEventListener('characteristicvaluechanged', (e) => {
  const v = e.target.value;
  if (v.getUint8(8) === 0) console.log('vzdálenost', v.getInt32(2, true) / 10, 'mm');
});
await meas.startNotifications();
const ctrl = await svc.getCharacteristic('4c500003-6c61-7365-7270-6c616e000000');
await ctrl.writeValue(new Uint8Array([0x01]));   // změř
```

Hotová implementace je v [`app/js/ble.js`](../app/js/ble.js).
