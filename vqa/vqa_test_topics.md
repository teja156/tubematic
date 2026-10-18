# VQA Test Topics

Twenty topics for exercising the VQA environment via `/vqa-new-video "<topic>"` — ten tech
explainers (mostly DIAGRAM-track: animation-driven, few or no generated images) and ten
mythology/lore topics (mostly PHOTO-track: named characters and specific dramatic moments, so
`generate_image` gets exercised on most scenes). Scored against the producibility rubric in
`agent_files/skills/tubematic-operator/SKILL.md` — every entry clears the ≥5 threshold.

Mythology entries also carry a "Names to verify" column: these are exactly the kind of proper
nouns most likely to need a `settings.pronunciation_lexicon` entry or an inline
`<respell as="...">` tag (see `docs/developer/08-scripting-and-voice.md#pronunciation`) — good candidates for
checking `tts_text.txt` (staged automatically by `/vqa-new-video`, see `vqa/README.md`) against
how they're actually spelled out for ElevenLabs.

---

## Tech explainers — DIAGRAM track

| # | Topic | Score | Track notes |
|---|---|---|---|
| 1 | How DNS resolves a domain name to an IP address | 8 | step-by-step resolver → root → TLD → authoritative; flow diagram |
| 2 | How TCP's three-way handshake establishes a connection | 9 | step-by-step SYN/SYN-ACK/ACK; classic before/after (closed → open) |
| 3 | How a TLS handshake negotiates an encrypted connection | 8 | step-by-step; flow diagram; countable exchange steps |
| 4 | How a load balancer distributes traffic across servers | 8 | before/after (overloaded single server → distributed); flow diagram |
| 5 | How BGP routes traffic between autonomous systems | 7 | flow diagram; more abstract, fewer countable elements |
| 6 | How a CDN caches content closer to users | 8 | before/after (slow origin fetch → fast edge fetch); step-by-step |
| 7 | How NAT translates private IP addresses to public ones | 8 | before/after; step-by-step; countable elements |
| 8 | How binary search finds an element in a sorted array | 9 | step-by-step; countable array elements; state-machine-like narrowing |
| 9 | How mark-and-sweep garbage collection reclaims memory | 8 | before/after (memory before/after collection); step-by-step |
| 10 | How a hash table resolves collisions (chaining vs. open addressing) | 8 | before/after; step-by-step; small countable table |

## Mythology & Lore — PHOTO track

| # | Topic | Score | Names to verify | Track notes |
|---|---|---|---|---|
| 1 | Krishna's counsel to Arjuna before the battle of Kurukshetra | 7 | Krishna, Arjuna, Kurukshetra | named characters; specific historic/legendary moment; real-legendary place |
| 2 | Bhishma's fall on a bed of arrows at Kurukshetra | 8 | Bhishma, Kurukshetra | named character; one dramatic moment; distinctive physical scene |
| 3 | Ravana's abduction of Sita in the Ramayana | 8 | Ravana, Sita, Lanka | named characters; dramatic moment; Ravana's ten heads as a distinctive creature |
| 4 | Hanuman's leap across the ocean to Lanka | 8 | Hanuman, Lanka | named character; one dramatic moment; real-legendary place |
| 5 | Odin's sacrifice of his eye at Mimir's well for wisdom | 7 | Odin, Mimir | named character; specific mythic moment; distinctive place |
| 6 | Thor's duel with the Midgard Serpent at Ragnarok | 8 | Thor, Jörmungandr, Ragnarok | named characters/creature; climactic dramatic moment |
| 7 | Icarus flying too close to the sun on wings of wax | 7 | Icarus, Daedalus | named character; one specific dramatic moment |
| 8 | Perseus beheading Medusa using his shield as a mirror | 8 | Perseus, Medusa | named characters; dramatic moment; distinctive creature |
| 9 | Aegon's Conquest — Aegon Targaryen's landing at the Blackwater | 8 | Aegon Targaryen, Balerion, Blackwater Rush | named character + dragon; specific historical moment |
| 10 | The Battle Above the Gods Eye, Dance of the Dragons | 9 | Rhaenyra Targaryen, Aemond Targaryen, Vhagar, Meleys, Gods Eye | named characters + dragons; climactic historical moment |

---

## Notes

- **Tech explainers should render with little or no `generate_image` spend** — the rubric's
  DIAGRAM track is exactly what `tubematic-scene-config` treats as animatable without a photo
  floor. Good set for exercising rendering/AI-review without burning image-gen budget.
- **Mythology entries will trigger `generate_image`** on most scenes — expect real Gemini/OpenAI
  image spend per video, not just ElevenLabs voicing cost. Under VQA-4 those scenes should classify
  **PHOTO**, not HYBRID: drama is a PHOTO signal, and an overlay has to earn its place separately.
- **The two tracks above are *topic* producibility tracks, not scene treatments.** A PHOTO-track
  topic is scored that way because it has real subjects in it; how each of its beats is *shown* is
  decided per-beat downstream by `tubematic-scene-config`.

### VQA-4 acceptance controls

The PHOTO-default rework (VQA-4) needs three runs, and these are the topics to use:

| Control | Topic | What must happen |
|---|---|---|
| **Positive** | Mythology #10, Battle Above the Gods Eye | Most or all image beats classify **PHOTO** — Ken Burns moves with typographic content, not arrows and labels. At most one HYBRID, and its handback line names what the overlay tells the viewer |
| **Negative (required)** | Mythology #4, Hanuman's leap across the ocean to Lanka | The one topic here that genuinely turns on *where* — a route across open water from one shore to another. At least one beat should still classify **HYBRID** with an anchored route overlay. This is the only planned run that exercises `ImageFX.project(u, v)`, which has never produced a pixel |
| **DIAGRAM** | Tech #8, binary search | Zero generated images and zero `read_image` calls — confirms nothing leaked into the DIAGRAM path |

Also watch, on the positive run, for the **over-correction in the other direction**: a video made
entirely of bare `KenBurnsImage` entries. `SKILL.md` caps those at half the video's scenes, but that
cap is self-enforced — `validate_job` cannot check it, same as the image floor.
- Highest-confidence single smoke test per category: **#8 (binary search)** for tech, **#10
  (Battle Above the Gods Eye)** for mythology — both score 9 and have unambiguous track
  classification.
- #9 and #10 deliberately share the Dance of the Dragons setting from different angles (the
  conquest that founded House Targaryen vs. the civil war that nearly ended it) — useful if you
  want two videos in the same "universe" to compare scene/character consistency across separate
  `generate_image` calls.
- Sanskrit/Norse/Greek names (Bhishma, Jörmungandr, Mimir, etc.) are the ones most likely to need
  a `pronunciation_lexicon` entry — check `tts_text.txt` after voicing rather than assuming
  ElevenLabs got them right.
