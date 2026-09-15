"""Shot library expansion — 300 direction presets.

ETAPA 6. `knowledge_base/SHOT_LIBRARY.md` states the target and the contract:

    "The full library target is 300+ shots. New shots require code, name, lens,
     frame, movement, lighting, emotional intention and continuity notes."

This module supplies the expansion. Two things are held constant:

* **The ten published presets are untouched.** `SEED_SHOTS` in `shot_resolver.py`
  stays byte-identical, because `SHOT_LIBRARY.md` declares shot codes *stable
  identifiers*. The expansion adds 290 new codes in the free space of
  SH001–SH300 and never renumbers anything.
* **Every shot obeys the CINEMATIC_BIBLE.** Each movement names a motivation,
  each lens is one of the five focal lengths the Bible declares, and each frame
  is one of the four shot sizes. `ShotLibrary.violations()` checks all 300
  against ETAPA 5's grammar, and a test fails if any shot drifts.

Authoring format
----------------
Each row carries only the *creative* fields the document asks for:

    (code, name, lens_mm, frame, movement, lighting, intention, continuity)

The purely technical fields — `speed`, `focus`, `shake`, `depth` — are **derived**
from frame, lens and movement by `_derive_*` below. That is deliberate: an 85mm
close-up always has shallow depth and a locked tripod never shakes, so deriving
them keeps 300 entries internally consistent instead of hand-typing 1,160 values
that could contradict each other.

Independence: imports `contracts`, `cinematic_library` and `shot_resolver` (for
the published seeds) only. No FastAPI, no SQLAlchemy, no prompts.
"""
from __future__ import annotations

from .cinematic_library import CinematicLibrary
from .contracts import ShotPreset
from .shot_resolver import SEED_SHOTS

#: The ten codes already published in SHOT_LIBRARY.md and knowledge.py. Reserved
#: so the expansion can never collide with a stable identifier.
PUBLISHED_CODES: frozenset[str] = frozenset(shot.code for shot in SEED_SHOTS)

#: Narrative families. A shot browser groups by these so a director picks a
#: function ("I need tension") instead of scanning 300 codes.
FAMILIES: tuple[str, ...] = (
    "establishing",
    "introduction",
    "dialogue",
    "action",
    "tension",
    "intimacy",
    "product",
    "fashion",
    "transition",
    "atmosphere",
    "resolution",
    "documentary",
)

FAMILY_LABELS: dict[str, str] = {
    "establishing": "Geography & world",
    "introduction": "Character introduction",
    "dialogue": "Dialogue & interaction",
    "action": "Action & movement",
    "tension": "Tension & suspense",
    "intimacy": "Emotion & intimacy",
    "product": "Product & detail",
    "fashion": "Fashion & editorial",
    "transition": "Transition & time",
    "atmosphere": "Atmosphere & environment",
    "resolution": "Departure & resolution",
    "documentary": "Documentary & interview",
}

#: Shot rows: (code, name, lens_mm, frame, movement, lighting, intention, continuity)
#: grouped by family. Movement always names a motivation from the Bible.
ShotRow = tuple[str, str, int, str, str, str, str, str]

