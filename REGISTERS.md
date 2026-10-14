# Registercatalogus v0.2.0

## Aanvulling 0.4.0 — leesbare relaisstatus

PDF p166 geeft 0x0019–0x001C als relaiswoorden. PDF p173–174 bevestigt
compressor 1 op 0x001A bit 0; de verdere gebruikte relaisbits staan op p174.
De nieuwe entiteiten decoderen alleen gedocumenteerde bits uit reeds bekende
leeswoorden. Een ontbrekende/verouderde groep levert geen OFF-status op.
De waargenomen compressorstatistieken zijn afgeleid en hebben geen eigen
Modbus-register. Nieuwe foutentiteiten gebruiken de bestaande FAULT_LABELS.

Geen schrijfadres, schrijfallowlist, schaal, vrijgave of verificatieregel is
uitgebreid. De eigen stooklijn gebruikt uitsluitend een bestaand setpoint via
dezelfde beveiligde route. Externe meter- en PV-bronnen zijn HA-entiteiten,
geen virtuele injectie in apparaatregisters.

## Monitoring in lokale versie 0.3.0

De bestaande registercatalogus en entiteitsidentiteiten blijven behouden.

| Bron | Onderbouwing | Gebruik |
|---|---|---|
| 0x005C | PDF p167, raw / 100 naar kW | Elektrisch vermogen; optioneel geïntegreerde energie |
| 0x005D | PDF p167, gerapporteerd in kWh | Alleen apparaatdiagnostiek; resolutie/reset/overloop niet bewezen |
| 0x004F / 0x0050 | PDF p167, inlaat/uitlaat | Bestaande meetdeler en foutonderdrukking behouden |
| 0x0058 | PDF p167 echte waarde; p160 parameter 25 noemt L/min | Berekend debiet met expliciete schaalbevestiging en correctiefactor |

Afgeleide entiteiten krijgen geen verzonnen Modbus-registeradres. De bestaande
`flow_raw`-sleutel en gerapporteerde sensor blijven behouden; de gekalibreerde
sensor is afzonderlijk. Geen wijziging aan schrijfadressen of allowlists.
Zie [ENERGIEMONITORING.md](ENERGIEMONITORING.md) voor formules en metadata.

Adressen zijn de hexadecimale, nul-gebaseerde adressen op de Modbus-bus.
Bron: meegeleverde HouseHeating-handleiding; paginanummers hieronder zijn PDF-pagina’s.
De kolom schrijven betekent: uitsluitend na expliciete vrijgave en verificatie.

