<p align="center">
  <img src="assets/logo.png" alt="HouseHeating Modbus" width="180">
</p>

# HouseHeating Modbus — installatie en eerste ingebruikname

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Timminater&repository=househeating-modbus&category=integration)

**Versie 0.1.0 · experimentele praktijktestversie · doelmodel HH-C3-12**

Deze integratie is ontwikkeld tegen de gedeelde Modbus-API van Home Assistant Core 2026.10.1. Het pakket is ingesteld op minimaal die versie. De protocolcode en adapterlogica zijn met gesimuleerde antwoorden getest; een volledige Home Assistant-runtime en een echte warmtepomp zijn hier niet getest. Maak vooraf een Home Assistant-back-up.

## 1. Installeren

Pak `househeating_modbus_v0.1.0.zip` uit. Kopieer alleen de map `custom_components/househeating` naar de configuratiemap van Home Assistant, zodat dit bestand bestaat:

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

Er zijn 74 register-sensoren beschikbaar. De meeste technische en optionele sensoren zijn standaard uitgeschakeld. Open de entiteitenlijst van het apparaat en schakel alleen de relevante extra entiteiten in, bijvoorbeeld buffervattemperatuur, boilertemperatuur, protocolversie of elektrisch ingangsvermogen. Een aangemaakte entiteit betekent niet dat die meting bij jouw configuratie fysiek aanwezig is.

Basiswaarden worden standaard elke 30 seconden gelezen. Extra registers en curven worden elke 120 seconden gelezen. Elke aanvraag bevat maximaal 16 registers; de minimale busrust is 120 milliseconden. Dit zijn conservatieve startinstellingen, geen garantie dat elke controller/gateway daarmee probleemloos werkt.

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

Instellen gaat in hele graden Celsius. Standaardgrenzen: koeling 7–25 °C, verwarming 20–60 °C, vloerverwarming 20–45 °C, warmwater 20–65 °C. De plafonds voor verwarming, vloer en warmwater kun je in de opties verlagen. Het vloerplafond kan na controle tot de gedocumenteerde 60 °C worden verhoogd, maar dat is nadrukkelijk geen installatieadvies. Warmwater blijft in deze versie maximaal 65 °C, omdat de technische specificaties en de registertabel in de handleiding niet hetzelfde maximum vermelden.

Na een wijziging volgt een controle door teruglezen. Een niet-bevestigde opdracht levert een fout op en wordt door deze integratie niet automatisch opnieuw geschreven. Controleer bij een fout eerst de werkelijke toestand: een opdracht kan zijn uitgevoerd terwijl alleen het antwoord verloren ging.

Gebruik voor eerste tests een kleine setpointwijziging in de reeds gekozen modus. Voer geen snelle aan/uit- of verwarm/koelwisselingen uit om de integratie te testen. De softwarevrijgave is geen technische keuring van het hydraulische of elektrische systeem.

## 7. Storingen, herstarts en updates

Een mislukte basisuitlezing maakt het apparaat niet-beschikbaar; oude basiswaarden worden niet opnieuw als verse metingen gepresenteerd. Een mislukte extra registergroep maakt alleen die groep niet-beschikbaar. Als een firmware maar een deel van zo'n groep ondersteunt, is die groep in deze versie niet afzonderlijk onderverdeeld naar ondersteunde adressen. Schakel de extra groepen tijdelijk uit en gebruik de diagnostiek voor het maken van een passend profiel.

Met de knop **Alle waarden opnieuw uitlezen** kun je ook na een communicatiefout een nieuwe poging doen. Bij terugkeer van de verbinding worden optionele gegevens opnieuw gelezen. Niet elke tijdelijk stilgevallen verbinding wordt door de netwerklaag onmiddellijk ontdekt; de volgende aanvraag en de ingestelde time-out bepalen mede hoe snel uitval zichtbaar wordt.

