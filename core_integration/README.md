# Voorbereiding voor Home Assistant Core

**Deze map is geen installeerbare Core-release en geen gereedstaande pull request.** Installeer voor de praktijktest de custom-integratie.

De adapter is gelijk aan de custom-versie, maar importeert `househeating_modbus` als zelfstandig pakket. Het `version`-veld is uit het manifest verwijderd. De afhankelijkheid `househeating-modbus==0.1.0` is nog niet op PyPI gepubliceerd; daarom is dit alleen een ontwikkelbasis. Er is geen Core-wijziging, PyPI-publicatie of GitHub-pull-request uitgevoerd.

Voor een echte bijdrage zijn onder andere nodig:

1. De fabrikant-/firmwarevarianten op echte hardware bevestigen: schaal, grenzen, statusbits, gatewaygedrag en schrijfbevestiging.
2. Een onderhouden, publiek beschikbare apparaatbibliotheek publiceren en de exacte gepubliceerde versie in het manifest vastleggen.
3. Een verantwoordelijke maintainer/codeowner, integratiedocumentatie en merkinformatie toevoegen.
4. Echte Home Assistant-tests schrijven en uitvoeren voor setup, config-/options-flow, entiteiten, fouten, reconfigure, unload en diagnose. De meegeleverde contracttests zijn daarvoor geen vervanging.
5. Hassfest, lint-/typechecks en de relevante eisen van de Integration Quality Scale doorlopen.
6. De huidige register-/snapshotmodellen beoordelen met de maintainers; zo nodig migreren naar de `Component`-descriptorlaag uit `modbus-connection`.

`tools/vendor_library.py` genereert deze adapter uit de custom-versie. Bewerk voor gedeelde wijzigingen eerst de custom-versie; het script overschrijft deze gegenereerde map.