_ROWS_BY_FAMILY: dict[str, tuple[ShotRow, ...]] = {
    # ---------------------------------------------------------------- geography
    "establishing": (
        ("SH002", "City Wakes", 24, "establishing shot", "slow crane reveal descending to street level", "blue hour ambience, soft volumetric key", "the world before the story", "establish geography once; later scenes inherit this light"),
        ("SH003", "Harbour Scale", 24, "establishing shot", "lateral tracking along the waterfront", "hard noon discipline, deep shadows", "commerce and distance", "match tide and cloud direction across the sequence"),
        ("SH004", "Mountain Threshold", 24, "establishing shot", "slow push-in toward the pass", "cold morning key, thin haze revealing depth", "arrival at a boundary", "keep the ridge line on the same screen side"),
        ("SH005", "Desert Approach", 24, "establishing shot", "ground-level dolly advance across dunes", "hard directional key, long shadows", "exposure and vulnerability", "sun angle must match the preceding exterior"),
        ("SH006", "Factory Floor", 24, "establishing shot", "overhead crane reveal descending into the hall", "practical sodium sources, volumetric haze", "industrial order", "machine rhythm must match the cut tempo"),
        ("SH007", "Rain Arrival", 24, "establishing shot", "slow drift across a wet plaza", "neon practicals, coloured bounce", "the city as an obstacle", "wetness level must be continuous"),
        ("SH008", "Estate Reveal", 24, "establishing shot", "symmetrical dolly advance through the gates", "warm side light, controlled contrast", "wealth and seclusion", "hold the axis for the following interior"),
        ("SH009", "Rooftop Survey", 24, "establishing shot", "slow orbit over the skyline", "blue hour ambience, practical windows", "scale above the characters", "keep landmark positions consistent"),
        ("SH010", "Forest Entry", 35, "establishing shot", "tracking advance beneath the canopy", "soft volumetric key through leaves", "entering an unknown system", "foliage density must match the reverse"),
        ("SH011", "Bridge Crossing", 24, "establishing shot", "lateral tracking parallel to the span", "hard noon discipline, specular water", "a decision in motion", "traffic direction stays screen-left to right"),
        ("SH012", "Neon Alley", 24, "establishing shot", "handheld drift into the alley mouth", "neon practicals, rain diffusion", "the underworld is close", "keep signage colour palette consistent"),
        ("SH013", "Airport Terminal", 24, "establishing shot", "wide tracking through the concourse", "cool daylight, even practicals", "transit and anonymity", "crowd density must match the following shot"),
        ("SH015", "Coastal Cliff", 24, "establishing shot", "crane reveal descending toward the edge", "cold key, haze revealing depth", "isolation made visible", "wave direction stays constant"),
        ("SH016", "Village Morning", 35, "establishing shot", "slow dolly advance along the lane", "warm side light, soft haze", "community before conflict", "smoke and light direction must match"),
        ("SH017", "Subway Descent", 24, "establishing shot", "tracking descent down the escalator", "fluorescent practicals, green cast", "going under", "flicker rate must match the platform shot"),
        ("SH018", "Stadium Empty", 24, "establishing shot", "slow orbit across the empty tiers", "hard directional key, clean blacks", "anticipation without crowd", "seat colour temperature must stay even"),
        ("SH019", "Warehouse Maze", 24, "establishing shot", "handheld advance between the racks", "single practical source, deep falloff", "nowhere to hide", "rack geometry must match the pursuit"),
        ("SH020", "Snow Field", 24, "establishing shot", "slow lateral tracking across the drift", "flat overcast key, protected highlights", "silence as pressure", "wind direction stays consistent"),
        ("SH021", "Old Town Roof", 35, "establishing shot", "crane up and away from the chimney line", "warm side light, golden falloff", "a place that remembers", "roofline must match the interior window"),
        ("SH022", "Port Crane", 24, "establishing shot", "slow push-in beneath the gantry", "hard noon discipline, steel reflections", "machinery over people", "crane position must match the wide"),
        ("SH023", "Night Highway", 24, "establishing shot", "tracking advance along the empty road", "headlight practicals, sodium bounce", "movement without destination", "lane direction stays constant"),
        ("SH024", "Greenhouse", 35, "establishing shot", "slow dolly advance through the glass rows", "diffused daylight, soft haze", "cultivated order", "plant growth stage must match the scene"),
        ("SH025", "Quarry Depth", 24, "establishing shot", "overhead crane reveal descending into the pit", "hard directional key, dust revealing depth", "scale of extraction", "dust level must match the following shot"),
        ("SH026", "Border Checkpoint", 35, "establishing shot", "slow tracking along the fence line", "cold key, flat contrast", "permission and denial", "fence line stays on the same side"),
        ("SH027", "Sunrise Ridge", 24, "establishing shot", "static locked tripod as the light rises", "warm side light building, protected highlights", "a day begins", "sun position must match every exterior in the episode"),
    ),
    # ------------------------------------------------------------- introduction
    "introduction": (
        ("SH028", "First Silhouette", 50, "medium shot", "slow push-in from a backlit doorway", "strong rim, key withheld", "a presence before a face", "rim direction must match the following reveal"),
        ("SH029", "Hands First", 85, "close-up", "slow drift across the hands at work", "soft key, warm side fill", "character defined by craft", "hand position must match the wider coverage"),
        ("SH030", "Walk On", 35, "medium shot", "tracking advance matching the stride", "hard directional key, long shadow", "confidence in motion", "screen direction must match the establishing shot"),
        ("SH031", "Mirror Introduction", 50, "medium shot", "slow dolly advance toward the reflection", "practical lamp, soft falloff", "self-assessment", "mirror geometry must match the room layout"),
        ("SH033", "Name in Passing", 50, "medium shot", "lateral tracking as the subject crosses frame", "even practicals, cool daylight", "identity announced casually", "wardrobe must match the following interior"),
        ("SH034", "Boots on Gravel", 85, "close-up", "low-angle tracking with the feet", "hard noon discipline, sharp shadows", "grounded arrival", "ground texture must match the wide"),
        ("SH035", "Late Arrival", 35, "medium shot", "handheld drift following from behind", "mixed practicals, uneven", "out of place, out of time", "crowd density must match the room"),
        ("SH036", "Authority Enters", 35, "medium shot", "symmetrical dolly advance, centred frame", "controlled key, clean blacks", "the room answers to this person", "hold the axis established by SH124"),
        ("SH037", "Quiet Observer", 85, "close-up", "static locked tripod, subject unaware", "soft key from frame left", "watching before acting", "eyeline must match the reverse"),
        ("SH038", "Uniform Detail", 85, "close-up", "slow drift down the insignia", "soft key, specular control", "rank made visible", "insignia must match the wide coverage"),
        ("SH039", "Backlit Turn", 50, "medium shot", "slow orbit as the subject turns", "strong rim, face emerging from shadow", "recognition deferred", "turn direction must match the reverse"),
        ("SH040", "Signature Gesture", 135, "extreme close-up", "slow push-in on the habitual gesture", "soft key, razor separation", "identity in a habit", "gesture must recur at the resolution"),
        ("SH041", "Doorway Frame", 35, "medium shot", "static locked tripod, subject fills the frame", "practical interior, dark exterior", "threshold decision", "door geometry must match the room"),
        ("SH042", "Crowd Separation", 85, "medium shot", "slow dolly advance isolating the subject", "soft key, background falling away", "one among many, then alone", "crowd motion must match the wide"),
        ("SH043", "Workbench Portrait", 50, "medium shot", "slow tracking around the bench", "single practical source, warm", "skill as biography", "tool placement must match the insert"),
        ("SH044", "Rain Window", 85, "close-up", "static locked tripod through wet glass", "diffused daylight, soft falloff", "withheld interior life", "rain density must match the exterior"),
        ("SH045", "Staircase Descent", 35, "medium shot", "tracking descent matching the steps", "hard directional key from above", "deliberate lowering of status", "stair geometry must match the landing"),
        ("SH046", "Phone Light", 85, "close-up", "slow push-in on the lit face", "screen practical as key, deep falloff", "attention captured elsewhere", "screen colour must match the following insert"),
        ("SH047", "Coat and Shoulder", 50, "medium shot", "handheld drift behind the shoulder", "cool practicals, mixed cast", "carrying weight", "wardrobe must match the introduction wide"),
        ("SH048", "First Words", 50, "medium shot", "slow dolly advance as the subject speaks", "soft key, gentle rim", "voice establishes character", "eyeline must match the listener"),
        ("SH049", "Reflection in Steel", 85, "close-up", "slow drift across the distorted face", "specular practicals, controlled highlights", "identity not yet settled", "surface must match the environment"),
        ("SH050", "Gait Signature", 35, "medium shot", "low-angle tracking with the walk", "hard noon discipline, hard shadows", "character in rhythm", "pace must match the following scene"),
        ("SH052", "Waiting Room", 50, "medium shot", "static locked tripod, subject small in frame", "flat fluorescent practicals", "institutional anonymity", "seat position must match the wide"),
        ("SH053", "Glove Removal", 135, "extreme close-up", "slow push-in as the glove comes off", "soft key, warm side fill", "deliberate exposure", "hand must match SH029"),
        ("SH054", "Threshold Step", 35, "medium shot", "slow dolly advance across the doorway", "warm interior against cold exterior", "commitment", "door geometry must match SH041"),
    ),
    # ----------------------------------------------------------------- dialogue
    "dialogue": (
        ("SH055", "Over Shoulder A", 50, "medium shot", "static locked tripod, breathing frame", "soft key on speaker, rim on listener", "position stated", "eyeline and screen direction must hold for the whole scene"),
        ("SH056", "Over Shoulder B", 50, "medium shot", "static locked tripod, mirrored axis", "soft key on speaker, rim on listener", "position answered", "cross the axis never; match SH055"),
        ("SH057", "Two Shot Level", 35, "medium shot", "slow lateral tracking as they walk", "even daylight, soft fill", "equality in the frame", "pace must match both singles"),
        ("SH058", "Power Tilt", 50, "medium shot", "low-angle push-in on the dominant speaker", "hard key from above", "authority asserted", "angle must reverse for the subordinate"),
        ("SH059", "Submission Angle", 50, "medium shot", "high-angle static locked tripod", "flat key, exposed face", "vulnerability conceded", "angle must match SH058's reverse"),
        ("SH060", "Interrupting Close", 85, "close-up", "fast push-in on the interruption", "hard key, crushed background", "the argument turns", "cut point must land on the interrupting word"),
        ("SH061", "Listening Face", 85, "close-up", "static locked tripod, no movement", "soft key, minimal rim", "reaction over action", "reaction must precede the line it answers"),
        ("SH062", "Table Geometry", 35, "medium shot", "slow dolly advance along the table", "even practicals, symmetrical", "negotiation as architecture", "seat positions must match the wide"),
        ("SH063", "Whisper Lean", 85, "close-up", "slow drift as they lean in", "low practical source, deep falloff", "secrecy", "distance must match the reverse"),
        ("SH064", "Walking Argument", 35, "medium shot", "handheld tracking between them", "mixed practicals, moving shadows", "conflict in motion", "screen direction must not flip mid-scene"),
        ("SH065", "Silence Between", 50, "medium shot", "static locked tripod, held long", "unchanged key", "what is not said", "hold long enough for the audience to lean in"),
        ("SH066", "Interrogation Single", 50, "close-up", "slow push-in under the lamp", "single hard key, deep falloff", "pressure applied", "lamp position must match the wide"),
        ("SH067", "Deflection", 85, "close-up", "slow drift as the gaze leaves frame", "soft key, shadow across the eyes", "avoidance", "gaze direction must match the object of avoidance"),
        ("SH068", "Shared Laugh", 35, "medium shot", "handheld drift between both faces", "warm practicals, soft", "alliance formed", "energy must match both singles"),
        ("SH069", "Phone Argument", 50, "close-up", "static locked tripod, one side only", "screen practical, cool falloff", "distance inside intimacy", "audio must match the other side's timing"),
        ("SH070", "Crowded Confidence", 85, "close-up", "slow push-in isolating the speaker", "soft key, background falling away", "private words in public", "crowd motion must match the wide"),
        ("SH071", "Doorway Confrontation", 35, "medium shot", "slow dolly advance into the frame", "practical interior, hard edge light", "an obstacle appears", "door geometry must match the room"),
        ("SH072", "Reconciliation", 50, "medium shot", "slow orbit settling into a two shot", "warm side light, soft haze", "distance closing", "final framing must match the scene's opening"),
        ("SH073", "Betrayal Tell", 135, "extreme close-up", "slow push-in on the eyes", "soft key, razor separation", "the truth leaks", "must land before the line that exposes it"),
        ("SH074", "Translator's Pause", 50, "medium shot", "static locked tripod, three-quarter", "even key, neutral", "meaning in transit", "timing must match both language tracks"),
        ("SH075", "Cornered", 35, "medium shot", "handheld advance closing the space", "hard key, wall in shadow", "no exit left", "wall geometry must match the wide"),
        ("SH076", "Final Word", 85, "close-up", "slow pull-back releasing the speaker", "key lifting slightly", "the last position", "pull-back must match the scene's exit"),
        ("SH077", "Group Verdict", 35, "medium shot", "slow lateral tracking across the faces", "even key, symmetrical", "collective judgement", "seat order must match the establishing wide"),
        ("SH078", "Aftermath Quiet", 50, "medium shot", "static locked tripod, empty chair in frame", "unchanged key, cooler", "absence speaks", "chair position must match SH062"),
    ),
    # ------------------------------------------------------------------- action
    "action": (
        ("SH079", "Sprint Pursuit", 35, "medium shot", "handheld tracking move with the subject", "hard directional key, motion blur controlled", "flight", "screen direction must hold across every cut"),
        ("SH080", "Impact Landing", 24, "medium shot", "fast push-in landing on the impact", "hard key, dust revealing depth", "consequence", "impact point must match the preceding wide"),
        ("SH081", "Corridor Run", 35, "medium shot", "handheld advance through the corridor", "practicals streaking, volumetric haze", "no time to think", "corridor geometry must match the floor plan"),
        ("SH082", "Vehicle Chase", 24, "establishing shot", "lateral tracking parallel to the vehicle", "hard noon discipline, reflective surfaces", "speed with geography", "route must match the map established earlier"),
        ("SH083", "Rooftop Leap", 24, "establishing shot", "crane reveal descending after the jump", "cold key, haze revealing depth", "commitment without safety", "gap distance must match the reverse"),
        ("SH084", "Close Quarters", 50, "medium shot", "handheld orbit around the struggle", "single practical source, deep falloff", "chaos with readable geography", "fighter positions must match the wide"),
        ("SH085", "Weapon Draw", 135, "extreme close-up", "fast push-in on the hand", "hard key, specular control", "the point of no return", "hand must match the character's established handedness"),
        ("SH086", "Getaway Wheel", 85, "close-up", "handheld drift inside the cabin", "streaking practicals, cool cast", "control under pressure", "steering direction must match the exterior"),
        ("SH087", "Stairwell Fall", 24, "establishing shot", "crane descent following the fall", "hard key from above, deep shaft", "loss of control", "stair geometry must match the building"),
        ("SH088", "Crowd Break", 35, "medium shot", "handheld advance through the fleeing crowd", "mixed practicals, uneven", "the individual against the mass", "crowd direction must match the wide"),
        ("SH090", "Glass Shatter", 135, "extreme close-up", "static locked tripod as the glass breaks", "strong rim, backlight through fragments", "the boundary fails", "fragment direction must match the impact"),
        ("SH091", "Rooftop Sprint", 24, "establishing shot", "lateral tracking along the parapet", "blue hour ambience, practical windows", "exposure at speed", "skyline must match SH009"),
        ("SH092", "Door Breach", 35, "medium shot", "handheld advance through the breach", "hard key, dust revealing depth", "entry by force", "door must match the established layout"),
        ("SH093", "Motorcycle Weave", 24, "medium shot", "low-angle tracking with the machine", "hard noon discipline, asphalt reflections", "threading danger", "traffic direction must match the street"),
        ("SH094", "Fall From Height", 24, "establishing shot", "crane descent watching the drop", "cold key, haze revealing depth", "descent as consequence", "height must match the establishing"),
        ("SH095", "Reload Insert", 135, "extreme close-up", "fast push-in on the mechanism", "hard key, specular control", "preparation under pressure", "weapon must match the preceding wide"),
        ("SH096", "Water Escape", 35, "medium shot", "handheld drift on the surface", "diffused daylight, protected highlights", "survival", "current direction must match the river"),
        ("SH097", "Night Alley Fight", 35, "medium shot", "handheld orbit with controlled framing", "neon practicals, wet reflections", "violence with readable space", "neon colours must match SH012"),
        ("SH098", "Barrier Smash", 24, "medium shot", "fast dolly advance through the break", "hard key, debris in backlight", "refusal to stop", "debris direction must match the impact"),
        ("SH099", "Extraction Lift", 24, "establishing shot", "crane up and away with the helicopter", "hard directional key, rotor wash haze", "escape at cost", "landing zone must match the wide"),
        ("SH100", "Tunnel Chase", 24, "establishing shot", "tracking advance through the tunnel", "sodium practicals, rhythmic streaks", "no way out but through", "tunnel geometry must match the route"),
        ("SH101", "Rooftop Standoff", 35, "medium shot", "slow orbit holding both figures", "blue hour ambience, rim separation", "neither will move", "figure positions must match the wide"),
        ("SH102", "Final Blow", 85, "close-up", "fast push-in on the impact", "hard key, protected highlights", "the cost lands", "impact must match SH080"),
        ("SH103", "Aftermath Walk", 50, "medium shot", "slow tracking advance through the wreckage", "smoke haze revealing depth, low key", "survival without victory", "wreckage layout must match the fight"),
    ),
    # ------------------------------------------------------------------ tension
    "tension": (
        ("SH104", "Held Breath", 85, "close-up", "extremely slow push-in, almost imperceptible", "soft key, shadow creeping across the face", "time stretching", "the push-in must not resolve before the sound does"),
        ("SH105", "Unseen Watcher", 135, "close-up", "static locked tripod through an obstruction", "low practical source, deep falloff", "being observed", "obstruction must match the room geometry"),
        ("SH106", "Door Handle", 135, "extreme close-up", "slow push-in on the turning handle", "single practical, hard falloff", "the decision is physical", "handle must match the door established earlier"),
        ("SH107", "Empty Chair", 50, "medium shot", "static locked tripod, held long", "unchanged key, cooler than the scene", "someone is missing", "chair must match SH078"),
        ("SH108", "Footsteps Offscreen", 35, "medium shot", "static locked tripod, frame refuses to move", "even practicals, long shadow entering", "threat approaching", "shadow direction must match the source"),
        ("SH109", "Phone Ringing", 85, "close-up", "slow drift toward the device", "screen practical, cool falloff", "an unavoidable call", "device must match the character's established prop"),
        ("SH110", "Corridor Waiting", 35, "medium shot", "slow dolly advance down the empty corridor", "practicals receding, volumetric haze", "the approach is the threat", "corridor must match SH081"),
        ("SH111", "Hand on Weapon", 135, "extreme close-up", "static locked tripod, no movement", "hard key, specular control", "restraint or violence", "hand must match SH085"),
        ("SH112", "Window Scan", 50, "close-up", "slow drift following the searching gaze", "diffused daylight, soft falloff", "looking for what is not there", "gaze direction must match the exterior"),
        ("SH113", "Locked Room", 24, "establishing shot", "slow orbit mapping every exit", "single practical source, deep falloff", "nowhere to go", "exit positions must match the geography"),
        ("SH114", "Ticking Detail", 135, "extreme close-up", "slow push-in on the mechanism", "hard key, controlled highlights", "time as antagonist", "mechanism must match the established prop"),
        ("SH115", "Whispered Warning", 85, "close-up", "handheld drift, unstable frame", "low practical source, shadowed eyes", "information as danger", "proximity must match the reverse"),
        ("SH116", "Shadow Crossing", 35, "medium shot", "static locked tripod, shadow traverses frame", "hard key, moving obstruction", "something passed", "shadow speed must match the offscreen source"),
        ("SH117", "Basement Stairs", 24, "establishing shot", "slow tracking descent into darkness", "single practical at the foot, falloff", "deliberate descent", "stair geometry must match SH045"),
        ("SH118", "Unanswered Knock", 50, "medium shot", "static locked tripod on the closed door", "warm interior, cold gap light", "refusal", "door must match SH041"),
        ("SH119", "Breath on Glass", 135, "extreme close-up", "slow push-in on the condensation", "diffused daylight, protected highlights", "presence proved", "glass must match SH044"),
        ("SH125", "Delayed Reaction", 85, "close-up", "static locked tripod, held past comfort", "soft key, minimal rim", "understanding arrives late", "reaction must land after the reveal"),
        ("SH126", "Elevator Numbers", 135, "extreme close-up", "slow push-in on the changing digits", "cool practical, even falloff", "countdown without a clock", "digit sequence must match the floor plan"),
        ("SH127", "Car Back Seat", 50, "close-up", "static locked tripod, frame boxed in", "streaking practicals, cool cast", "trapped by choice", "window streaks must match the route"),
        ("SH128", "Unread Message", 85, "extreme close-up", "slow drift across the screen", "screen practical, deep falloff", "knowledge withheld", "message must match the plot beat"),
        ("SH129", "Long Lens Street", 135, "medium shot", "static locked tripod, subject compressed in crowd", "hard noon discipline, flat perspective", "surveillance", "crowd direction must match the street"),
        ("SH130", "Creaking Floor", 35, "medium shot", "handheld drift toward the sound", "low practical source, deep falloff", "the house is listening", "floorboard position must match the room"),
        ("SH131", "Last Light", 50, "close-up", "slow pull-back as the light fails", "key dimming, practical taking over", "options narrowing", "light level must match the scene's arc"),
        ("SH132", "Standoff Silence", 35, "medium shot", "static locked tripod, both figures held", "hard key, symmetrical shadow", "nobody moves first", "positions must match SH101"),
    ),
    # ------------------------------------------------------------------ intimacy
    "intimacy": (
        ("SH133", "Eyes Closed", 85, "extreme close-up", "extremely slow push-in, razor focus", "soft key, warm side fill", "withheld interior life", "must match SH014's treatment exactly"),
        ("SH134", "Forehead Touch", 85, "close-up", "static locked tripod, breathing frame", "soft key, gentle rim", "trust without words", "distance must match the reverse"),
        ("SH135", "Hand Held", 135, "extreme close-up", "slow drift across the joined hands", "warm side light, soft falloff", "commitment in contact", "hands must match SH029"),
        ("SH136", "Tears Deferred", 85, "extreme close-up", "static locked tripod, no movement", "soft key, protected highlights", "grief held back", "must land after the line, never during"),
        ("SH137", "Whispered Name", 85, "close-up", "slow push-in as the word lands", "low practical source, warm", "recognition", "audio must be closer than the preceding line"),
        ("SH138", "Shoulder Rest", 50, "close-up", "static locked tripod, two heads in frame", "soft key, shared falloff", "shared weight", "positions must match the two shot"),
        ("SH139", "Scar Revealed", 135, "extreme close-up", "slow drift following the line of the scar", "warm side light, tactile", "history on the body", "scar must match the character's established detail"),
        ("SH140", "Hair Tucked", 85, "extreme close-up", "slow push-in on the gesture", "soft key, razor separation", "tenderness as habit", "gesture must match SH040"),
        ("SH141", "Shared Blanket", 35, "medium shot", "static locked tripod, held long", "single practical, deep falloff", "shelter made of two", "light level must match the room"),
        ("SH142", "Morning After", 50, "medium shot", "slow dolly advance through the doorway", "diffused daylight, protected highlights", "vulnerability in daylight", "room must match the night scene"),
        ("SH143", "Letter Read", 85, "close-up", "slow push-in on the reading face", "warm practical lamp, soft falloff", "words arriving late", "letter must match the established prop"),
        ("SH144", "Dance Slow", 50, "medium shot", "slow orbit around the pair", "warm side light, soft haze", "time suspended together", "rotation must match the music's phrasing"),
        ("SH145", "Bath Steam", 35, "close-up", "static locked tripod through haze", "soft key, haze revealing depth", "privacy and release", "haze must reveal depth, never decorate"),
        ("SH146", "Sleeping Face", 85, "extreme close-up", "extremely slow drift, almost static", "low practical source, warm falloff", "guard dropped", "light must match the room's night level"),
        ("SH147", "Apology Unspoken", 50, "close-up", "slow pull-back giving space", "soft key, cooler fill", "words that will not come", "pull-back must match the scene's distance"),
        ("SH148", "Ring Placed", 135, "extreme close-up", "slow push-in on the finger", "warm side light, specular control", "a promise made physical", "hand must match SH135"),
        ("SH149", "Kitchen Quiet", 35, "medium shot", "static locked tripod, domestic geometry", "warm practicals, even falloff", "intimacy in routine", "kitchen layout must match the wide"),
        ("SH150", "Backlit Embrace", 50, "medium shot", "slow orbit settling behind the pair", "strong rim, faces in soft shadow", "union against the light", "rim direction must match the exterior"),
        ("SH151", "Photograph Found", 85, "close-up", "slow push-in on the image", "warm practical, controlled highlights", "the past intrudes", "photograph must match the established history"),
        ("SH152", "Wound Tended", 135, "extreme close-up", "slow drift across the careful hands", "single practical, warm falloff", "care as confession", "wound must match the preceding action"),
        ("SH153", "Goodbye at the Door", 50, "medium shot", "static locked tripod, threshold framing", "warm interior, cold exterior", "leaving and staying", "door must match SH054"),
        ("SH154", "Laugh Lines", 135, "extreme close-up", "slow push-in on the smiling face", "warm side light, tactile", "joy with history", "must match the character's established age"),
        ("SH155", "Child's Hand", 135, "extreme close-up", "slow drift as the small hand closes", "soft key, protected highlights", "trust given completely", "scale must match the adult hand beside it"),
        ("SH156", "Last Look Back", 85, "close-up", "slow pull-back releasing the face", "key lifting, rim holding", "memory formed", "must match the departure's direction"),
    ),
    # ------------------------------------------------------------------ product
    "product": (
        ("SH157", "Hero Product Reveal", 85, "close-up", "slow dolly advance onto the object", "large soft key, polished reflections", "desire stated", "product orientation must match every insert"),
        ("SH158", "Material Macro", 135, "extreme close-up", "slow drift across the surface texture", "hard directional key, specular control", "quality made visible", "grain and weave must match the wide"),
        ("SH159", "Turntable", 85, "close-up", "constant orbit, one full revolution", "large soft key, controlled rim", "every angle considered", "rotation direction must stay constant"),
        ("SH160", "Unboxing", 50, "medium shot", "slow push-in as the lid lifts", "even soft key, clean blacks", "anticipation rewarded", "packaging must match the brand palette"),
        ("SH161", "Pour and Settle", 135, "extreme close-up", "static locked tripod, motion inside frame", "hard key, protected highlights", "substance and ritual", "liquid colour must match the grade"),
        ("SH162", "Hand and Object", 85, "close-up", "slow drift as the hand presents", "warm side light, soft falloff", "scale and ownership", "hand must match the model's established look"),
        ("SH163", "Symmetry Flat Lay", 50, "establishing shot", "overhead static locked tripod", "even soft key, no shadows", "order as luxury", "object spacing must match the layout board"),
        ("SH164", "Detail Insert Luxury", 135, "extreme close-up", "slow push-in on the stitching", "hard key, razor separation", "craft justifies price", "stitching must match SH122's treatment"),
        ("SH165", "Reflection Sweep", 85, "close-up", "slow drift as the highlight travels", "single hard source moving across", "surface perfection", "reflection speed must match the move"),
        ("SH166", "Scale in Hand", 50, "medium shot", "static locked tripod, object against palm", "soft key, warm falloff", "portability", "hand must match SH162"),
        ("SH167", "Assembly Sequence", 85, "close-up", "slow tracking following each part", "even key, clean blacks", "engineering as beauty", "part order must match the real assembly"),
        ("SH168", "Fabric Fall", 135, "extreme close-up", "static locked tripod, motion inside frame", "hard key, specular control", "weight and drape", "fabric must match the garment wide"),
        ("SH169", "Logo Reveal", 135, "extreme close-up", "slow push-in resolving the mark", "hard key, protected highlights", "identity confirmed", "logo must match the brand asset exactly"),
        ("SH170", "Steam and Heat", 85, "close-up", "slow drift through the rising steam", "backlight, haze revealing depth", "freshness proved", "haze must reveal depth, never decorate"),
        ("SH171", "Shelf Context", 35, "medium shot", "slow lateral tracking along the shelf", "even practicals, soft falloff", "the product among rivals", "shelf order must match the set dressing"),
        ("SH172", "Cap Removed", 135, "extreme close-up", "static locked tripod, action inside frame", "hard key, specular control", "the ritual begins", "cap must match the product silhouette"),
        ("SH173", "Water Bead", 135, "extreme close-up", "extremely slow push-in on the droplet", "hard key, protected highlights", "precision and purity", "droplet position must match the lighting angle"),
        ("SH174", "In Use", 50, "medium shot", "handheld drift following the usage", "natural available light, soft", "the product in a life", "environment must match the campaign world"),
        ("SH175", "Contrast Pair", 85, "close-up", "slow dolly advance between the two", "large soft key, controlled rim", "the better choice made obvious", "positions must match the comparison board"),
        ("SH176", "Shadow Play", 135, "extreme close-up", "static locked tripod, shadow crossing", "single hard source moving", "sculpted form", "shadow direction must match the key"),
        ("SH177", "Weight Drop", 85, "close-up", "static locked tripod, impact inside frame", "hard key, protected highlights", "substance proved", "surface must match the set"),
        ("SH178", "Packaging Turn", 85, "close-up", "constant orbit, half revolution", "large soft key, even falloff", "design considered", "rotation must match SH159"),
        ("SH179", "Final Hero", 85, "close-up", "slow pull-back to the finished composition", "large soft key, champagne highlight", "the object of desire settled", "must match SH157's framing inverted"),
        ("SH180", "End Card Object", 50, "medium shot", "static locked tripod, centred frame", "clean blacks, single controlled highlight", "brand held in stillness", "must match the campaign's closing frame"),
    ),
    # ------------------------------------------------------------------ fashion
    "fashion": (
        ("SH181", "Editorial Portrait", 85, "close-up", "static locked tripod, controlled pose", "large soft key, subtle rim", "presence over narrative", "makeup and hair must match every frame"),
        ("SH182", "Runway Walk", 35, "medium shot", "tracking advance matching the stride", "hard directional key, wet reflections", "garment in motion", "pace must match the music's tempo"),
        ("SH183", "Fabric in Wind", 135, "extreme close-up", "static locked tripod, motion inside frame", "hard key, specular control", "material as subject", "wind direction must stay constant"),
        ("SH184", "Silhouette Turn", 50, "medium shot", "slow orbit as the model turns", "strong rim, face in shadow", "shape before identity", "turn direction must match the sequence"),
        ("SH185", "Accessory Detail", 135, "extreme close-up", "slow drift across the hardware", "hard key, protected highlights", "the detail sells the whole", "hardware must match the look board"),
        ("SH186", "Lookbook Frame", 50, "medium shot", "static locked tripod, full figure", "even soft key, clean backdrop", "the garment read completely", "pose must match the look sheet"),
        ("SH187", "Backstage Rush", 35, "medium shot", "handheld drift through the chaos", "mixed practicals, uneven", "the work behind the image", "crowd density must match the call sheet"),
        ("SH188", "Mirror Fitting", 50, "medium shot", "slow dolly advance toward the reflection", "even soft key, soft falloff", "self as image", "mirror must match the room layout"),
        ("SH189", "Heel on Marble", 135, "extreme close-up", "low-angle tracking with the step", "hard key, polished reflections", "authority in the walk", "floor must match the set"),
        ("SH190", "Coat Sweep", 85, "close-up", "slow drift as the coat moves", "hard key, specular control", "volume and line", "coat must match SH183's fabric"),
        ("SH191", "Beauty Close", 135, "extreme close-up", "extremely slow push-in, razor focus", "large soft key, protected highlights", "skin natural, nothing hidden", "skin must stay natural; no grade override"),
        ("SH192", "Studio Sweep", 35, "medium shot", "slow lateral tracking along the seamless", "even soft key, no shadows", "the garment isolated", "backdrop tone must match the campaign"),
        ("SH193", "Stair Editorial", 35, "medium shot", "low-angle tracking up the steps", "hard directional key, long shadow", "elevation as metaphor", "stair geometry must match the location"),
        ("SH194", "Window Light", 85, "close-up", "static locked tripod, daylight falloff", "diffused daylight, soft falloff", "natural luxury", "light direction must match the time of day"),
        ("SH195", "Jewellery Macro", 135, "extreme close-up", "slow drift across the stones", "hard key, specular control", "light held in material", "stone colour must match the grade"),
        ("SH196", "Group Formation", 35, "establishing shot", "slow dolly advance into the formation", "even soft key, symmetrical", "collection as statement", "positions must match the styling board"),
        ("SH197", "Seat and Pose", 50, "medium shot", "slow orbit settling on the pose", "hard key, sculpted shadow", "attitude held", "pose must match the look sheet"),
        ("SH198", "Rooftop Fashion", 35, "medium shot", "handheld drift against the skyline", "blue hour ambience, rim separation", "the city as backdrop", "skyline must match SH009"),
        ("SH199", "Fabric Layer", 135, "extreme close-up", "slow push-in through the layers", "hard key, tactile falloff", "construction revealed", "layers must match the garment spec"),
        ("SH200", "Walk Away", 50, "medium shot", "static locked tripod, figure receding", "hard key, long shadow", "the image leaves", "direction must match SH182"),
        ("SH201", "Hand on Rail", 85, "close-up", "slow drift along the rack", "even soft key, soft falloff", "choice as gesture", "garments must match the rack dressing"),
        ("SH202", "Perfume Light", 135, "extreme close-up", "slow push-in through the glass", "backlight, haze revealing depth", "scent made visible", "haze must reveal depth, never decorate"),
        ("SH203", "Final Pose", 50, "medium shot", "slow pull-back to the finished frame", "large soft key, champagne highlight", "the look complete", "must match SH186's framing inverted"),
        ("SH204", "Campaign Still", 85, "close-up", "static locked tripod, held for the still", "large soft key, subtle rim", "the image that ships", "must match the campaign's key art"),
    ),
    # --------------------------------------------------------------- transition
    "transition": (
        ("SH205", "Whip Between", 35, "medium shot", "fast whip transition across the frame", "matched key on both sides", "time collapsed", "whip direction must match the cut"),
        ("SH206", "Match Cut Hands", 135, "extreme close-up", "static locked tripod, action bridges the cut", "matched warm side light", "two moments, one gesture", "hand position must match across the cut"),
        ("SH207", "Doorway Wipe", 35, "medium shot", "tracking advance as the figure passes", "matched exposure both sides", "scene change inside the frame", "screen direction must hold"),
        ("SH208", "Light to Dark", 50, "close-up", "slow push-in as the key fails", "key dimming to practical only", "mood shifts with the light", "final level must match the next scene's open"),
        ("SH209", "Rise to Sky", 24, "establishing shot", "crane up and away until only sky", "blue hour ambience, protected highlights", "release from the scene", "sky tone must match the following exterior"),
        ("SH210", "Descend to Street", 24, "establishing shot", "crane reveal descending into the crowd", "hard noon discipline, even falloff", "returning to the world", "crowd direction must match the street"),
        ("SH211", "Reflection Dissolve", 85, "close-up", "slow drift across the mirrored surface", "matched specular control", "one face becomes another", "surface must match both scenes"),
        ("SH212", "Window Pass", 35, "medium shot", "lateral tracking as the view changes", "matched daylight both sides", "travel without a cut", "window geometry must match the vehicle"),
        ("SH213", "Object Handoff", 135, "extreme close-up", "static locked tripod, hands cross the frame", "matched warm key", "responsibility transferred", "prop must match both scenes"),
        ("SH214", "Stairwell Transition", 24, "establishing shot", "tracking descent between floors", "practicals changing colour per floor", "moving between worlds", "floor lighting must match each level"),
        ("SH215", "Crowd Immersion", 35, "medium shot", "handheld advance disappearing into the mass", "mixed practicals, uneven", "the individual dissolved", "crowd direction must match the wide"),
        ("SH216", "Season Shift", 24, "establishing shot", "static locked tripod, held across a dissolve", "matched composition, changed light", "time passing on one spot", "camera position must not move at all"),
        ("SH217", "Clock Advance", 135, "extreme close-up", "slow push-in on the changing face", "cool practical, even falloff", "time asserted", "must match SH126's mechanism"),
        ("SH218", "Door to Door", 35, "medium shot", "tracking advance through the threshold", "matched exposure, changed palette", "two places, one move", "door geometry must match both rooms"),
        ("SH219", "Smoke Wipe", 35, "medium shot", "slow drift through the obscuring haze", "haze revealing depth, backlight", "concealed change", "haze must reveal depth, never decorate"),
        ("SH220", "Sound Bridge Look", 50, "close-up", "static locked tripod, gaze leads the cut", "soft key, gentle rim", "attention moves first", "gaze direction must match the next scene"),
        ("SH221", "Lift Doors", 35, "medium shot", "static locked tripod as the doors close", "cool practical, even falloff", "scene sealed", "must match SH126's floor"),
        ("SH222", "Rain to Clear", 24, "establishing shot", "static locked tripod across the change", "diffused daylight to hard key", "weather as narrative", "camera position must not move"),
        ("SH223", "Page Turn", 135, "extreme close-up", "static locked tripod, action inside frame", "warm practical, soft falloff", "chapter closed", "must match SH143's letter"),
        ("SH224", "Corridor to Corridor", 35, "medium shot", "tracking advance through the join", "matched practicals, changed colour", "continuous space, different world", "corridor must match both buildings"),
        ("SH225", "Mirror Turn", 85, "close-up", "slow orbit as the reflection changes", "matched soft key", "identity in flux", "mirror must match both rooms"),
        ("SH226", "Escalator Shift", 24, "establishing shot", "tracking descent between levels", "fluorescent to daylight", "moving between states", "must match SH017's descent"),
        ("SH227", "Final Frame Match", 50, "medium shot", "static locked tripod, composition echoes the opening", "matched key and palette", "the circle closes", "must mirror the episode's first frame"),
        ("SH228", "Fade to Still", 50, "medium shot", "slow pull-back settling to static", "key easing down, protected highlights", "the story stops", "final exposure must match the end card"),
    ),
    # --------------------------------------------------------------- atmosphere
    "atmosphere": (
        ("SH229", "Dust in Light", 135, "extreme close-up", "slow drift through the shaft", "backlight, haze revealing depth", "air made visible", "haze must reveal depth, never decorate"),
        ("SH230", "Rain on Glass", 85, "close-up", "static locked tripod, motion inside frame", "diffused daylight, protected highlights", "the world held at a distance", "rain density must match the exterior"),
        ("SH231", "Steam Rise", 35, "medium shot", "slow drift through the rising column", "backlight, haze revealing depth", "heat and industry", "steam source must match the set"),
        ("SH232", "Fog Bank", 24, "establishing shot", "slow dolly advance into the murk", "flat overcast key, soft falloff", "the unknown ahead", "fog density must match every exterior"),
        ("SH233", "Neon Reflection", 35, "close-up", "slow drift across the wet surface", "neon practicals, coloured bounce", "the city written in light", "neon colours must match SH012"),
        ("SH234", "Candle Row", 85, "close-up", "slow lateral tracking along the flames", "practical flame as key, deep falloff", "devotion and time", "flame direction must match the draught"),
        ("SH235", "Snowfall Static", 35, "medium shot", "static locked tripod, flakes inside frame", "flat overcast key, protected highlights", "quiet accumulation", "wind must match SH020"),
        ("SH236", "Water Surface", 135, "extreme close-up", "slow drift across the ripple", "hard key, specular control", "depth beneath calm", "ripple direction must match the current"),
        ("SH237", "Smoke Room", 35, "medium shot", "handheld drift through the haze", "single practical source, haze revealing depth", "obscured intent", "haze must reveal depth, never decorate"),
        ("SH238", "Sun Flare", 24, "establishing shot", "slow push-in into the light", "hard key, protected highlights", "exposure at the limit", "sun position must match the time of day"),
        ("SH239", "Leaves Falling", 85, "close-up", "static locked tripod, motion inside frame", "soft volumetric key through canopy", "season turning", "foliage must match SH010"),
        ("SH240", "City Breath", 24, "establishing shot", "static locked tripod, traffic inside frame", "blue hour ambience, practical windows", "the place is alive", "traffic direction must match SH002"),
        ("SH241", "Ember Drift", 135, "extreme close-up", "slow drift following the embers", "backlight, warm falloff", "aftermath still warm", "ember direction must match the fire"),
        ("SH242", "Window Rain Night", 50, "close-up", "static locked tripod through wet glass", "neon practicals, coloured bounce", "inside looking out", "must match SH044's night variant"),
        ("SH243", "Wind in Grass", 35, "medium shot", "lateral tracking with the wave", "hard noon discipline, soft shadows", "land moving like water", "wind direction must match the exterior"),
        ("SH244", "Steam Vent", 24, "establishing shot", "slow dolly advance through the plume", "hard key, haze revealing depth", "the street exhales", "vent position must match the geography"),
        ("SH245", "Firelight", 85, "close-up", "static locked tripod, flicker on the face", "practical flame as key, deep falloff", "warmth with danger", "flicker rate must match the fire source"),
        ("SH246", "Ice Formation", 135, "extreme close-up", "slow push-in across the crystal", "cold key, protected highlights", "time made solid", "must match the scene's temperature"),
        ("SH247", "Harbour Mist", 24, "establishing shot", "slow drift along the water", "flat overcast key, soft falloff", "departure obscured", "must match SH003's water"),
        ("SH248", "Lightning Flash", 35, "establishing shot", "static locked tripod, flash inside frame", "hard momentary key, deep blacks", "the sky intervenes", "flash timing must match the sound"),
        ("SH249", "Curtain Drift", 50, "close-up", "slow drift as the fabric moves", "diffused daylight, soft falloff", "the room breathing", "draught must match the window state"),
        ("SH250", "Puddle Mirror", 135, "extreme close-up", "static locked tripod, reflection inside frame", "neon practicals, specular control", "the world inverted", "must match SH007's wetness"),
        ("SH251", "Sunset Wash", 24, "establishing shot", "slow lateral tracking along the horizon", "warm side light, golden falloff", "the day closes", "sun position must match SH027"),
        ("SH252", "Night Static", 24, "establishing shot", "static locked tripod, held long", "practical windows, deep blacks", "the city at rest", "window pattern must match SH002"),
    ),
    # --------------------------------------------------------------- resolution
    "resolution": (
        ("SH253", "Walk Into Distance", 24, "establishing shot", "static locked tripod, figure receding", "warm side light, long shadow", "the story releases them", "direction must match the preceding scene"),
        ("SH254", "Door Closes", 50, "medium shot", "static locked tripod, held after the close", "warm interior fading", "a chapter sealed", "door must match SH054"),
        ("SH255", "Last Object", 135, "extreme close-up", "slow push-in on what remains", "soft key, warm falloff", "meaning left behind", "object must match the story's key prop"),
        ("SH256", "Empty Room", 24, "establishing shot", "slow dolly advance through the cleared space", "diffused daylight, even falloff", "absence as evidence", "room must match the scene it empties"),
        ("SH257", "Hand Released", 135, "extreme close-up", "slow drift as the hands part", "warm side light, soft falloff", "letting go", "must invert SH135"),
        ("SH258", "Sunset Face", 85, "close-up", "slow push-in on the settled expression", "warm side light, golden falloff", "acceptance", "sun position must match SH251"),
        ("SH259", "Final Ascent", 24, "establishing shot", "crane up and away from the figure", "blue hour ambience, rim separation", "release into scale", "must invert SH002's descent"),
        ("SH260", "Grave Marker", 50, "medium shot", "static locked tripod, held long", "flat overcast key, soft falloff", "grief given a place", "marker must match the established detail"),
        ("SH261", "Letter Left", 85, "close-up", "slow pull-back from the page", "warm practical, soft falloff", "words finally sent", "must match SH143"),
        ("SH262", "Reunion Frame", 35, "medium shot", "slow dolly advance bringing both together", "warm side light, soft haze", "distance finally closed", "positions must match their separation"),
        ("SH263", "Child Runs Off", 35, "medium shot", "tracking advance with the running figure", "hard key, long shadow", "the future unburdened", "pace must be lighter than the opening"),
        ("SH264", "Weapon Set Down", 135, "extreme close-up", "slow push-in on the released grip", "hard key, specular control", "violence ended", "must invert SH085"),
        ("SH265", "Window Seat", 50, "medium shot", "static locked tripod, view beyond", "diffused daylight, soft falloff", "peace at a distance", "view must match the location"),
        ("SH266", "Final Handshake", 50, "medium shot", "slow orbit settling on the joined hands", "even key, symmetrical", "an agreement that holds", "must match SH062's table"),
        ("SH267", "Lights Out", 35, "establishing shot", "static locked tripod as the practicals die", "key fading to black", "the world closes", "final exposure must match the end card"),
        ("SH268", "Road Ahead", 24, "establishing shot", "slow push-in down the empty road", "warm side light, golden falloff", "continuing without us", "road must match SH023"),
        ("SH269", "Photograph Placed", 85, "close-up", "slow push-in as the image is set down", "warm practical, soft falloff", "memory given a home", "must match SH151"),
        ("SH270", "Final Glance Back", 85, "close-up", "slow pull-back releasing the face", "warm side light, rim holding", "acknowledgement", "must match SH156"),
        ("SH271", "Gate Closes", 35, "establishing shot", "static locked tripod, held after the close", "hard key, deep shadow", "access withdrawn", "gate must match SH008"),
        ("SH272", "Sea Horizon", 24, "establishing shot", "static locked tripod, held long", "flat overcast key, protected highlights", "scale without answer", "horizon level must match every exterior"),
        ("SH273", "Final Object Insert", 135, "extreme close-up", "slow drift across the settled prop", "soft key, warm falloff", "the story's last word", "must match SH255"),
        ("SH274", "Group Departure", 35, "establishing shot", "static locked tripod, figures receding", "warm side light, long shadows", "the world continues", "positions must match SH077"),
        ("SH275", "Last Light Out", 50, "close-up", "slow push-in as the lamp is switched off", "practical dying, deep falloff", "rest earned", "must match the room's established lamp"),
        ("SH276", "Closing Frame", 24, "establishing shot", "slow pull-back to the widest view", "blue hour ambience, protected highlights", "the whole story at once", "must echo the episode's opening frame"),
    ),
    # --------------------------------------------------------------- documentary
    "documentary": (
        ("SH277", "Interview Single", 50, "medium shot", "static locked tripod, slight off-centre", "soft key, gentle rim, eye-light", "testimony", "eyeline must stay off-camera for the whole interview"),
        ("SH278", "Interview Wide", 35, "establishing shot", "static locked tripod, subject in context", "natural available light, soft", "who they are where they are", "room must match the single's background"),
        ("SH279", "Observational Follow", 35, "medium shot", "handheld drift following at distance", "natural available light, mixed", "life without intervention", "screen direction must hold across cuts"),
        ("SH280", "Hands at Work", 85, "close-up", "handheld drift, close but unobtrusive", "natural available light, soft falloff", "craft observed", "action must match the wide coverage"),
        ("SH281", "Verite Conversation", 35, "medium shot", "handheld drift between the speakers", "natural available light, uneven", "unscripted exchange", "must not reverse the axis mid-scene"),
        ("SH282", "Archive Still", 85, "close-up", "slow drift across the photograph", "even soft key, protected highlights", "the record speaks", "image must match the archive source"),
        ("SH283", "Location Survey", 24, "establishing shot", "slow lateral tracking surveying the space", "natural available light, mixed", "place as character", "geography must match every interior"),
        ("SH284", "Process Detail", 135, "extreme close-up", "slow push-in on the mechanism", "hard key, controlled highlights", "how it actually works", "sequence must match the real process"),
        ("SH285", "Witness Reaction", 85, "close-up", "static locked tripod, held", "soft key, minimal rim", "the cost on a face", "reaction must follow the testimony"),
        ("SH286", "Walking Interview", 35, "medium shot", "tracking advance alongside the subject", "natural available light, moving", "thinking in motion", "pace must match the subject's natural walk"),
        ("SH287", "Room Tone Hold", 35, "establishing shot", "static locked tripod, held long", "natural available light, even", "the space between words", "camera must not move at all"),
        ("SH288", "Document Insert", 135, "extreme close-up", "slow drift across the page", "even soft key, protected highlights", "evidence", "text must match the cited source"),
        ("SH289", "Subject at Rest", 50, "medium shot", "static locked tripod, unaware", "natural available light, soft falloff", "the person off duty", "must not be staged"),
        ("SH290", "Community Wide", 24, "establishing shot", "slow dolly advance into the gathering", "natural available light, mixed", "the collective", "crowd must match the location's scale"),
        ("SH291", "Expert Single", 50, "medium shot", "static locked tripod, formal framing", "soft key, gentle rim", "authority cited", "must match SH277's eyeline rule"),
        ("SH292", "Follow the Object", 85, "close-up", "handheld drift tracking the handled item", "natural available light, uneven", "chain of custody", "object must match SH288"),
        ("SH293", "Night Verite", 35, "medium shot", "handheld drift through the dark", "practical sources only, deep falloff", "what happens unobserved", "light level must match the real location"),
        ("SH294", "Machine Rhythm", 135, "extreme close-up", "static locked tripod, cycle inside frame", "hard key, specular control", "labour as pattern", "cycle rate must match the audio"),
        ("SH295", "Subject Looks Up", 85, "close-up", "static locked tripod, gaze meets lens", "soft key, eye-light", "the fourth wall acknowledged", "must be the only such shot in the episode"),
        ("SH296", "Corridor Verite", 35, "medium shot", "handheld advance following from behind", "mixed practicals, uneven", "access granted", "corridor must match the location"),
        ("SH297", "Field Survey", 24, "establishing shot", "slow lateral tracking across the site", "hard noon discipline, even falloff", "work at scale", "geography must match the interview background"),
        ("SH298", "Notebook Detail", 135, "extreme close-up", "slow push-in on the handwriting", "even soft key, protected highlights", "the observer's record", "handwriting must match the cited note"),
        ("SH299", "Closing Testimony", 50, "close-up", "slow push-in as the account ends", "soft key, gentle rim", "the last word is theirs", "must match SH277's framing"),
        ("SH300", "Final Survey", 24, "establishing shot", "crane up and away from the location", "natural available light, protected highlights", "the place outlives the story", "must echo SH283's survey"),
    ),
}


