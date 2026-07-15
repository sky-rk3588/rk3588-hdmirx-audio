# Kako poslati patch u Linux kernel — vodič običnog čoveka

Napisao sam ovaj vodič posle svog prvog mainline patcha (jul 2026), dok mi je
sve još sveže. Pre tri meseca sam učio šta je `git commit`. Ako sam ja mogao,
možeš i ti — a na srpskom ovakvog vodiča nije bilo, pa evo ga.

Živi dokazi da ovaj postupak radi:

- Kernel patch (DRM/Rockchip): <https://lore.kernel.org/dri-devel/20260714202850.40999-1-royalnet026@gmail.com/>
- RFC serija od 2 patcha (media): <https://lore.kernel.org/linux-media/20260715051939.64652-1-royalnet026@gmail.com/>

> **Najvažnija stvar u celom vodiču:** kernel NE koristi GitHub pull requeste.
> Patch se šalje **mejlom**, na mailing listu, komandom `git send-email`.
> Zvuči zastarelo — ali radi savršeno kad ga jednom podesiš.

## Šta ti treba

- Git commit sa tvojom izmenom (u bilo kom klonu kernel izvora — može i plitak,
  `--depth=1`)
- Gmail nalog (može i drugi provajder, ovde opisujem Gmail)
- **Pravo ime i prezime** — kernel traži da se patch potpisuje pravim imenom
  (Developer Certificate of Origin), pseudonimi ne prolaze
- 30 minuta za jednokratno podešavanje

## Korak 1: Jednokratno podešavanje (radi se samo prvi put)

### 1a. Instaliraj git-email

```bash
sudo apt install git-email
```

### 1b. Podesi git za slanje preko Gmaila

```bash
git config --global sendemail.smtpServer smtp.gmail.com
git config --global sendemail.smtpServerPort 587
git config --global sendemail.smtpEncryption tls
git config --global sendemail.smtpUser TVOJMAIL@gmail.com
git config --global sendemail.from "Ime Prezime <TVOJMAIL@gmail.com>"
git config --global sendemail.confirm auto
```

### 1c. Google App Password

Gmail ne prima običnu lozinku za slanje iz terminala — treba "lozinka za
aplikaciju":

1. Uključi 2-Step Verification na <https://myaccount.google.com/security>
   (ako već nije)
2. Idi na <https://myaccount.google.com/apppasswords>
3. App name: `git-send-email` → **Create**
4. Dobiješ **16 slova** — prepiši ih **bez razmaka** na sigurno mesto
   (prikazuju se samo jednom!)

Tu lozinku ćeš lepiti u terminal svaki put kad šalješ (ništa se ne prikazuje
dok lepiš — to je normalno).

## Korak 2: Pripremi patch

### 2a. Napravi patch fajl iz commita

```bash
git format-patch -1 HEAD
```

Dobiješ fajl `0001-naslov-tvog-commita.patch`. Za seriju od više commita sa
propratnim pismom:

```bash
git format-patch --cover-letter -3 -o patches/
```

pa u `0000-cover-letter.patch` popuni `*** SUBJECT HERE ***` i
`*** BLURB HERE ***` (šta serija radi, na čemu je testirana, šta pitaš
maintainere).

**Commit poruka mora imati:**

- Naslov u formatu podsistema: `drm/rockchip: dw_hdmi_qp: kratak opis` (pogledaj
  `git log --oneline` za taj fajl da vidiš kako drugi pišu)
- Objašnjenje ZAŠTO (ne samo šta) — i na čemu si testirao
- `Signed-off-by: Ime Prezime <mail>` na dnu (dodaje `git commit -s`)

### 2b. Proveri stil — checkpatch

```bash
perl scripts/checkpatch.pl --strict 0001-*.patch
```

(`scripts/checkpatch.pl` postoji u svakom kernel izvoru, a često i u
`/usr/src/linux-headers-*/scripts/`.) Cilj:
`0 errors, 0 warnings — ready for submission`. Popravi sve što prijavi.

### 2c. Nađi primaoce — get_maintainer

```bash
perl scripts/get_maintainer.pl 0001-*.patch
```

