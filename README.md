# LiveKid → Home Assistant (nieoficjalna integracja)

Integracja dla rodziców korzystających z **LiveKid** (dziennik przedszkolny, app.livekid.com).
Korzysta z tego samego API co aplikacja webowa i loguje się e-mailem i hasłem rodzica.
Każde dziecko z konta dostaje własne urządzenie w HA.

> Projekt prywatny, niezwiązany z LiveKid. Używaj tylko z własnym kontem rodzica.

## Instalacja
HACS → ⋮ → *Custom repositories* → `https://github.com/Dezeusik/ha-livekid` (Integration) → pobierz „LiveKid” →
restart HA → Ustawienia → Urządzenia i usługi → Dodaj integrację → **LiveKid**.
Domyślnie dane odświeżają się co 10 min, minimum to 5. Odstęp zmienisz w „Konfiguruj”.

Test bez HA: `curl -sL https://raw.githubusercontent.com/Dezeusik/ha-livekid/main/tools/test_login.py | python3 - twoj@email`

## Encje (dla każdego dziecka)
| Encja | Stan | Atrybuty |
|---|---|---|
| Status | `w przedszkolu` / `odebrany` / `nieobecny` / `nieobecność zgłoszona` / `jeszcze nie ma` | godziny, kto przyprowadził/odebrał, temperatura |
| Przyjście / Odbiór | godzina | kto |
| Posiłki dziś | liczba | nazwy i godziny (porcje, jeśli przedszkole je zaznacza) |
| Drzemka | „12:30–13:50” | wszystkie drzemki |
| Raport dnia | komentarz nauczyciela | notatki |
| Aktualności | tytul najnowszej | nieprzeczytane, lista |
| Galeria | tytul najnowszego albumu | liczba zdjęć, nieobejrzane |
| Wiadomości nieprzeczytane | liczba | ostatnia wiadomość |
| Ostatni rachunek | kwota w zł | opis, termin płatności, kategorie |
| Saldo | jak w aplikacji | – |
| Jadłospis | tytuł | link do pliku |
| Obecności w miesiącu | liczba dni | nieobecności, dni robocze |

Czujnik binarny **W przedszkolu**.

## Zdarzenia (do powiadomień)
`livekid_przyjscie`, `livekid_odbior` (z posiłkami, drzemkami i raportem), `livekid_raport_dnia`,
`livekid_aktualnosc`, `livekid_galeria`, `livekid_wiadomosc`, `livekid_rachunek`, `livekid_jadlospis`.
Każde zawiera `dziecko` i `przedszkole`. Przy pierwszym uruchomieniu zdarzenia nie są wysyłane.

```yaml
alias: LiveKid – odbiór
triggers:
  - trigger: event
    event_type: livekid_odbior
actions:
  - action: notify.mobile_app_TWOJ_TELEFON
    data:
      title: "🏠 {{ trigger.event.data.dziecko }} odebrany {{ trigger.event.data.godzina }}"
      message: >-
        {% if trigger.event.data.kto %}Odebrał(a): {{ trigger.event.data.kto }}{% endif %}
        {% for d in trigger.event.data.drzemki %}😴 {{ d.od }}–{{ d.do }} {% endfor %}
        {{ trigger.event.data.raport or '' }}
```