| Entiteitsleutel | Adres | Functie | Eenheid | Schrijven | PDF-pagina |
|---|---|---|---|---|---|
| `status_1` | `0x0000` | Bedrijfsstatus 1 (bits) | ruw / status | Nee | 166 |
| `status_2` | `0x0001` | Bedrijfsstatus 2 (bits) | ruw / status | Nee | 166 |
| `fault_word_2` | `0x0002` | Fout-/diagnosewoord 0x0002 | ruw / status | Nee | 166 |
| `fault_word_3` | `0x0003` | Fout-/diagnosewoord 0x0003 | ruw / status | Nee | 166 |
| `fault_word_4` | `0x0004` | Fout-/diagnosewoord 0x0004 | ruw / status | Nee | 166 |
| `fault_word_5` | `0x0005` | Fout-/diagnosewoord 0x0005 | ruw / status | Nee | 166 |
| `fault_word_6` | `0x0006` | Fout-/diagnosewoord 0x0006 | ruw / status | Nee | 166 |
| `fault_word_7` | `0x0007` | Fout-/diagnosewoord 0x0007 | ruw / status | Nee | 166 |
| `fault_word_8` | `0x0008` | Fout-/diagnosewoord 0x0008 | ruw / status | Nee | 166 |
| `fault_word_9` | `0x0009` | Fout-/diagnosewoord 0x0009 | ruw / status | Nee | 166 |
| `compressor_frequency` | `0x0040` | Compressorfrequentie | Hz | Nee | 167 |
| `fan_raw` | `0x0041` | Ventilatorsnelheid (ruw) | ruw / status | Nee | 167 |
| `eev_steps` | `0x0042` | Stappen expansieventiel | ruw / status | Nee | 167 |
| `evi_steps` | `0x0043` | Stappen EVI-ventiel | ruw / status | Nee | 167 |
| `ac_voltage` | `0x0044` | AC-ingangsspanning | V | Nee | 167 |
| `ac_current` | `0x0045` | AC-ingangsstroom | A | Nee | 167 |
| `compressor_current` | `0x0046` | Compressorfasestroom | A | Nee | 167 |
| `ipm_temperature` | `0x0047` | Temperatuur compressormodule | °C | Nee | 167 |
| `high_pressure_saturation_temperature` | `0x0048` | Verzadigingstemperatuur hoge druk | °C | Nee | 167 |
| `low_pressure_saturation_temperature` | `0x0049` | Verzadigingstemperatuur lage druk | °C | Nee | 167 |
| `outdoor_temperature` | `0x004A` | Buitentemperatuur | °C | Nee | 167 |
| `outdoor_coil_temperature` | `0x004B` | Temperatuur buitenspoel | °C | Nee | 167 |
| `indoor_coil_temperature` | `0x004C` | Temperatuur binnenspoel | °C | Nee | 167 |
| `suction_temperature` | `0x004D` | Zuigtemperatuur | °C | Nee | 167 |
| `discharge_temperature` | `0x004E` | Persgastemperatuur | °C | Nee | 167 |
| `water_inlet_temperature` | `0x004F` | Waterinlaattemperatuur | °C | Nee | 167 |
| `water_outlet_temperature` | `0x0050` | Wateruitlaattemperatuur | °C | Nee | 167 |
| `economizer_inlet_temperature` | `0x0051` | Economizerinlaattemperatuur | °C | Nee | 167 |
| `economizer_outlet_temperature` | `0x0052` | Economizeruitlaattemperatuur | °C | Nee | 167 |
| `dhw_temperature` | `0x0054` | Boilertemperatuur | °C | Nee | 167 |
| `plate_temperature` | `0x0055` | Temperatuur platenwarmtewisselaar | °C | Nee | 167 |
| `pump_pwm` | `0x0057` | Waterpomp-PWM | % | Nee | 167 |
| `flow_raw` | `0x0058` | Waterdebiet | L/min | Nee | 167 |
| `dhw_return_temperature` | `0x0059` | Retourtemperatuur warmwatercirculatie | °C | Nee | 167 |
| `unit_voltage` | `0x005A` | Ingangsspanning eenheid | V | Nee | 167 |
| `unit_current` | `0x005B` | Ingangsstroom eenheid | A | Nee | 167 |
| `input_power` | `0x005C` | Gerapporteerd elektrisch ingangsvermogen | kW | Nee | 167 |
| `reported_energy` | `0x005D` | Gerapporteerd elektriciteitsverbruik | kWh | Nee | 167 |
| `solar_temperature` | `0x0072` | Temperatuur zonneboiler | °C | Nee | 168 |
| `zone_2_temperature` | `0x0073` | Temperatuur zone 2 | °C | Nee | 168 |
| `buffer_temperature` | `0x0074` | Buffervattemperatuur | °C | Nee | 168 |
| `total_outlet_temperature` | `0x0075` | Totale wateruitlaattemperatuur | °C | Nee | 168 |
| `phase_b_voltage` | `0x0076` | Spanning fase B | V | Nee | 168 |
| `phase_b_current` | `0x0077` | Stroom fase B | A | Nee | 168 |
| `phase_c_voltage` | `0x0078` | Spanning fase C | V | Nee | 168 |
| `phase_c_current` | `0x0079` | Stroom fase C | A | Nee | 168 |
| `smart_grid_raw` | `0x007A` | Smart-gridstatus (ruw) | ruw / status | Nee | 168 |
| `mixing_valve_zone_2_raw` | `0x007B` | Mengklep zone 2 (ruw) | ruw / status | Nee | 168 |
| `zone_1_temperature` | `0x007C` | Mengtemperatuur zone 1 | °C | Nee | 168 |
| `mixing_valve_zone_1_raw` | `0x007D` | Mengklep zone 1 (ruw) | ruw / status | Nee | 168 |
| `io_word_0019` | `0x0019` | I/O-statuswoord 0x0019 | ruw / status | Nee | 166 |
| `io_word_001a` | `0x001A` | I/O-statuswoord 0x001A | ruw / status | Nee | 166 |
| `io_word_001b` | `0x001B` | I/O-statuswoord 0x001B | ruw / status | Nee | 166 |
| `io_word_001c` | `0x001C` | I/O-statuswoord 0x001C | ruw / status | Nee | 166 |
| `io_word_001d` | `0x001D` | I/O-statuswoord 0x001D | ruw / status | Nee | 166 |
| `io_word_001e` | `0x001E` | I/O-statuswoord 0x001E | ruw / status | Nee | 166 |
| `io_word_001f` | `0x001F` | I/O-statuswoord 0x001F | ruw / status | Nee | 166 |
| `io_word_0020` | `0x0020` | I/O-statuswoord 0x0020 | ruw / status | Nee | 166 |
| `cooling_setpoint` | `0x0300` | Gewenste koeltemperatuur | °C | Ja | 184 |
| `heating_setpoint` | `0x0301` | Gewenste verwarmingstemperatuur | °C | Ja | 184 |
| `dhw_setpoint` | `0x0302` | Gewenste warmwatertemperatuur | °C | Ja | 184 |
| `floor_setpoint` | `0x0303` | Gewenste vloerverwarmingstemperatuur | °C | Ja | 184 |
| `operating_mode` | `0x0304` | Bedrijfsmodus | ruw / status | Ja | 185 |
| `power` | `0x0305` | Warmtepomp aan/uit | ruw / status | Ja | 185 |
| `indoor_setpoint_raw` | `0x0306` | Gewenste binnentemperatuur (ruw) | ruw / status | Nee | 185 |
| `operating_profile` | `0x0307` | Bedrijfsprofiel | ruw / status | Ja | 185 |
| `cooling_curve` | `0x0313` | Koelcurve | ruw / status | Ja | 185 |
| `heating_curve` | `0x0314` | Verwarmingscurve | ruw / status | Ja | 185 |
| `dhw_curve` | `0x0315` | Warmwatercurve | ruw / status | Ja | 185 |
| `floor_curve` | `0x0316` | Vloerverwarmingscurve | ruw / status | Ja | 185 |
| `firmware_version` | `0x0360` | Firmwareversie (ruw) | ruw / status | Nee | 187 |
| `product_type` | `0x0361` | Producttype | ruw / status | Nee | 187 |
| `product_type_id` | `0x0362` | Producttype-ID | ruw / status | Nee | 187 |
| `protocol_version` | `0x0363` | Protocolversie | ruw / status | Nee | 187 |