Izbaci tačan spisak: maintaineri (idu u To) + mailing liste (idu u Cc).
Ne izmišljaj primaoce — ova skripta je zakon.

## Korak 3: Probno slanje SEBI

**Nikad ne šalji na listu iz prve.** Prvo sebi:

```bash
git send-email --to=TVOJMAIL@gmail.com 0001-*.patch
```

- Na `Send this email?` → `y`
- Nalepi app password → Enter
- Očekuješ: `Result: 250`

Otvori svoj inbox i pogledaj: da li patch izgleda celo (poruka + diff)?

## Korak 4: Pravo slanje

```bash
git send-email \
  --to="Ime Maintainera <adresa>" \
  --to="Drugi Maintainer <adresa>" \
  --cc="lista@vger.kernel.org" \
  --cc="druga-lista@lists.infradead.org" \
  0001-*.patch
```

Za seriju: navedi sve fajlove (`0000-* 0001-* 0002-*`) — git ih sam poveže u
thread. Na prvo `Send this email?` ukucaj `a` (all) da pošalje sve odjednom.

Za par minuta tvoj patch je javno na <https://lore.kernel.org> — nađi svoju
listu (npr. `lore.kernel.org/dri-devel/`) i sačuvaj trajni link.

## Korak 5: Odgovaranje na review (VAŽNO!)

Odgovori maintainera stižu na tvoj mail. Kad odgovaraš iz Gmaila:

1. **Reply All** — uvek (lista mora da vidi razgovor)
2. **Plain text mode** — OBAVEZNO! U Gmail compose prozoru: tri tačkice (⋮)
   → "Plain text mode". **vger liste ćutke ODBIJAJU HTML mejlove** — bez ovoga
   tvoj odgovor nestaje u prazno.
3. **Piši ISPOD citata** (inline), ne iznad. Obriši nebitne delove citata,
   ostavi `>` linije na koje odgovaraš, ispod svake svoj odgovor.
4. **Kritika = uspeh.** Reviewer koji ti nabroji 5 problema ti je upravo
   poklonio spisak za v2. Zahvali, potvrdi šta je tačno, obrazloži šta nije,
   i reci šta ćeš popraviti. Tako se gradi poverenje.

Novu verziju šalješ kao `[PATCH v2]` (`git format-patch -v2`), sa spiskom
izmena ispod `---` linije (ne ulazi u commit poruku).

## Tabela zamki (sve sam ih lično zakačio)

| Zamka | Rešenje |
|---|---|
| Gmail odbija lozinku | Treba **App Password**, ne obična lozinka (korak 1c) |
| Odgovor "nestao" — niko ga ne vidi | Gmail je poslao HTML → uključi **Plain text mode** |
| Odgovorio si samo pošiljaocu | Uvek **Reply All** — lista mora u Cc |
| `y` umesto `a` kod serije | Ništa strašno — git pita za svaki sledeći mejl, samo nastavi |
| Pseudonim u Signed-off-by | Mainline traži pravo ime (DCO) — podesi pre slanja |
| Patch ne legne kod maintainera | Pre slanja proveri da se primenjuje na najnoviji kod (`git apply --check` na svežem checkoutu) |
| Niko ne odgovara nedelju dana | Normalno — sačekaj 1–2 nedelje pa pošalji ljubazan "ping" reply |
| Nisi siguran u dizajn | Pošalji kao `[RFC PATCH]` — tako pitaš za mišljenje pre finalne verzije |

## Mali rečnik

- **lore.kernel.org** — javna arhiva svih kernel mailing lista; tvoj patch tu
  dobija trajni link
- **DCO / Signed-off-by** — tvoj potpis da imaš pravo da doprineseš taj kod
- **RFC** — "Request For Comments"; pitaš za mišljenje, ne tražiš odmah merge
- **v2, v3...** — nove verzije patcha posle review izmena
- **Reviewed-by / Acked-by / Applied** — magične reči koje znače da napreduje

---

Srećno! Ako je ovaj vodič nekome pomogao da pošalje svoj prvi patch —
javi mi se, to mi je cela poenta.

*Igor (sky-rk3588), Orange Pi 5 Plus / RK3588 avanture*
