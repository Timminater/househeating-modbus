# Energiemonitoring — HouseHeating Modbus 0.4.0

## Aanvulling 0.4.0

Externe thermische vermogensbronnen en langere rendementsperioden zijn nu
beschikbaar. De bestaande elektrische opties en gezamenlijke geldigheidsregels
blijven behouden. De externe warmtemeter levert signed W/kW; warmte-energie
wordt daaruit geïntegreerd. Een cumulatieve thermische kWh-teller wordt niet
als primaire bron behandeld. De hydraulische schatting kan naast de gekozen
meterbron zichtbaar blijven. Zie [FUNCTIES.md](FUNCTIES.md).

Deze optionele uitbreiding is softwarematig getest tegen Home Assistant 2026.10.1.
Werking op een fysieke warmtepomp is nog niet gevalideerd. Alle
warmtewaarden en rendementen zijn schattingen, geen geijkte warmtemeting of SCOP.
Bestaande entiteiten, hun unique IDs, configuratie en schrijfbeveiliging blijven behouden.
Monitoring opent geen eigen Modbus-client en schrijft geen warmtepompregisters.

## Inschakelen en bronnen kiezen

Na een afzonderlijk geautoriseerde installatie: open **Instellingen → Apparaten &
diensten → HouseHeating Modbus → Configureren → Energiemonitoring**. Monitoring
staat standaard uit, ook bij bestaande installaties. Het afzonderlijke
bedieningsformulier behoudt de eerdere vrijgave en apparaatfingerprint.

1. Schakel monitoring in en kies de elektrische bron.
2. **Modbus**: integreer `input_power`, register `0x005C / 100`, in kW.
3. **Extern**: selecteer een vermogenssensor met device class `power`, in W of kW.
   Optioneel kan daarnaast een cumulatieve sensor met device class `energy`,
   in Wh of kWh, de primaire elektrische energie leveren. Zonder teller wordt
   het externe vermogen geïntegreerd. Eigen afgeleide HouseHeating-sensoren
   kunnen niet als invoer worden gekozen.
4. Bevestig pas na controle van de actuele firmware de temperatuurschaal en
   debietschaal. Zonder bevestiging blijft thermische monitoring onbeschikbaar;
   elektrische energie kan al worden bijgehouden.
5. Vul eventuele kalibratie en vloeistofeigenschappen in. Die wijzigen alleen
   de berekeningen, nooit de originele gerapporteerde waarden of setpoints.

`reported_energy` (`0x005D`) blijft een gerapporteerde apparaatwaarde in kWh,
zonder state class. Resolutie, schaalverschillen tussen firmwares, resets en
overloop zijn niet op hardware bewezen. Deze waarde wordt daarom niet
automatisch als betrouwbare primaire energieteller gebruikt.

De elektrische meetgrens bepaalt het rendement: controleer of compressor,
circulatiepompen, hulpverwarming en andere verbruikers binnen de gekozen bron
vallen. Een bron die alleen de compressor meet geeft een andere systeemgrens
dan een meter voor de volledige installatie. Leg die keuze zelf vast.

## Formule en instellingen

```text
ΔT [K] = T_uit − T_in + ΔT_correctie
P_thermisch [kW] = debiet [L/min] × dichtheid [kg/L]
                   × soortelijke warmte [kJ/(kg·K)] × ΔT / 60
```

Bij 20 L/min en ΔT 5 K volgt circa 6,97 kW met dichtheid 1 en soortelijke
warmte 4,18. Dit is een waterbenadering. Temperatuurafhankelijkheid en
sensorafwijkingen zijn hiermee niet automatisch gecorrigeerd.

