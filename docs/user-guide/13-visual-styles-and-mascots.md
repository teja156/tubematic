# Visual Styles and Mascots

A visual style decides how a video looks. A mascot is an optional character that reacts on screen
while the narration plays. You choose both when you approve a topic, and both are fixed from then on.

---

## What every video has

Whatever the style, a video is 1080×1920 at 30 frames a second, with a synthesised voiceover and
word-timed captions. A small "Made with tubematic.ai" mark sits in the top right
corner unless you turn it off on **Settings → Rendering**.

## The styles

| Style | What you get | Needs |
|---|---|---|
| **Auto** | The agent picks the style that suits the topic before it writes the script, or mixes treatments when no style fits. See [What Auto does](#what-auto-does) | Nothing |
| **Photo Explainer** | A dark canvas. Full-frame generated pictures of the real things the video is about, with slow camera moves. No drawn figures | Nothing |
| **Stick Explainer** | A white canvas. Black hand-drawn line art, with stick figures for roles such as "the user" or "an attacker" | Nothing |
| **Illustrated** | Generated cartoon or rendered characters that stay the same from scene to scene | An OpenAI key |
| **Bean Explainer (experimental)** | A bald cartoon character with a thick outline reacts pose by pose to the narration on a bright colour field, while props and short handwritten labels build up beside it. No images | Nothing |
| **Storybook Atlas (experimental)** | A vintage picture book told in chapters, each opened by a plaque over a hand-drawn room or landscape. A small mouse guide walks beside the story while its people, named by printed tags, and hatched objects arrive on the narrator's words. No images | Nothing |
| **Under the Hood (experimental)** | A dark canvas and close-up photographs of one physical object. Short capital labels point at its parts, gold arcs show fields and flows, numbers tick, and a cartoon presenter reacts in the bottom corner | An OpenAI key. Up to 12 generated photographs per video |
| **Case File Story (experimental)** | A suspense story in painted pictures that puts the viewer inside a scheme or a money dilemma. One blank-faced character stands in for the viewer, meters change with the plot, cards count the numbers out, and it ends on a choice between two buttons | An OpenAI key. Up to 16 generated pictures per video, and one reference picture |
| **Paper Diorama (experimental)** | A playful explainer in rooms of cut paper. A taped banner names each beat, paper props pop in on the narrator's words, a small clay critter reacts, and the captions are torn paper tags. No images | Nothing |
| **Editorial Collage (experimental)** | An evidence desk. Newspaper-style clippings with the video's own headlines, grey halftone prints, cut-out stickers, typed index cards and big figures, joined by a red string as the camera glides across the desk. Red pen, highlighter and stamps land on the key words | An OpenAI key. Up to 10 generated pictures per video |
| **Storybook Reveal (experimental)** | A picture book for a fable or a moral story. Each page is one painted picture that appears as a pencil drawing and then floods with colour, under a hand-lettered title. The hero looks the same on every page | An OpenAI key. Up to 12 generated pages per video, and one reference picture |
| **Archive and Engraving (experimental)** | A documentary page on parchment. Engraved plates in museum frames, a serif title with one red word, red strike-throughs, stamps, routes on old charts and a timeline. People appear as name cards, never as faces | An OpenAI key. Up to 10 generated engravings per video |
| **Puppet History (experimental)** | Round-headed cut-out puppets in era costumes act out "you are now a..." history on flat sets, document cards with stamps and struck-out numbers, and maps of today's countries, with hard cuts between scenes. No images | Nothing |
| **Mid-century How-To (experimental)** | A 1950s classroom-film cartoon. A gloved presenter walks you through a task in numbered steps, each on its own flat colour, pressing buttons on phones, keypads and other flat objects, with checks, circled numbers and a closing card that lists the steps. No images | Nothing |
| **Comic Panels (experimental)** | A comic page builds up panel by panel on cream newsprint, with a hero, a villain, speech balloons and sound effects like POW. The camera moves from panel to panel and pulls back to the whole page. No images | Nothing |
| **Process Cast (experimental)** | Little drawn characters with faces, such as a packet, a cell or a byte made of cubes, act out an invisible process at stations along one ground line. They carry task cards, split and join up, and the camera glides between stations. No images | Nothing |
| **Cartoon 3D (experimental)** | Inked cartoon characters in a painted 3D world, with a moving camera | A renderer with a working NVIDIA GPU |
| **Low-Poly Skit (experimental)** | Toy people made of flat-shaded shapes act out a story in small 3D dioramas, with a new shot about every second, a camera jolt on every footstep and hit, and crowds of hundreds. The captions turn yellow word by word. No images | Nothing |
| **Flat Vector Science (experimental)** | Flat glowing creatures, cells and planets drift on a dark backdrop, named by pills whose words light up as they are spoken. Shots show scale: a dive through the ocean, a ladder of sizes, a zoom by powers of ten. No images | Nothing |
| **Isometric Infographic (experimental)** | A small isometric world of flat blocks on cream paper. One thing travels a route that draws ahead of it, buildings drop in, pins name places with a number, and a counter keeps the running total. No images | Nothing |
| **Night Signal (experimental)** | A calm warning told in glowing white pictograms on black, with the one danger in red: a stranger at the door, a doorbell camera, a phone screen, RULE cards and a card of steps. Scenes change through short glitches. No images | Nothing |
| **Whiteboard** | One big white board. A floating marker writes and draws each step just after the narrator says it, and the camera glides between parts of the board. It ends on the whole board, each part numbered. No people and no images | Nothing |

Photo Explainer, Stick Explainer and Illustrated set the canvas and how people are drawn. They do not limit what a scene can show. A Stick
Explainer video still draws a process as a diagram, and still shows a generated image for a real
place or person, inside a panel on the white canvas.

The canvas is the same for the whole video. A video that switched between a dark and a white
background would flash, and a viewer reads that as a broken render.

### Picking one

- Choose **Auto** when you have no preference.
- Choose **Photo Explainer** for real, specific things the viewer came to see: products, buildings,
  artworks, machines, named people and places, or a real event and the machine or company it
  happened to.
- Choose **Stick Explainer** for a process acted out by generic people in roles: what a user clicks,
  what an attacker tries, how a kitchen team gets an order out, what a rescuer does in CPR. It also
  suits how a system works, such as a request crossing a network, with its parts acting as roles.
- Choose **Illustrated** when the video follows the same characters through several scenes. Each new
  pose is one more OpenAI image call, so this style costs more per video than the two above.
- Choose **Bean Explainer** for relatable, conversational topics: habits, health, money mistakes,
  how people behave, and "every X explained" lists, where each item gets its own section. The props
  come from a fixed library of everyday objects, so it suits subjects a phone, a coin, a clock or a
  sign can stand for better than specific real products or places. It is experimental.
- Choose **Storybook Atlas** for the story of an invention, a discovery or an idea: how the first
  program was written, where a word or an everyday thing came from, a person from history and what
  they made. The script is written as a calm story in three to five chapters, and people appear as
  picture-book figures recognised by their name and clothes, never by their face. It suits history
  better than a list of tips or a mechanism explained part by part. It is experimental.
- Choose **Under the Hood** for how one physical thing works inside: a touchscreen, a battery, a
  lock, an SSD, a fridge, or the price of a part. The script goes one layer deeper per scene and
  quotes real numbers, which become labels, counters and charts. Each photograph is an OpenAI image
  call, up to 12 per video, so it costs more per video than the styles without images. It is
  experimental.
- Choose **Case File Story** for how a fraud, a scam, money laundering or a heist works, or for a
  money dilemma: found money, an offer that is too good, a rule someone is about to break. The
  script is a suspense story told to the viewer as "you". It names what happened and what the law
  calls it, then ends on a choice between two options. Its people are invented, so it does not suit
  a real, named case. A scheme is explained the way a news report would explain it, and it always
  ends found out or named as a crime. Each picture is an OpenAI image call, up to 16 per video and
  one more for the character's reference picture, so it costs more per video than the styles
  without images. It is experimental.
- Choose **Paper Diorama** for a tech, product or safety idea told playfully inside one familiar
  place: a password manager as a bank vault, cafe Wi-Fi in a diner, two-factor login as a second lock.
  Plain paper props stand in for the idea (a note for your data, a padlock for encryption) and the
  script is light and warm. It suits one idea with a before and after better than a list of tips or
  a process walked through step by step, and it never shows real products, logos or people. The props
  come from a library of paper models, and the agent builds any it lacks from paper shapes. It is
  experimental.
- Choose **Editorial Collage** for a real incident, breach, outage or market event told as an
  investigation: what happened when, the documents, the numbers, and how it spread from one company
  or person to the next. Real people are named in the headlines and never shown as faces, every
  grey print carries a small "Illustration" note, and a card that copies a real document says
  "Recreation". For a real place or machine the viewer came to see as pictures, Photo Explainer fits
  better. Each picture is an OpenAI image call, up to 10 per video. It is experimental.
- Choose **Storybook Reveal** for a fable, a myth, a parable or a small story about one character that
  ends on a lesson, such as a habit that grows or a kindness repaid. The script is told as a calm tale
  in a few pages. The agent first makes a reference picture of the hero, so the hero looks the same on
  every page. It does not suit real history (Storybook Atlas and Archive and Engraving fit that) or a
  list of tips. Each page is an OpenAI image call, up to 12 per video and one more for the hero's
  reference picture. It is experimental.
- Choose **Archive and Engraving** for history told seriously: how an old belief was overturned, an
  idea passed from one thinker to the next, a voyage on old maps, the history of a market or an
  invention told as a documentary. A real person appears as a name card with their dates and an
  emblem, never as a picture of their face, and every picture carries a small "Illustration" note so
  no one takes it for a real archive print. A card that copies a real document says "Recreation".
  For a light story of how an everyday thing was invented, Storybook Atlas fits better. Each plate is
  an OpenAI image call, up to 10 per video. It is experimental.
- Choose **Puppet History** for history told to the viewer as "you": a job, a rank or a rule in a
  past era, such as a Roman legionary's twenty-five years or a week as a medieval peasant, why an
  event happened told with light humour and a reversal at the end, or an army's march or a trade
  route across a map. The script puts you in the era with a job, gives each beat one change, and
  builds to a twist the picture can show, such as a costume swapped or a number struck out. A real
  person appears only as the same puppet in a generic costume of their era with their name on a
  plate, so the puppet never looks like them. Living people, leaders of a regime still in power and
  tragedies are left out. Maps show today's countries, so a historical region is named by the modern
  countries it covers. A calm history of an invention suits Storybook Atlas better. It is experimental.
- Choose **Mid-century How-To** for a task the viewer can copy in a few steps: turning on a
  setting, securing an account, backing up a phone, checking a link before clicking it. The script
  opens on why the task matters, then numbers each step aloud and names what to tap, type or turn
  on. It suits a procedure better than a list of separate tips, how something works inside, or a
  story. It is experimental.
- Choose **Comic Panels** for a fight or a showdown told round by round: a defender against an
  invader, such as your password against a guessing attack or an antibiotic against a superbug, an
  arms race where each side answers the other's move, or a short punchy story with an invented hero
  and villain. The script sets the scene in a line, gives each round one move and one answer, and
  writes a few short lines for the characters to say, which the video shows as balloons and the
  narrator never reads out. A process with no fight in it suits Process Cast better, and a process
  acted out by people in roles suits Stick Explainer. The characters are invented and never look
  like a real person. It is experimental.
- Choose **Process Cast** for an invisible process whose actors are things: bits adding up to a
  byte, cells and organs at work, the layers of a system met one by one, a build passing through
  named stages. The script names each part once and keeps calling it by that name, because each part
  becomes a character with that name on its tag, and it moves the story from one place to the next.
  A process acted out by people in roles, such as a user and an attacker, suits Stick Explainer
  better. The characters are the style's own cast and have nothing to do with mascots. It is
  experimental.
- Choose **Cartoon 3D** for a story told by characters on a 3D set. It is experimental.
- Choose **Low-Poly Skit** for a what-if told to "you" as a chain of consequences that grows with each step, such as
  what happens if everyone jumps at once, or if you dug through the Earth: one small set per sentence, a crowd or a planet as the
  payoff. It is playful, fast and experimental. It does not suit a real, named person or product, or a diagram of how something
  works.
- Choose **Flat Vector Science** for size and scale in nature and space: how deep the ocean goes, how
  big a star is, what happens to your body somewhere extreme, how a virus copies itself. The script
  asks one question and answers it with numbers that carry units, each compared with something
  familiar. Its subjects come from a library of drawn creatures, organs, planets and objects, and the
  agent can draw one more when the library lacks it. It is experimental.
- Choose **Isometric Infographic** for one thing's journey through a system of places: a parcel from
  a warehouse to your door, water from a reservoir to your tap, power from a plant to your socket.
  The script follows the thing station by station and says the running number aloud. It suits
  places and routes better than a process acted out by people. It is experimental.
- Choose **Night Signal** for a warning: what to do, or never do, when a stranger, a call, a link or
  a knock at night is the danger, and safety steps for a bad moment. The script is a calm list of
  rules told to the viewer as "you". It suits a dark, serious tone only. It is experimental.
- Choose **Whiteboard** for an idea worked out step by step: a formula built up, money arithmetic
  such as interest or a percentage, an everyday chain of causes that ends in one picture, two ideas
  side by side. The script is written like a teacher at a board, one step per sentence, ending on one
  sentence that sums the idea up.

### What Auto does

When you approve a topic left on Auto, the agent picks a style before it writes the script, because
the script is written for the style: a Whiteboard script works an idea out one step at a time,
for example. It reads what each style is made for and avoids, compares that with the topic, and
picks the style that clearly fits. It considers every style this install can make: Illustrated only
while an OpenAI key is stored, Under the Hood, Case File Story, Editorial Collage, Archive and
Engraving and Storybook Reveal only while an OpenAI key is stored and the video has no mascot, Paper
Diorama, Puppet History, Mid-century How-To, Comic Panels and Process Cast only while the video has no
mascot, Cartoon 3D only while a GPU is working and the video has no mascot, Low-Poly Skit only while the video has no mascot.
It may pick a style that generates images, which costs more per video. It does not pick a style for
variety: the same kind of topic gets the same style every time.

The agent keeps **mixed scenes** when the topic needs two things no single style has, such as
full-frame pictures of a real bank next to stick figures acting out the run on it, or when no style
clearly fits.
A real event told through its pictures goes to Photo Explainer. So does a real
failure with a technical cause, such as a rocket lost to a software bug: the agent rules out any
style that cannot show the real rocket, however much of the topic is about a number or a line of
code. The agent then
chooses a dark or a white canvas for the whole video once the voice exists (dark when images carry
the video, white when roles, processes and diagrams do), and draws each part of the script in
whatever way suits it: an image, a diagram, line-art figures or generated characters. A mixed video can combine what the named
styles keep apart. One on a dark canvas can use line-art figures for "the user" and "the server",
which Photo Explainer leaves out. The agent uses generated characters only for a character the
viewer must recognise across scenes, and only while an OpenAI key is stored.

The video's window shows the choice under **Visual style**, after the word Auto: the picked style's
name, or Mixed scenes with its canvas once chosen. Until the agent has chosen, it reads
"Auto (not yet chosen)". The **Why this style** row gives the agent's reason and the runner-up, the
style that came second.

At Script Ready you can take the runner-up instead: **Switch to …** in the video's window sends the
video back to the agent, which picks the script's [formula](03-using-tubematic.md#script-formulas)
again and writes a new script for that style. The old script is discarded. For
a new video nothing has been paid for at this point; for a video you sent back for revision after it
was voiced, the new script is voiced again when you approve it. To give the style back to Auto entirely, request a revision of the
topic: a revised topic returns to Auto, and the agent picks again after you approve it.

A Bean Explainer video has a fixed look, so its pick is the whole decision: the agent picks the background colour, the character's
accessory and the props, and times every pose to the narration. When the library has nothing for an
object the video needs, the agent draws that prop itself in the same style and checks the drawing
before the video renders. A Whiteboard video is the same again: the agent picks what to write and
draw for each step from a fixed set of layouts and a library of simple drawings, times it to the
narration, and draws a simple one of its own, checked before use, when the library has nothing for
an object such as a bicycle.
A Storybook Atlas video works the same way too: the agent splits the narration into chapters, picks
each chapter's room or landscape, dresses the people of the story, and times every walk, object and
plate to the narration, drawing an object of its own when the library lacks one.

An Under the Hood video works the same way: the agent makes the photographs, looks at each one and
makes it again if it shows the wrong thing, pins the labels to the parts, and times the labels,
numbers and the presenter's poses to the narration. The presenter is the same character in every
video.

For a Case File Story video the agent first makes a reference picture of the character in the
clothes the story calls for, then makes each painting from it, so the character stays the same.
It looks at each painting and makes it again if the character changed or the picture shows the
wrong thing. It then chooses the meters and times the pictures, the cards and the two buttons to
the narration. The character's head is the same in every video.

A Puppet History video works the same way: the agent casts the puppets in costumes of the era, lays
the story out as a run of beats on sets, cards and maps, and times every entrance, pose, costume
swap, sign, stamp and map fill to the narration. The narrator stays off screen, so a puppet never
speaks. When the library has no hand prop the video needs, such as an hourglass, the agent draws one
in the same style and checks the drawing before the video renders.

A Mid-century How-To video works like a Bean Explainer one: the agent picks each step's colour, the
presenter's outfit and the objects, and times every gesture, press and check to the narration. The
presenter is the same character in every video, and he never moves his mouth to the words, because
the narrator is off screen. When the library has no object the video needs, such as a smoke alarm,
the agent draws one in the same style and checks the drawing before the video renders.

A Comic Panels video works the same way: the agent casts a hero, a villain and any invented people,
lays the story out as one to three comic pages of three or four panels, and times every panel, character,
balloon, sound effect and camera punch to the narration. The narrator stays off screen, so a balloon
is always a line a character says and never the narration read twice. When the library has no prop the
video needs, the agent draws one in the same style and checks the drawing before the video renders.

A Process Cast video works the same way: the agent casts each part of the process as a character,
picks its body, colour and name, sets up the stations, and times every entrance, hop, card, copy and
reaction, and every camera move, to the narration. Faces show feelings and never move to the words.
When the library has no prop the video needs, the agent draws one in the same style and checks the
drawing before the video renders.

### Insert scenes

An insert is a short scene, a few seconds long, in another look inside a video's style, where the
narration reaches something that look shows best. The video's style carries everything else: the
opening, the answer it builds to, and the ending. The captions stay on screen through an insert,
and the video goes back to its style right after it.

| Insert | What it shows |
|---|---|
| **System Flow** | A diagram of parts: components appear as line icons in boxes, connectors draw between them, and points of light travel along the connectors, for a request crossing a network or the steps of a protocol |
| **Terminal Doc** | Text as the picture: a password being hashed, letters scrambled into a cipher, a command typed and what it prints, a large number resolving out of noise |
| **Code Scenes** | A few lines of real code on an editor card: the lines being read light up, a bug gets a red squiggle and a message, the code changes into its fix, and a small pane shows what it prints |
| **Format Packs** | Phone-style formats: a made-up message thread with the scam's tells circled, a short numbered list, a quiz with a locked answer, or a news strap with a changing number |

Format Packs draws no real app or brand. The phone is a plain frame with no maker's look,
phone numbers come only from the ranges set aside for fiction, and every made-up message thread or
headline carries an EXAMPLE tag, so a still from the video cannot pass for a real screenshot. A
headline shown with its source is a quote from that source.

Code Scenes shows what a snippet prints only when the code makes it certain. Nothing runs the code,
so the AI review checks that output against the code and sends the video back when it does not match.

An insert follows the video's canvas, so on a white video it is drawn dark on paper. A Cartoon 3D
or Low-Poly Skit video takes no inserts.

The **Inserts** setting decides whether a video may have them. On **Auto** the agent decides, after
it picks the style and before it writes the script; many videos get none. On **None** the video has
none. The video's window shows the decision in the **Inserts** row, with the agent's reason, and the
Script tab marks each part of the script an insert shows.

Videos voiced before System Flow and Terminal Doc became inserts keep their whole-video look.

### Where you choose

| Where | What it sets |
|---|---|
| A topic waiting for approval, on its Quick Actions row or in its window | That video's style and its **Inserts** setting |
| The **New Video** page | The style and the **Inserts** setting of the video you are creating |
| **Edit defaults** on a domain's row on the **Topics** page | The style its curriculum topics arrive with, and the **Inserts** setting every new video in it starts with. You can still change both on each topic |

Once you approve the topic, the style and the **Inserts** setting are fixed.

Click the style field to open the list. **Auto** comes first, then the 2D styles, then the 3D
styles. A style marked **EXP** is experimental. A style marked **GPU** renders on a GPU only. A
style this install cannot make is greyed out, with the reason under its name.

![The visual style list open on the New Video page: the 2D styles, each with an eye button, with Whiteboard chosen and four styles marked EXP; under 3D, Cartoon 3D is greyed out with "needs a working GPU"; under Inserts, System Flow is greyed out because an insert style is never a whole video](../images/style-picker.png)

The eye button on a row plays a few seconds of that style in a window, with **Prev** and **Next**
to step through the others and **Use this style** to pick the one you are watching. Picking a style
there does not approve the topic.

![The preview window for Storybook Atlas: a still of the style's looping preview on the left, and on the right its name, the 2D and EXP tags, one line on what the style is for, Prev and Next, and Use this style](../images/style-preview.png)

At the bottom of the list, **Inserts** are styles used for a few seconds inside another style, such
as a diagram of a mechanism. You can watch their preview, and you cannot choose one for a whole
video.

After the topic is approved, the eye button beside **Visual style** in the video's window plays the
preview of the style the video uses.

### When a style is greyed out

A style the install cannot make stays in the list, greyed out, with the reason under its name:

- **needs an OpenAI key** (Illustrated, Under the Hood, Case File Story, Editorial Collage, Archive
  and Engraving, Storybook Reveal): no OpenAI key is stored.
  Add one on **Settings → API Keys**.
- **needs a working GPU** (Cartoon 3D): no renderer has passed its GPU test. See
  [GPU Rendering](10-gpu-rendering.md).
- **GPU not tested yet** (Cartoon 3D): the renderer has not finished its first test. Wait a minute,
  or press **Test GPU** on its card under **Settings → Rendering**.

A topic that already holds a greyed-out style cannot be approved until you pick another.

A Cartoon 3D video renders on a GPU only. If the GPU stops working after you approve the topic, the
video fails with a comment saying why. See
[GPU Rendering](10-gpu-rendering.md) for how to check the GPU.

---

## External styles

An external style is a visual style made outside Tubematic's releases: by you with an agent, by
someone else who shared it as a zip file or a git repository, or published in the Tubematic
gallery. Once installed it appears in every style list with an **EXTERNAL** tag and works like the
other styles. It takes no mascot and no insert scenes.

A style package is code. It runs in the renderer's browser whenever a video in that style renders,
and your agent reads its guide while it writes the video. Tubematic does not sandbox it, so install
a style only from someone you trust. Styles in the Tubematic gallery were reviewed by a person before
they were published, and their install screen says **REVIEWED**; a zip, a repository or another
gallery address was not.

### Installing a style

Open **Profiles → Styles**. Then:

- **Gallery** lists the reviewed styles. Press **Install** on one.
- **Install from file** takes a zip of a style package.
- **Install from repo URL** takes a git repository's https address and a commit or a tag. Name a
  commit or a tag: a branch can change after you looked at it.

Nothing is installed yet. The install screen opens and shows where the package came from, a warning,
the result of Tubematic's checks, a scan of its code and guide, every file (click a text file to read
it), and the guide your agent will read. The scan lists anything worth a look, such as code that
reaches the internet. Read them. To install, enter your dashboard password and press **Install**. To
drop it, press **Discard**. A package you leave waits for 24 hours.

You can also ask your agent: `/tubematic-install-style ~/Downloads/my-style.zip` (or a folder, a
repository address with `@<commit or tag>`, or a gallery id). The agent reads the package, writes its
opinion onto the install screen and gives you the link. Only you can install it there, with your
password. Never give the agent your password.

### Sharing a style in the gallery

The Tubematic gallery is the GitHub repository
[teja156/tubematic-styles](https://github.com/teja156/tubematic-styles). To submit a style, open a pull
request there with the package folder, or with a pointer to your own repository at a commit; its
`SUBMITTING.md` says how. A maintainer reviews the code, the guide and the content against a written
checklist, and merging publishes it to every Tubematic's **Gallery** tab. The **Gallery** tab reads
the address in its **Gallery address** field; clear it to turn the gallery off.

### Using an external style

Pick it like any style for a video or as a domain's default. **Auto** never picks an external style
until you tick **Auto may pick it** on its row of the Styles page.

A package whose files change after you installed it (for example, edited by hand) shows as
unavailable with "its files changed after it was approved". Press **Review** on its row to see it
again and approve it with your password. A package you copy into `~/.tubematic-data/styles/` by hand
waits for the same review.

Installing a newer version of a style replaces the old one. Videos already queued with the old
version are not rendered with the new one: they go back for a fresh look first.

### Removing an external style

Press **Remove** on its row. It is refused while an unfinished video or a domain's default style
uses it; finish those videos or switch them to another style first.

---

## Mascots

A mascot is a small character that walks on and off screen and reacts to the narration. It looks
surprised, has an idea, hops, glances at something. It does not narrate and does not lip-sync.

Mascots are experimental and off by default. A video has one only if you pick it. They are drawn on
the GPU, so you can pick a mascot only while a renderer's GPU test has passed. Cartoon 3D, Low-Poly Skit, Under
the Hood, Case File Story, Paper Diorama, Editorial Collage, Archive and Engraving, Storybook
Reveal, Puppet History, Mid-century How-To, Comic Panels, Process Cast, Flat Vector Science, Isometric
Infographic and Night Signal videos cannot have one: Under
the Hood and Mid-century How-To have their own presenter, Case File Story its own lead character, Paper
Diorama its own critter and Storybook Reveal its own hero, Editorial Collage and Archive and Engraving
are serious documentary pages a cartoon character would not suit, and Puppet History, Comic Panels and
Process Cast have a whole cast of drawn characters that a mascot would be confused with. Flat
Vector Science, Isometric Infographic and Night Signal draw a world a mascot would not fit, at a scale
or in colours it would break. Low-Poly Skit is built from one house figure made of 3D shapes, and a flat mascot picture would not sit in its world.

![The Mascots page under Profiles: a form for a new mascot, and the built-in mascot Tubi marked READY](../images/mascots.png)

### Tubi

Tubematic ships with one mascot, Tubi: a small retro terminal whose screen is its face. You can pick
Tubi without setting anything up. You cannot edit Tubi, but **Ask for a variation** creates a new
mascot based on it.

### Making your own

1. Open **Profiles → Mascots**.
2. Enter a name and describe the character: what it is, how it looks, how it carries itself. Or
   press **Surprise me** and let the agent invent one.
3. Optionally pick the agent, model and effort that should draw it. Without a pick, the default
   agent draws it.
4. Wait for the next agent session. The agent writes the drawing code and renders three sheets: a
   turnaround, the mascot's ten emotions and a strip of poses. This happens while the pipeline is
   paused too.
5. Open the mascot when it reaches **In review** and look at the sheets. Press **Approve** to make
   it available, or **Request changes** with a comment saying what to fix.

A mascot moves through **Pending**, **Building** and **In review**. If drawing fails twice, it
shows **Failed** with the reason, and any approved version stays in use.

Asking for changes to an approved mascot does not disturb videos that use it. Videos keep the last
approved version while the new one is drawn. A video whose scenes are already written stays on the
version it was written for.

**Archive** removes a mascot from every picker. Videos already past topic approval keep rendering
with it. A topic still waiting for approval with an archived mascot cannot be approved until you
pick another mascot or none.

### Choosing a mascot

Three places set it. Each overrides the one above.

| Where | What it sets |
|---|---|
| **Settings → Rendering → Default mascot (experimental)** | The default for the whole install. Empty means none |
| **Mascot (exp.)**, under **Edit defaults** on a domain's row on the **Topics** page | The default for that domain. *Use install default* follows the setting above. *None* means no mascot in this domain |
| The mascot picker on a topic waiting for approval | That one video. Fixed once you approve the topic |

You can set a default only while a renderer's GPU works. A default you set earlier stays stored if
the GPU stops working, and applies again once the GPU is back.

The agent decides when the mascot appears and what it reacts to.
[Scene Authoring](../developer/10-scene-authoring.md#mascots) explains how.
