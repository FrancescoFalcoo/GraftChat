# Come funziona `core/`

Guida di studio al codice di `core/`: cosa fa ogni funzione, perché è fatta così e dove
viene usata. Le regole vengono da [DESIGN.md](DESIGN.md) (soprattutto §6, §7 e §14); qui
c'è il ragionamento che le collega al codice.

Per vedere tutto in azione su una conversazione di esempio:

```bash
python devtools/preview.py     # chiama ogni funzione del core e stampa il risultato
python -m pytest               # tutti i test
```

## 1. Il modello in quattro frasi

- Un **messaggio** conosce solo il messaggio che lo precede nello stesso thread
  (`parent_id`). Un thread è quindi una catena: radice → figlio → figlio.
- Il **main** è il thread con `branch_id = None`. Ogni **branch** è un altro thread, con il
  suo `branch_id`. Il primo messaggio di ogni thread ha `parent_id = None` (§14.1).
- Un branch è agganciato al main da un solo dato: `anchor_message_id`, più gli offset del
  passaggio selezionato. Nei messaggi del branch non c'è nessun riferimento al main.
- Quando un branch rientra, sul main compare un **merge node** (un messaggio con ruolo
  `merge`) e il branch ne salva l'id in `merge_message_id`. I **take-away point** sono
  righe separate, legate al branch.

Tutte le funzioni di `core/` sono **pure**: ricevono oggetti, restituiscono oggetti nuovi,
non toccano database né rete. Gli id e le date li passa chi chiama. Per questo si testano
senza preparare niente.

## 2. `core/tree.py`

| funzione | cosa fa |
|---|---|
| `thread` | Rimette in ordine i messaggi di un thread seguendo i `parent_id`. |
| `open_branch` | Crea un branch `OPEN` su `content[start:end]` di una risposta del main. |
| `merge_branch` | Restituisce il branch marcato `MERGED` su un merge node (§14.6). |
| `discard_branch` | Restituisce il branch marcato `DISCARDED`. |
| `pending_branches` | I branch senza decisione, cioè quelli `OPEN`. |
| `check_invariants` | Controlla l'intero stato di una conversazione. |

Una correzione fatta a `merge_branch`: se il main era vuoto, il messaggio d'errore leggeva
`main[-1]` e Python lanciava `IndexError` invece di `InvariantError`. Ora l'ultimo id si
legge solo se il main non è vuoto.

### `pending_branches(branches)`

Scorre i branch e tiene quelli con `status == OPEN`, nell'ordine in cui arrivano. Con la
macchina a stati di §14.5 (`OPEN → MERGED`, `OPEN → DISCARDED`, entrambi finali) "nessuna
decisione presa" e "`OPEN`" sono la stessa cosa. I branch vuoti sono inclusi (§14.8): sono
comunque una decisione in sospeso, anche se l'unica scelta possibile è scartarli.

La usa l'API per dire al frontend quanti branch mostrare nel banner "You came back from N
branches. Merge?".

### `check_invariants(messages, branches, points)`

Le altre funzioni controllano **un'operazione**. Questa controlla **tutto quello che è
salvato**: l'API la chiama prima di confermare ogni modifica, e se trova una violazione la
modifica viene annullata. Non restituisce niente; lancia `InvariantError` alla prima
violazione.

È divisa in quattro passi, in quest'ordine:

1. `_check_unique_ids`: nessun id ripetuto tra i messaggi, tra i branch, tra i punti.
   Va per primo perché gli altri controlli costruiscono dizionari per id, e un dizionario
   sovrascrive in silenzio un doppione.
2. `_check_messages`:
   - tutto appartiene a una sola conversazione;
   - il `branch_id` di ogni messaggio esiste. Un messaggio "orfano" non verrebbe mai
     trovato da `thread`, perché nessuno chiede quel branch;
   - i merge node stanno solo sul main;
   - il main e ogni branch sono una catena sola: basta chiamare `thread`, che già lancia
     errore se trova due radici, un bivio o un messaggio irraggiungibile.