# ---------------------------------------------------------------------------
# Derived technical fields
# ---------------------------------------------------------------------------

#: Depth of field follows the shot size. The Bible ties framing to meaning, and
#: depth is what makes that meaning read: an establishing shot must keep
#: geography legible, an extreme close-up must isolate.
_DEPTH_BY_FRAME: dict[str, str] = {
    "establishing shot": "deep, geography readable",
    "medium shot": "medium, subject separated from context",
    "close-up": "shallow, background soft",
    "extreme close-up": "extremely shallow, razor thin",
}

_FOCUS_BY_FRAME: dict[str, str] = {
    "establishing shot": "deep focus, planes distinct",
    "medium shot": "subject locked, context readable",
    "close-up": "subject sharp, background falling away",
    "extreme close-up": "razor thin on the point of interest",
}

#: Movement vocabulary that implies a stabilised rig rather than a hand.
_STABILISED_WORDS: tuple[str, ...] = (
    "orbit", "crane", "dolly", "tripod", "locked", "tracking", "lateral", "turntable",
)


def _derive_shake(movement: str) -> str:
    lowered = movement.casefold()
    if "handheld" in lowered:
        return "motivated handheld"
    if any(word in lowered for word in _STABILISED_WORDS):
        return "none, stabilised"
    return "none"