Temperaturen: standaard signed 16-bit / 10; setpoints hebben een afzonderlijke deler.
Statusvelden blijven unsigned. Ventilator, debiet en enkele overige onduidelijke velden worden bewust ruw weergegeven.
Extra registergroepen en curven worden langzamer gelezen; ontbrekende optionele groepen maken basiswaarden niet onbeschikbaar.
Curven worden alleen via 0x0313–0x0316 bediend vanaf protocol 130; de oudere gecombineerde bytevelden worden niet beschreven.

## Aanvullingen v0.2.0

- `flow_raw`/0x0058 behoudt zijn entiteitsleutel maar heeft nu eenheid L/min
  (PDF p160 en p167). Stilstandwaarde 0 is geldig.
- `dhw_sensor_enabled`/0x0130: alleen lezen, bevestigt de warmwaterfunctie (P48).
- `temperature_control_mode`/0x0174: alleen lezen, 0 = waterinlaat,
  1 = wateruitlaat (P116). Onbekende waarden worden niet geraden.
- Boiler/vermogen/debiet/relais worden elke basiscyclus gelezen; zones en
  configuratie blijven langzamer. Optionele leesfouten hergebruiken geen oude meting.
- Warmwater-schrijfplafond kan van standaard 65 tot maximaal 75 °C worden ingesteld.
  Register 0x0301 voor verwarming blijft maximaal 60 °C.
