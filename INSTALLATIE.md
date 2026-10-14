# HouseHeating Modbus — installatie en eerste ingebruikname

**Versie 0.4.0 · experimenteel · doelmodel HH-C3-12 · Home Assistant 2026.10.1+**

Gebruik bij voorkeur HACS. Bestaande gebruikers werken de integratie bij;
verwijder/toevoegen is niet nodig. Maak vooraf een Home Assistant-back-up.
De protocolcode, echte HA-klassen en lifecycle zijn softwarematig getest;
productie-installatie en fysieke warmtepomp zijn niet gevalideerd.

Energiemonitoring, compressorstatistieken en eigen stooklijn staan standaard uit.
Automatische stooklijnbediening vraagt bestaande vrijgave en expliciete
bevestiging. Zie [FUNCTIES.md](FUNCTIES.md) en [ENERGIEMONITORING.md](ENERGIEMONITORING.md).

## 1. Installeren

Gebruik bij voorkeur HACS, zoals beschreven in [README.md](README.md#installeren-met-hacs-aanbevolen). Hieronder staat het handmatige alternatief.

Pak `househeating_modbus_v0.4.0.zip` uit. Kopieer alleen de map `custom_components/househeating` naar de configuratiemap van Home Assistant, zodat dit bestand bestaat:

```text
/config/custom_components/househeating/manifest.json
```

De map `_vendor/househeating_modbus` moet daarbij meegekopieerd worden; die bevat de eigen apparaatbibliotheek. Installeer die bibliotheek niet apart in Home Assistant en wijzig geen Python-pakketten van Home Assistant handmatig.

Herstart Home Assistant volledig. Ga daarna naar **Instellingen → Apparaten & diensten → Integratie toevoegen → HouseHeating Modbus**. De bedieningsnamen worden Nederlands bij een Nederlandstalig profiel.

Er is geen extra `modbus:`-blok in `configuration.yaml` nodig. Laat een bestaande integratie, los uitleesscript of ander onafhankelijk Modbus-programma niet tegelijkertijd dezelfde fysieke bus/gateway bedienen. Dit pakket opent zijn verbinding via de gedeelde Home Assistant-API, niet via een eigen Pymodbus-client.

## 2. Verbinding kiezen

| Keuze in het scherm | Wanneer gebruiken | Invullen |
|---|---|---|
| Modbus RTU over TCP | Transparante RS485-naar-netwerkbrug die RTU-frames doorstuurt | Host/IP en werkelijke TCP-poort |
| Modbus TCP | Gateway die Modbus TCP/MBAP omzet naar RTU | Host/IP en werkelijke TCP-poort |
| USB/RS485 | RS485-adapter rechtstreeks beschikbaar in Home Assistant | Serieel pad, liefst `/dev/serial/by-id/...` |

Het juiste type wordt bepaald door de gatewayconfiguratie; RTU-over-TCP en Modbus TCP zijn niet uitwisselbaar. De standaardpoort in het formulier is 502, maar jouw gateway kan een andere poort gebruiken. Een transparante gateway gebruikt aan de warmtepompzijde **9600 baud, 8 databits, geen pariteit, 1 stopbit, Modbus RTU**. Bij USB/RS485 stelt de integratie deze UART-instellingen zelf in. Adres 0 wordt geweigerd; vul het werkelijke apparaatadres tussen 1 en 247 in. De waarde 1 in het scherm is alleen een startwaarde, geen automatische adresdetectie.

Bij Home Assistant in een Unraid-VM moet een USB-adapter aan die VM beschikbaar zijn gemaakt; het pad moet in Home Assistant bestaan, niet alleen op de Unraid-host.

Laat de geschikte monitoringpoort en eventuele gelijktijdige communicatie van de oorspronkelijke controller controleren. De handleiding onderscheidt COM2/monitoring en COM4/controller, maar printrevisies kunnen verschillen. Een softwarematige gedeelde verbinding lost botsingen met een onafhankelijke fysieke master niet op. Werk niet aan een onder spanning staande warmtepomp.

## 3. Eerst uitlezen

Bij toevoegen worden uitsluitend leescommando's verzonden. De integratie schrijft geen standaardinstellingen, zet de pomp niet aan of uit en herstelt geen oude setpoints uit Home Assistant. Bestaande waarden worden van de warmtepomp gelezen.

Je krijgt één apparaat, met standaard onder andere buitentemperatuur, waterinlaat- en wateruitlaattemperatuur, compressorfrequentie, bedrijfsmodus, bedrijfsprofiel en de vier temperatuursetpoints. Aan/uit, moduskeuze en instelgetallen zijn al aanwezig maar blijven niet-beschikbaar zolang de bediening niet is vrijgegeven.

Er zijn 76 register-sensoren beschikbaar; leessensoren naast bedieningsentiteiten zijn standaard uitgeschakeld. De meeste technische en optionele sensoren zijn standaard uitgeschakeld. Open de entiteitenlijst van het apparaat en schakel alleen de relevante extra entiteiten in, bijvoorbeeld buffervattemperatuur, boilertemperatuur, protocolversie of elektrisch ingangsvermogen. Een aangemaakte entiteit betekent niet dat die meting bij jouw configuratie fysiek aanwezig is.

Basiswaarden worden standaard elke 30 seconden gelezen. Boiler, debiet, vermogen en relais worden eveneens elke 30 seconden gelezen. Overige extra registers, configuratie en curven worden elke 120 seconden gelezen. Elke aanvraag bevat maximaal 16 registers; de minimale busrust is 120 milliseconden. Dit zijn conservatieve startinstellingen, geen garantie dat elke controller/gateway daarmee probleemloos werkt.

## 4. Temperatuurschaling verifiëren

De handleiding noemt raw/10, maar in verwante firmware/documentatie bestaan verschillen. Daarom zijn twee afzonderlijke delers instelbaar onder **Opties**:

| Op het fysieke scherm | Ruwe Modbus-waarde | Deler |
|---|---|---|
| 35,0 °C | 350 | 10 |
| 35 °C | 35 | 1 |

Controleer de **metingen én alle vier setpoints**. Neem niet aan dat ze dezelfde deler gebruiken. De ruwe waarde staat bij iedere register-sensor in de attributen en in de diagnostiek. Bewaar gewijzigde delers eerst met bediening uit; controleer daarna de cijfers opnieuw. Een ogenschijnlijk normale temperatuur bewijst niet dat de schaal correct is.

De firmware-/protocolversie is standaard beschikbaar als uitgeschakelde diagnostische entiteit en altijd in de diagnostiek, voor zover het apparaat het register beantwoordt. Adressen zijn rechtstreeks overgenomen als nul-gebaseerde wire-adressen; tel er niet automatisch 1 of 40001 bij op.

## 5. Bediening vrijgeven

Open de opties, zet **Modbus-bediening na bevestiging inschakelen** aan en ga verder. Er verschijnt een controlepagina met temperaturen, setpoints, ruwe waarden en firmware-/protocolinformatie. Vergelijk alle waarden met het fysieke bedieningsscherm. Bevestigen verzendt nog géén schrijfopdracht; het maakt de gewone bedieningsentiteiten daarna beschikbaar.

Een ongeldige identiteit, ongeldige temperatuur, een herkende fout van een vereiste temperatuursensor, of een setpoint buiten het documentatiebereik verhindert vrijgave. Dat is opzettelijk. Raadpleeg de diagnostiek in plaats van de controle weg te programmeren.

De firmware-/protocolvingerafdruk is geen uniek serienummer. Een verandering blokkeert schrijven; een vervangende pomp met identieke versiegegevens kan hiermee niet worden onderscheiden.

## 6. Wat je kunt bedienen

| Bediening | Functie |
|---|---|
| Aan/uit-schakelaar | Normale globale software-aan/uitopdracht; geen netspanningsonderbreking |
| Bedrijfsmodus | Koeling, verwarming, warmwater, vloerverwarming en combinaties met warmwater |
| Bedrijfsprofiel | Standaard, krachtig of stil |
| Vier instelgetallen | Gewenste temperaturen voor koeling, verwarming, warmwater en vloerverwarming |
| Vier curvekeuzes | Ingebouwde curves; alleen protocol ≥ 130; entiteiten standaard uitgeschakeld |

Een modus- of temperatuurwijziging zet de warmtepomp niet automatisch aan. Een globale uitschakeling is niet uitsluitend het uitschakelen van ruimteverwarming. Houd daar rekening mee wanneer warmwater met ruimteverwarming wordt gecombineerd.

Instellen gaat in hele graden Celsius. Standaardgrenzen: koeling 7–25 °C, verwarming 20–60 °C, vloerverwarming 20–45 °C, warmwater 20–65 °C. De plafonds voor verwarming, vloer en warmwater kun je in de opties verlagen. Het vloerplafond kan na controle tot de gedocumenteerde 60 °C worden verhoogd, maar dat is nadrukkelijk geen installatieadvies. Warmwater begint met een schrijfplafond van 65 °C. Je kunt dat na controle verhogen tot 75 °C, ondersteund door register 0x0302 en de actuele HGB-productpagina. Verwarming blijft maximaal 60 °C volgens register 0x0301.

Na een wijziging volgt een controle door teruglezen. Een niet-bevestigde opdracht levert een fout op en wordt door deze integratie niet automatisch opnieuw geschreven. Controleer bij een fout eerst de werkelijke toestand: een opdracht kan zijn uitgevoerd terwijl alleen het antwoord verloren ging.

Gebruik voor eerste tests een kleine setpointwijziging in de reeds gekozen modus. Voer geen snelle aan/uit- of verwarm/koelwisselingen uit om de integratie te testen. De softwarevrijgave is geen technische keuring van het hydraulische of elektrische systeem.

## 7. Storingen, herstarts en updates

Een mislukte basisuitlezing maakt het apparaat niet-beschikbaar; oude basiswaarden worden niet opnieuw als verse metingen gepresenteerd. Een mislukte extra registergroep maakt alleen die groep niet-beschikbaar. Als een firmware maar een deel van zo'n groep ondersteunt, is die groep in deze versie niet afzonderlijk onderverdeeld naar ondersteunde adressen. Schakel de extra groepen tijdelijk uit en gebruik de diagnostiek voor het maken van een passend profiel.

Met de knop **Alle waarden opnieuw uitlezen** kun je ook na een communicatiefout een nieuwe poging doen. Bij terugkeer van de verbinding worden optionele gegevens opnieuw gelezen. Niet elke tijdelijk stilgevallen verbinding wordt door de netwerklaag onmiddellijk ontdekt; de volgende aanvraag en de ingestelde time-out bepalen mede hoe snel uitval zichtbaar wordt.

Een Home Assistant-herstart leidt niet tot het terugschrijven van oude of lege instellingen. De pomp blijft bron van de huidige instellingen. Het wijzigen van de verbinding via **Opnieuw configureren** behoudt de apparaat- en entiteitsidentiteiten binnen dezelfde config-entry, maar vergrendelt bediening opnieuw. Verwijder de integratie niet om alleen een IP-adres te wijzigen.

Voor een nieuwe pakketversie: maak een back-up, vervang de map `househeating` volledig door de nieuwe versie en herstart Home Assistant. Installeer niet tegelijk de core-voorbereidingsversie en de custom-versie.

## 8. Bewuste beperkingen

Geen fabrieksreset, geforceerde compressor-/klepregeling, geforceerde ontdooiing, virtuele sensoren of onbeperkte raw-write-actie. Geen eigen stookcurve-, PV- of dynamische-prijsregeling: daarvoor zijn eerst bewezen basisbediening en aparte automations nodig.

Vanaf v0.2.0 zijn ook `climate` en `water_heater` beschikbaar. Verwarming uit behoudt actief warmwater; warmwater uit behoudt actieve ruimteverwarming of koeling. De globale schakelaar blijft de hele pomp bedienen. De boilerentiteit is alleen beschikbaar met een geldige boilermeting en bevestigde warmwaterfunctie. Zone 2 heeft nog geen eigen bediening.

Ventilatorsnelheid blijft ruw weergegeven. Waterdebiet gebruikt L/min, onderbouwd door lopende parameter 25 op PDF-pagina 160 en register 0x0058 op PDF-pagina 167. Het elektrische vermogen is de door de pomp gerapporteerde waarde, niet een gegarandeerd geijkte meting. De energieteller is niet als gevalideerde `total_increasing`-sensor aangemerkt en is daarom nog niet voor het energiedashboard bedoeld. Er is geen berekende COP.

## 9. Diagnostiek verzamelen

Open de integratiekaart en kies **Diagnostische gegevens downloaden**. Het rapport bevat registerwaarden, firmware/protocol, gebruikte schalen, fouten per extra groep en de laatste schrijfbevestiging. Hostnaam/IP en het seriële apparaatpad worden uit foutteksten verwijderd. Controleer een rapport altijd zelf voordat je het publiek deelt.

## 10. HACS en broncode

Volg [README.md](README.md) voor HACS-installatie en updates. Alle runtimebestanden, inclusief de eigen bibliotheek, vertalingen en brand-iconen, staan onder `custom_components/househeating`. De Core-map is alleen ontwikkelvoorbereiding.