Een Home Assistant-herstart leidt niet tot het terugschrijven van oude of lege instellingen. De pomp blijft bron van de huidige instellingen. Het wijzigen van de verbinding via **Opnieuw configureren** behoudt de apparaat- en entiteitsidentiteiten binnen dezelfde config-entry, maar vergrendelt bediening opnieuw. Verwijder de integratie niet om alleen een IP-adres te wijzigen.

Voor een nieuwe pakketversie: maak een back-up, vervang de map `househeating` volledig door de nieuwe versie en herstart Home Assistant. Installeer niet tegelijk de core-voorbereidingsversie en de custom-versie.

## 8. Bewuste beperkingen

Geen fabrieksreset, geforceerde compressor-/klepregeling, geforceerde ontdooiing, virtuele sensoren of onbeperkte raw-write-actie. Geen eigen stookcurve-, PV- of dynamische-prijsregeling: daarvoor zijn eerst bewezen basisbediening en aparte automations nodig.

De eerste versie gebruikt `switch`, `select` en `number`, niet een `climate`-entiteit die gecombineerde warmwater-/verwarmingsmodi onjuist zou kunnen weergeven. De volledige normale moduskeuze blijft zo intact.

Ventilator en waterdebiet staan bewust ruw weergegeven waar de registertabel onvoldoende zekerheid geeft over eenheid of schaal. Het elektrische vermogen is de door de pomp gerapporteerde waarde, niet een gegarandeerd geijkte meting. De energieteller is niet als gevalideerde `total_increasing`-sensor aangemerkt en is daarom nog niet voor het energiedashboard bedoeld. Er is geen berekende COP.

## 9. Diagnostiek verzamelen

Open de integratiekaart en kies **Diagnostische gegevens downloaden**. Het rapport bevat registerwaarden, firmware/protocol, gebruikte schalen, fouten per extra groep en de laatste schrijfbevestiging. Hostnaam/IP en het seriële apparaatpad worden uit foutteksten verwijderd. Controleer een rapport altijd zelf voordat je het publiek deelt.

## 10. HACS en broncode

Deze ZIP is direct handmatig installeerbaar. Het volledige project bevat daarnaast de map `custom_integration` als basis voor een eigen HACS-repository, inclusief `hacs.json`, eigen bibliotheek en tests. Er is in deze opdracht geen GitHub-repository of HACS-publicatie gemaakt. HACS-installatie wordt pas mogelijk nadat de inhoud van die map als repository is gepubliceerd en als aangepaste repository is toegevoegd.

De map `core_integration` is ontwikkelvoorbereiding, geen geaccepteerde of direct installeerbare Core-integratie. Zie de checklist daar voor pakketpublicatie, echte runtime-tests en verdere review.

## Repository en ontwikkeling

Deze repository bevat de custom-integratie direct onder `custom_components/househeating`,
zodat HACS deze kan installeren. Voeg `https://github.com/Timminater/househeating-modbus`
toe als aangepaste HACS-repository van categorie **Integration**.

De apparaatbibliotheek staat onder `device_library`, de Core-voorbereiding onder
`core_integration`. Deze laatste map is geen installeerbare of geaccepteerde Core-integratie.
Zie [REGISTERS.md](REGISTERS.md), [SOURCES.md](SOURCES.md),
[TEST_REPORT.md](TEST_REPORT.md) en [GEMINI_REVIEW.md](GEMINI_REVIEW.md).

Ontwikkelen met Python 3.13 of nieuwer:

```sh
python -m pip install pytest pytest-asyncio
python -m pytest -q tests
python -m pytest -q device_library/tests
python tools/vendor_library.py
python tools/package.py
```

De tests gebruiken testdoubles; ze bewijzen geen werking op een echte warmtepomp.
De oorspronkelijke v0.1.0-runtime is behouden. Alleen repositorymetadata en
ontwikkelpaden zijn aangepast. De Gemini-code is niet overgenomen.
