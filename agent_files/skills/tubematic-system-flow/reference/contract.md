# System Flow: the `props.systemFlow` contract

The one scene of a System Flow video:

```json
{"type": "generated", "source": "installed", "src": "SystemFlow",
 "startFrame": 0, "durationInFrames": <totalFrames>,
 "props": {"systemFlow": {"boards": [ <board>, ... ]}}}
```

## Board

| Field | Type | Rule |
|---|---|---|
| `startFrame` | integer | 0 for the first board; later boards within 2 frames of a word's `startFrame`, each at least 2 s long |
| `headline` | string | at most 40 characters; its last word is drawn in cyan |
| `pill` | string, optional | at most 24 characters, drawn in capitals |
| `nodes` | list | 1 to 9 nodes |
| `edges` | list | connects this board's nodes; no cycles; every node connected |
| `events` | list | every frame inside this board (from its `startFrame` up to the next board's) |

## Node

`{"id": "lb", "label": "Load Balancer", "icon": "load_balancer"}`. The id is 1 to 24 lowercase letters,
digits or underscores. The label wraps by words into at most 2 lines of 14 characters. Rows come from
the edges (a node nothing points to is on row 1; any other is one below the lowest node pointing to
it); at most 3 rows and 3 nodes per row. Within a row, the listed order is the left-to-right order.

## Edge

`{"from": "browser", "to": "lb"}`, named `"browser>lb"` in events.

## Events

| `type` | Fields | Rule |
|---|---|---|
| `node` | `node`, `at` | exactly one per node |
| `edge` | `edge`, `at` | exactly one per edge; `at` at least 8 frames after its source's `node` event; its target's `node` event no later than `at` + 30 |
| `packet` | `edge`, `at`, `reverse` (bool), `tone` | `at` at least 15 frames after its edge's event; travels 20 frames and must arrive inside the board |
| `focus` | `node`, `at` | after the node entered; lasts until the next focus |
| `chip` | `edge`, `at`, `text`, `tone` | after the edge has drawn; text 1 to 24 characters; shown about 2.5 s or until the next chip |
| `fault` | `node`, `at` | after the node entered; the node turns red for the rest of the board |

`tone` is one of `structure` (default), `relation`, `ok`, `fault`.

Every board but the last fades out over its final 6 frames; the last board ends on its final frame.
Each event must leave room before that: `node` 31 frames, or 6 + 2 per label character + 15 when that
is longer (the label types on), `edge` 30, `chip` 30, `packet` 20, `focus` and `fault` 15. Chips are
at least 30 frames apart and focuses at least 15, because each replaces the one before.

Between the board's start, its events and its end, no gap may exceed 3.5 seconds.

## The worked example

`example-config.json` is an 18-second, two-board video (536 frames at 30 fps), and
`example-timeline.json` is the timeline it was timed against. Its narration, with each word's start
frame:

> Your@6 browser@16 asks@30 DNS@40 for@49 the@58 address@67 of@81 the@89 site.@98 A@110 load@117
> balancer@127 then@142 picks@152 one@164 of@173 two@181 web@190 servers@199 to@213 answer,@221 and@235
> the@244 page@253 comes@263 back@275 to@285 your@293 browser.@303

> Attackers@326 try@342 the@351 same@360 path.@370 The@382 firewall@391 blocks@406 them,@419 and@431
> only@440 clean@450 traffic@462 reaches@476 the@490 server.@499

Every event sits on the word it illustrates. The browser enters on "browser", its connector to DNS
draws on "asks" and DNS lands on "DNS"; the request runs on "for the address" and the chip
`example.com` appears on "address". The reply comes back as reversed green packets on "comes back",
and the focus returns to the browser on its second mention. The second board starts at 326, on
"Attackers"; the attacker's packet is red, and the attacker turns red with a `BLOCKED` chip on
"blocks".