| Instelling | Standaard | Betekenis |
|---|---|---|
| Maximale meetleeftijd | max(90 s, 2,5 × scaninterval) | Afzonderlijk per echte uitlezing/bronrapportage |
| Maximale hydraulische tijdspreiding | 5 s | Tussen begin/einde van de drie bronuitlezingen |
| Debietfactor | 1 | Factor op de ruwe debietwaarde voor berekeningen |
| ΔT-correctie | 0 K | Verschilcorrectie, zonder de originele temperaturen te wijzigen |
| Dichtheid | 1 kg/L | Handmatig, passend bij vloeistof en referentietemperatuur |
| Soortelijke warmte | 4,18 kJ/(kg·K) | Handmatig, passend bij vloeistof en referentietemperatuur |
| Vloeistofreferentie | Water approximation | Vrije omschrijving, bijvoorbeeld fabrikant en referentietemperatuur |
| Minimaal vermogen voor momentaan rendement | 0,05 kW | Lager vermogen telt wel mee in de energie |
| Externe tellerresolutie | 0,001 kWh | Werkelijk kleinste stap van de gebruikte teller |
| Plausibiliteitsplafond | 30 kW | Vermogen en gemiddeld vermogen bij tellerdelta's |

Voor water/glycol: gebruik dichtheid en soortelijke warmte uit fabrikantgegevens
bij een passende temperatuur. Noteer mengsel en referentietemperatuur in de
vloeistofreferentie. Er is geen automatische glycolpercentageberekening en geen
toegezegde meetnauwkeurigheid. Het gecorrigeerde debiet moet binnen 0–100 L/min
liggen; 0 is geldig bij stilstand, een ontbrekende temperatuur is geen nul.

## Energie, COP en koeling

Vermogen wordt met de trapeziumregel tussen opeenvolgende geldige monsters
geïntegreerd. Een tekenwisseling wordt bij nul gesplitst: afgegeven en
onttrokken warmte blijven afzonderlijk beschikbaar. Netto warmte is afgegeven
min onttrokken energie en kan afnemen.

Elektrische totaalenergie loopt onafhankelijk van geldige hydraulische
metingen door. Rendement gebruikt uitsluitend tijdsintervallen met geldige
warmte én bijbehorende elektrische energie. Dag-/maand-COP is netto gepaarde
verwarmingsenergie gedeeld door gepaarde elektriciteit, nooit het gemiddelde
van momentane COP. Bij constant 6 kW warmte en 2 kW elektrisch gedurende een
uur resulteert 6 kWh / 2 kWh = COP 3.

In verwarmings-/warmwatermodi vermindert negatieve warmteoverdracht de netto
verwarmingsenergie, ook tijdens ontdooien. Momentane COP is dan onbeschikbaar.
Het nog te bevestigen ontdooibit is alleen diagnostisch. Zuivere koeling
krijgt afzonderlijke gepaarde koelenergie en EER. Gemengde koeling/warmwater
en onbekende modi tellen niet mee voor COP/EER; gemeten hydraulische energie
blijft zichtbaar. Een functiewisseling tussen twee monsters sluit dat hele
interval uit van rendement.

Perioderendement verschijnt pas bij positieve nuttige energie en minimaal
0,01 kWh gepaarde elektriciteit. Met een externe teller geldt het hoogste van
0,01 kWh en tienmaal de opgegeven tellerresolutie.

## Dekking en kalenderperioden

Dag en maand volgen de Home Assistant-tijdzone, met correcte dagen van 23 of
25 uur. Verstreken tijd en integratie gebruiken UTC en controle op monotone
tijd. Vermogensintervallen worden bij kalendergrenzen gesplitst.

COP- en EER-dekking tonen afzonderlijk het percentage van de verstreken
kalendertijd met bruikbare gepaarde verwarmings- respectievelijk koelmetingen.
Een stilstaande installatie met geldige verwarmingsmetingen kan dus wel
verwarmingsdekking hebben; dekking is geen compressorlooptijd of
nauwkeurigheidspercentage. De periodieke sensoren geven ook verstreken,
gepaarde en uitgesloten seconden, uitsluitingsredenen en kwaliteitsmarkeringen.
Een halverwege begonnen periode heet `partial_period`. De laatst afgesloten
dag en maand blijven in diagnostiek en als attribuut bij het rendement staan.

Bij een externe teller moet het **hele tellerinterval** geldige warmtegegevens
en een betrouwbare functie hebben. Een delta over een dag-/maandgrens wordt
voor de betreffende perioden uitgesloten; de volledige delta blijft wel in
het elektrische totaal. Elektrische dag-/maandenergie kan hierdoor lager
zijn dan het verschil tussen twee levensduurtotalen. De markering
`counter_boundary_unallocated` maakt dit zichtbaar. Er wordt geen onbekende
tellerdelta willekeurig over de twee perioden verdeeld.