def _derive_speed(movement: str) -> str:
    lowered = movement.casefold()
    if "static" in lowered or "locked tripod" in lowered:
        return "static"
    if "whip" in lowered or "fast" in lowered or "sprint" in lowered:
        return "fast, controlled"
    if "orbit" in lowered and "constant" in lowered:
        return "constant"
    if "orbit" in lowered:
        return "constant, unhurried"
    if "extremely slow" in lowered:
        return "extremely slow"
    if "slow" in lowered or "drift" in lowered:
        return "slow, deliberate"
    return "measured"


def build_shot(row: ShotRow, family: str) -> ShotPreset:
    """Expand one authored row into a complete `ShotPreset`.

    The creative fields come from the row; `speed`, `focus`, `shake` and `depth`
    are derived so 300 entries cannot contradict each other.
    """

    code, name, lens_mm, frame, movement, lighting, intention, continuity = row
    return ShotPreset(
        code=code,
        name=name,
        camera_path=movement,
        speed=_derive_speed(movement),
        lens=f"{lens_mm}mm",
        focus=_FOCUS_BY_FRAME.get(frame, "subject locked"),
        shake=_derive_shake(movement),
        depth=_DEPTH_BY_FRAME.get(frame, "medium"),
        intention=intention,
        frame=frame,
        lighting=lighting,
        continuity=continuity,
        family=family,
    )


