# Bronbasis en controlegrenzen

Geraadpleegd voor deze implementatie op 13 oktober 2026.

## Apparaatprotocol

Aangeleverd bestand: **R290 HouseHeating-1.pdf**, 197 pagina's. Niet opgenomen in distributies.

- PDF p. 163 (afdruk 156): Modbus RTU, 9600/8N1, temperatuur ×10 en rusttijd 100 ms.
- PDF p. 164: lees-/schrijffuncties en registergebieden.
- PDF p. 166: status-, fout- en I/O-adressen.
- PDF p. 167–168: metingen, elektrische waarden en aanvullende temperatuursensoren.
- PDF p. 168–169: gebruikte status- en foutbits. Bit 8 van bedrijfsstatus 1 is in deze vertaling ongelukkig als “Systeem Bevriezen” aangeduid; de interpretatie als ontdooistatus moet tijdens een echte cyclus worden bevestigd.
- PDF p. 184–185: normale gebruikersinstellingen, modi en curves vanaf protocol 130.
- PDF p. 187: firmware-/protocolregisters.
- PDF p. 9: technisch warmwaterbereik, gebruikt voor conservatieve begrenzing bij afwijking van de registertabel.

Visueel gecontroleerde tabellen zijn leidend voor adres en betekenis; de ontbrekende of tegenstrijdige details zijn niet ingevuld met verzonnen eenheden of een ongeteste COP-formule.

## Software-API

- https://developers.home-assistant.io/blog/2026/07/05/modernizing-modbus/
- https://developers.home-assistant.io/docs/modbus/introduction/
- https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/modbus/connection.py
- https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/modbus/manifest.json
- https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/sofar/config_flow.py
- https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/sofar/__init__.py
- https://github.com/home-assistant-libs/modbus-connection/blob/main/src/modbus_connection/_protocol.py
- https://github.com/home-assistant-libs/modbus-connection/blob/main/src/modbus_connection/_client.py
- https://developers.home-assistant.io/blog/2026/09/30/probatio-validation-engine/
- https://developers.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/

De bekeken Home Assistant 2026.10.1-Modbusmanifest specificeert modbus-connection 4.12.4. De custom-integratie laat Home Assistant de dependencies van de standaard Modbus-integratie beheren; er worden geen concurrerende bibliotheekversies geforceerd.

De officiële voorbeelden zijn gebruikt als API-/architectuurreferentie, niet als bewijs van een uitgevoerde runtime-test voor deze nieuwe integratie. De documentatie raadt ook descriptor-gebaseerde componentmodellen aan; deze implementatie gebruikt expliciete eigen datamodellen op dezelfde publieke unit-interface. De Core-map is daarom nadrukkelijk voorbereidend en nog geen afgeronde reviewbijdrage.

## Aangeleverde archieven
SHA256 van de oorspronkelijke ZIP-bestanden; gecontroleerd bij import op 13 oktober 2026.
- `househeating_modbus_project_v0.1.0.zip`: `23b2a4a0e8d901dc520b560545692c9dd3043db6a7c89615923c1a508ba1c398`
- `househeating_modbus_v0.1.0.zip`: `5cb45302f8a1d1f18ab985d6e38f96461dba55339473c87cc1685ecf2c3af6c5`

## Hercontrole voor v0.2.0

- De actuele [HGB-productpagina](https://www.hgb-trading.nl/househeating-warmtepomp-monoblock-12-kw-162229888.html) noemt voor HH-C3-12 een watertemperatuur tot 75 °C. Dit ondersteunt samen met 0x0302 (20–75 °C, PDF p184) het instelbare warmwaterplafond van 75 °C. 0x0301 blijft 20–60 °C volgens diezelfde tabel.
- Waterdebiet: lopende parameter 25 op PDF p160 noemt 3–100 L/min; de Modbus-tabel p167 koppelt waterstroom als echte waarde aan 0x0058. Stilstandwaarde 0 wordt geaccepteerd.
- De echte Home Assistant 2026.10.1-package is geïnstalleerd en gebruikt `probatio==0.13.0`. De eerdere bewering dat die import een fout was, is onjuist. De import is behouden en wordt met echte formulieren getest.
- P48/0x0130 en P116/0x0174 worden alleen gelezen. Onbekende configuratie levert geen verzonnen procesmeting op. De dubbelzinnige P257 is niet gebruikt voor nieuwe schrijfbediening.
