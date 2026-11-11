# Broken Expectation

`formula_id`: `broken-expectation`

Open on a failure the viewer has had or can reproduce in ten seconds. Blame two wrong suspects, then name the real mechanism and close on the phrase the title used.

## Length

130 to 200 words across every segment's `voice`. Stay inside the band: the beats below are sized for it.

## Beats

In this order. A share is the part of the script's words the beat covers; hold each within a few points.

| Beat | Share of the script | Its job |
|---|---|---|
| The symptom | 0 to 15% | The exact input and the wrong output, with real values, happening to the viewer. |
| Wrong suspect 1 | 15 to 25% | The obvious thing to blame. |
| Wrong suspect 2 | 25 to 32% | The next thing to blame. It happens there too. |
| Turn | 32 to 38% | One short sentence: nothing is broken, the tool is answering a different question. |
| Mechanism | 38 to 78% | Two or three facts, each with a number or a named part. |
| Root cause | 78 to 93% | One sentence the viewer can repeat. |
| Callback | 93 to 100% | The title's phrase, now explained. A one-line fix may follow, because it is the payoff. |

## Openings

Draft one opening from each of three shapes. The type goes in `hooks[].type`.

| Type (`type`) | Shape |
|---|---|
| The viewer's problem (`problem`) | You [did one small thing]. And [tool] insists you [did something else]. |
| Belief, then break (`myth`) | [Tool] can obviously [do X]. Try [a tiny test anyone can run] and you get [the wrong result]. |
| Question (`question`) | Why does [tool] report [wrong-looking thing] when all you did was [small thing]? |

## What holds the viewer

One question (why did it fail?) held until the root cause. Every beat is joined to the next by 'but' or 'so'. The two wrong suspects are the re-openings; the viewer's own objection, spoken aloud, can be a third.

## Ending

The callback to the title's phrase, or the general rule the case stands for. A one-line fix is allowed.

## Pitfalls

- Naming the mechanism in the first sentence
- A symptom the viewer cannot picture or reproduce
- Three or more mechanisms: one failure, one cause
- A callback that opens 'And that's why' or 'So that's how': it reads as a recap. State the title's phrase as a plain sentence

## Template

The shape of the whole script with the facts left out. Fill it with this topic's facts; never keep its wording.

> You [did one small thing]. And [tool] [reports something that looks wrong]. So you blame [the obvious suspect]. But [the second suspect] does it too. [Tool] is not broken. It [answers a different question]. [Fact with a number]. [Fact]. [Fact]. The real cause: [one sentence]. That is why [the title's phrase]. [One-line fix].