#: The 290 new presets, expanded from the authored rows.
EXPANDED_SHOTS: tuple[ShotPreset, ...] = tuple(
    build_shot(row, family) for family, rows in _ROWS_BY_FAMILY.items() for row in rows
)

#: The complete library: the ten published presets plus the expansion.
FULL_SHOT_LIBRARY: tuple[ShotPreset, ...] = SEED_SHOTS + EXPANDED_SHOTS

#: The published library target, from SHOT_LIBRARY.md.
LIBRARY_TARGET = 300


class ShotLibrary:
    """Query and validate the full 300-shot library.

    Read-only over the presets. The grammar it validates against is ETAPA 5's
    `CinematicLibrary`, so there is one definition of what a legal lens, frame
    or motivated movement is.
    """

    def __init__(self, shots: tuple[ShotPreset, ...] = FULL_SHOT_LIBRARY, grammar: CinematicLibrary | None = None) -> None:
        self._shots = shots
        self.grammar = grammar or CinematicLibrary()
        self._by_code: dict[str, ShotPreset] = {shot.code: shot for shot in shots}

    # ------------------------------------------------------------------ access

    def all(self) -> tuple[ShotPreset, ...]:
        return self._shots

    def count(self) -> int:
        return len(self._shots)

    def get(self, code: str) -> ShotPreset | None:
        return self._by_code.get(code.strip().upper())

    def families(self) -> tuple[str, ...]:
        """Families that actually have shots, in canonical order."""

        present = {shot.family for shot in self._shots if shot.family}
        return tuple(family for family in FAMILIES if family in present)

    def by_family(self, family: str) -> list[ShotPreset]:
        return [shot for shot in self._shots if shot.family == family]

    def by_lens(self, focal_mm: int) -> list[ShotPreset]:
        return [shot for shot in self._shots if self.grammar.focal_of(shot.lens) == focal_mm]

    def by_frame(self, frame: str) -> list[ShotPreset]:
        needle = frame.strip().casefold()
        return [shot for shot in self._shots if shot.frame.casefold() == needle]

    def by_motivation(self, motivation: str) -> list[ShotPreset]:
        needle = motivation.strip().casefold()
        return [shot for shot in self._shots if needle in self.grammar.motivation_of(shot.camera_path)]

    def search(self, query: str = "") -> list[ShotPreset]:
        """Filter across code, name, family, intention and continuity."""

        if not query.strip():
            return list(self._shots)
        needle = query.strip().casefold()
        return [
            shot
            for shot in self._shots
            if needle in shot.code.casefold()
            or needle in shot.name.casefold()
            or needle in shot.family.casefold()
            or needle in shot.intention.casefold()
            or needle in shot.continuity.casefold()
        ]

    def family_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for shot in self._shots:
            key = shot.family or "published"
            counts[key] = counts.get(key, 0) + 1
        return counts

    # -------------------------------------------------------------- validation

    def violations(self) -> dict[str, list[str]]:
        """Every shot that breaks the CINEMATIC_BIBLE, grouped by code.

        Returns an empty dict when the whole library complies. This is what keeps
        a 300-entry library honest: size is worthless if the entries contradict
        the document they claim to implement.
        """

        problems: dict[str, list[str]] = {}
        for shot in self._shots:
            issues: list[str] = []
            if self.grammar.focal_of(shot.lens) is None:
                issues.append(f"lens '{shot.lens}' is not in the lens language")
            if not self.grammar.motivation_of(shot.camera_path) and not self.grammar.is_still(shot.camera_path):
                issues.append(f"movement '{shot.camera_path}' names no motivation")
            if shot.frame and self.grammar.frame_of(shot.frame) is None:
                issues.append(f"frame '{shot.frame}' is not a known shot size")
            if not shot.intention:
                issues.append("no emotional intention declared")
            # SHOT_LIBRARY.md's expansion policy requires frame, lighting,
            # intention and continuity on *new* shots. The ten published presets
            # predate these fields and the document does not state a shot size
            # for all of them, so they are exempt rather than given invented
            # values. `family` is only set on expanded entries.
            if shot.family:
                for field_name in ("frame", "lighting", "continuity"):
                    if not getattr(shot, field_name):
                        issues.append(f"{field_name} is required on a new shot")
            if issues:
                problems[shot.code] = issues
        return problems

    def duplicates(self) -> list[str]:
        """Codes or names used twice — a stable identifier must be unique.

        Both are counted independently. Comparing the previously seen code
        against the current one (the obvious shortcut) always fails to notice a
        repeated code, because the two are by definition equal.
        """

        code_counts: dict[str, int] = {}
        name_counts: dict[str, int] = {}
        for shot in self._shots:
            code = shot.code.upper()
            name = shot.name.casefold()
            code_counts[code] = code_counts.get(code, 0) + 1
            name_counts[name] = name_counts.get(name, 0) + 1
        return sorted(
            {code for code, count in code_counts.items() if count > 1}
            | {name for name, count in name_counts.items() if count > 1}
        )

    def audit(self) -> dict[str, object]:
        """Library-wide report: size, coverage and compliance."""

        return {
            "total": self.count(),
            "target": LIBRARY_TARGET,
            "meets_target": self.count() >= LIBRARY_TARGET,
            "published": len(SEED_SHOTS),
            "expanded": len(EXPANDED_SHOTS),
            "families": self.family_counts(),
            "violations": self.violations(),
            "duplicates": self.duplicates(),
        }

    # ------------------------------------------------------------- presentation

    def describe(self, shot: ShotPreset) -> str:
        """Full direction line, including the ETAPA 6 expansion fields."""

        parts = [
            f"{shot.code} {shot.name}",
            shot.family and f"[{shot.family}]",
            shot.frame,
            f"{shot.lens}",
            shot.camera_path,
            shot.lighting and f"light: {shot.lighting}",
            f"speed {shot.speed}",
            f"shake {shot.shake}",
            f"{shot.depth} depth",
            shot.intention,
            shot.continuity and f"continuity: {shot.continuity}",
        ]
        return " — ".join(part for part in parts if part) + "."

    def motivations_of(self, shot: ShotPreset) -> tuple[str, ...]:
        """Which Bible motivations this shot's movement claims."""

        return self.grammar.motivation_of(shot.camera_path)

    def as_directable(self, shot: ShotPreset) -> dict[str, object]:
        """The preset plus the grammar read off it, for the shot browser."""

        return {
            **shot.to_dict(),
            "motivations": list(self.motivations_of(shot)),
            "lens_mm": self.grammar.focal_of(shot.lens),
        }