3. `_check_branches`, per ogni branch:
   - l'anchor esiste, è sul main, è una risposta del modello, gli offset sono dentro il
     testo e `anchor_quote` è proprio `content[start:end]`. Sono le stesse regole di
     `open_branch`, ricontrollate sullo stato salvato. "Anchor sul main" è la regola
     profondità = 1;
   - `merge_message_id` c'è **se e solo se** il branch è `MERGED`;
   - se è `MERGED`: il merge node esiste, ha ruolo `merge`, è sul main; il branch non è
     vuoto (§14.2); il merge node viene **dopo** l'anchor nel main. L'ultimo controllo usa
     la posizione di ogni messaggio in `thread(messages)`: un branch non può rientrare
     prima del punto da cui è partito.
4. `_check_points`: il branch di ogni punto esiste, in qualunque stato sia (§14.9), e due
   punti dello stesso branch non hanno la stessa `position`.

Cosa **non** controlla, e perché:

- "`text_generated` non viene mai sovrascritto" (§14.7). La funzione vede una fotografia
  dello stato: non può sapere cosa c'era prima. La regola si applica dove si modifica un
  punto: l'API può scrivere solo `included` e `text_final`.
- "Da 1 a 6 punti" e "titoli di al massimo 5 parole" (§8). Sono richieste al modello che
  genera i take-away, non proprietà dei dati: le applica `api/takeaway.py`.
- Che il merge node sia la fine del main. Vale solo nel momento del merge
  (`merge_branch`); dopo, il main continua.

## 3. `core/context.py`

Trasforma l'albero salvato nell'elenco di messaggi che il modello riceve davvero. È il
pezzo che l'esperimento misura. Il risultato è un `Context` con una lista di
`ContextMessage(role, content)`, dove `role` è `user` o `assistant`. Non produce mai
messaggi `system` (§14.3).

### I due testi che l'app aggiunge

`render_merge_block(anchor_quote, points)` scrive il blocco di un branch mergiato:

```
[merged from branch on: «Comprimi le immagini e servile in WebP o AVIF»]
- Usa AVIF per le foto: a parità di qualità pesa meno di WebP.
- Fallback WebP via <picture> per i browser senza AVIF.
```