## Gaten, resets en opslag

- Oude, ontbrekende, herstelde, ongeldige of niet-eindige waarden worden nooit
  stilzwijgend nul. Een timer maakt verouderde metingen onbeschikbaar, ook
  wanneer geen nieuwe Modbus-uitlezing binnenkomt.
- Per registergroep blijven de werkelijke leestijden bewaard. Een nieuwe
  globale snapshot maakt een oude of mislukte groep niet vers. Monitoring
  kan ontbrekende debiet-/vermogens-/tellerregisters afzonderlijk lezen via
  dezelfde gedeelde unit en dezelfde bloklimieten en busrust.
- Externe bronnen gebruiken `last_reported`, ook bij identieke waarden.
  Na opstart is een nieuwe daadwerkelijke rapportage vereist. Oude herstelde
  states worden genegeerd.
- Bij een dalende externe teller wordt geen negatieve consumptie of overloop
  aangenomen. Twee consistente lagere rapportages bevestigen een nieuwe
  baseline. Het onzekere interval telt niet mee.
- Een positieve sprong boven het plausibiliteitsplafond plus een tolerantie
  van twee tellerstappen wordt geweigerd. De laatste geaccepteerde baseline
  blijft bewaard; incidenten zijn zichtbaar in diagnostiek.
- Totalen en periodeboekhouding worden per config entry via HA `Store`
  opgeslagen **voordat** nieuwe totalen worden gepubliceerd. Bij opslagfout
  blijven de laatste opgeslagen totalen zichtbaar en ontstaat geen
  integratiebrug over het onzekere interval. Onbruikbare opgeslagen schema's
  blokkeren herstel in plaats van zichtbare totalen stilzwijgend te wissen.
- Na herstart blijven totalen bestaan, maar begint vermogensintegratie met
  een nieuwe tijdsbaseline (`restart_gap`). Een geldige externe teller kan
  werkelijke elektriciteit over uitval herstellen; zonder warmtegegevens
  wordt die elektriciteit niet in het rendement opgenomen.
- Na wijziging van bron, kalibratie of andere monitoringinstellingen blijven
  totalen bestaan. Nieuwe baselines en `configuration_changed` markeren de
  overgang; er is geen terugwerkende correctie. Uitschakelen/verwijderen en
  later opnieuw toevoegen van dezelfde config entry is geen meetcontinuïteit.

## Entiteiten en statistiek

| Waarde | Eenheid | Device class | State class |
|---|---|---|---|
| Geselecteerd elektrisch en geschat thermisch vermogen | kW | power | measurement |
| Gekalibreerd debiet | L/min | volume_flow_rate | measurement |
| Temperatuurverschil | K | temperature_delta | measurement |
| Elektrische en thermische totalen | kWh | energy | total |
| Dag-/maandenergie en gepaarde energie | kWh | energy | total, met last_reset |
| COP / EER | dimensieloos | geen | measurement |
| Meetdekking | % | geen | measurement |

Totalen hebben geen periodieke reset. Netto warmte mag afnemen. Bestaand
elektrisch vermogen, gerapporteerde kWh en registeridentiteiten zijn behouden.
Afgeleide sensoren hebben eigen sleutels en labels met geschat/berekend waar
van toepassing. Diagnostiek bevat bronkeuze, correcties, werkelijke
registervensters, tellerincidenten, dekking en vorige perioden.

Losse Integral- en Utility Meter-helpers blijven bruikbaar voor aanvullende
dashboards. Ze vervangen niet de gezamenlijke geldigheidscontrole van de
gepaarde energieboekhouding in deze integratie.

## Validatiegrenzen

Zie [TEST_REPORT.md](TEST_REPORT.md) voor reproduceerbare controles. Fysieke
debietschaal, temperatuurkalibratie, tellerresets en de elektrische systeemgrens
vereisen afzonderlijke uitsluitend lezende praktijkvalidatie. De softwaretests
bewijzen geen nauwkeurigheid op een echte warmtepomp. Praktijktests en installatie in de productieomgeving zijn niet uitgevoerd.