Entrano solo i punti con `included = True`, ordinati per `position`, con il testo
`text_final` (quello eventualmente modificato dall'utente). Se nessun punto è spuntato
restituisce la stringa vuota: è così che un merge senza punti "non inietta niente" (§14.4).

`render_anchor_note(anchor_quote)` scrive la frase che dice al modello di quale passaggio
parla il branch.

### L'idea centrale: i blocchi in attesa

Un merge node non è un messaggio per il modello. È un punto del main in cui "arrivano" dei
blocchi. Quei blocchi vanno messi **in testa al messaggio utente successivo**, ciascuno tra
i delimitatori `<context>` e `</context>` (§14.3, §14.10).

`_render` fa esattamente questo, scorrendo un thread già ordinato con una lista `pending`
di blocchi in attesa:

| messaggio incontrato | cosa succede |
|---|---|
| ruolo `merge` | i blocchi dei branch mergiati in quel nodo si aggiungono a `pending` |
| ruolo `user` | esce un messaggio `user` = blocchi in attesa + testo dell'utente; `pending` si svuota |
| ruolo `assistant` | esce un messaggio `assistant` uguale all'originale |

Svuotare `pending` dopo l'uso è ciò che garantisce che un blocco compaia una volta sola.

`_blocks_merged_at` sceglie i branch di un nodo: devono essere `MERGED` e avere
`merge_message_id` uguale all'id del nodo. Li scorre in ordine di id, così lo stesso stato
produce sempre lo stesso testo (serve per ripetere l'esperimento).

`_close` gestisce il caso limite: se alla fine restano blocchi senza un messaggio utente
dopo (il main finisce su un merge node, oppure il branch è vuoto), diventano un ultimo
messaggio `user` a sé. Buttarli via nasconderebbe al modello qualcosa che l'utente ha
scelto di riportare.

### `build_main_context(messages, branches, points)`

Prende `thread(messages)`, cioè solo il main, e lo passa a `_render`. I messaggi dei branch
non entrano mai: di un branch arriva al main soltanto il blocco dei punti spuntati. I branch
`OPEN` e `DISCARDED` non contribuiscono.

Esempio (è quello di `devtools/preview.py`). Main: domanda, risposta, merge node del branch
1, nuova domanda. Il modello riceve tre messaggi, e l'ultimo è:

```
<context>
[merged from branch on: «Comprimi le immagini e servile in WebP o AVIF»]
- Usa AVIF per le foto: a parità di qualità pesa meno di WebP.
- Fallback WebP via <picture> per i browser senza AVIF.
</context>

Ok, cosa faccio per prima cosa con le immagini?
```

### `build_branch_context(branch, messages, branches, points)`

Tre passi, come in §7:

1. Il main dalla radice fino all'anchor **compreso**, passato a `_render`. I take-away
   mergiati prima dell'anchor quindi si propagano; quello che è successo dopo l'anchor no.
2. La nota sull'anchor viene aggiunta a `pending`: finirà in testa al primo messaggio
   utente del branch.
3. I messaggi del branch, passati a `_render` con liste vuote di branch e punti.

L'**isolamento tra fratelli** viene dalla costruzione, non da un filtro: la funzione legge
solo il main fino all'anchor e il thread di quel branch, quindi i messaggi degli altri
branch non hanno modo di entrare. Se l'anchor non è sul main lancia `InvariantError`.

## 4. Dove l'API chiama il core

| quando | funzione del core |
|---|---|
| ogni risposta con lo stato della conversazione | `thread`, `pending_branches` |
| l'utente seleziona un passaggio e apre un branch | `open_branch` |
| l'utente scrive sul main / in un branch | `build_main_context` / `build_branch_context` |
| l'utente conferma il merge | `merge_branch` (una volta per branch, sullo stesso merge node) |
| l'utente scarta un branch | `discard_branch` |
| prima di confermare ogni modifica nel database | `check_invariants` |

Il codice è in [api/service.py](../api/service.py): carica lo stato da SQLite, chiama il
core, chiama il modello, salva il risultato. Non decide nessuna regola.

## 5. Domande che è facile ricevere

**Perché il primo messaggio di un branch ha `parent_id = None` e non l'anchor?**
Perché `parent_id` significa sempre "messaggio precedente nello stesso thread". Così
`thread` tratta main e branch allo stesso modo, senza casi speciali (§14.1).

**Perché i blocchi stanno dentro un messaggio utente e non in un messaggio `system`?**
Alcuni provider accettano il system prompt solo come parametro separato, e i messaggi
`system` a metà conversazione si comportano in modo diverso da un provider all'altro. Un
blocco delimitato dentro il messaggio utente funziona ovunque (§14.3).

**Perché `merge_branch` riceve tutti i messaggi?**
Per controllare dentro il core due regole che altrimenti finirebbero nell'API: un branch
vuoto non si mergia, e il merge node dev'essere la fine del main (§14.6).

**Cosa riceve il modello se mergio un branch senza spuntare niente?**
Niente: `render_merge_block` restituisce la stringa vuota e il blocco non viene creato. Nei
dati però il branch resta `MERGED`, perché serve per la cronologia e per l'esperimento
(§14.4).

**Un branch può vedere un altro branch?**
Solo attraverso un merge avvenuto prima del suo anchor: in quel caso vede i punti
riportati sul main, come li vede il main. Mai i messaggi dell'altro branch.

**Quanto costa costruire un contesto?**
È lineare nel numero di messaggi, moltiplicato per il numero di branch quando si incontra
un merge node. Per le dimensioni di una chat è trascurabile; la chiamata al modello costa
ordini di grandezza in più.

**Come so che l'app manda al modello proprio quello che il core costruisce?**
Ogni chiamata viene salvata in `llm_call_log.prompt_json` con i messaggi esatti, e i test
del backend confrontano quel testo con l'uscita di `core.context`.
