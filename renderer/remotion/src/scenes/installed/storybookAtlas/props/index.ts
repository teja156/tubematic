/*
 * The prop library: every prop the agent can name, by id, in groups by kind.
 * Every id is unique across groups. The catalogue the validator reads (box,
 * place, states, acts, portal) is these same objects, mirrored into the
 * contract fixture by a test.
 */
import { ROOM_PROPS } from "./room";
import { SCIENCE_PROPS } from "./science";
import { THINGS_PROPS } from "./things";
import type { PropEntry } from "./types";

export const PROP_GROUPS: Record<string, Record<string, PropEntry>> = {
  room: ROOM_PROPS,
  science: SCIENCE_PROPS,
  things: THINGS_PROPS,
};

export const PROPS: Record<string, PropEntry> = Object.assign({}, ...Object.values(PROP_GROUPS));
export type { PropEntry } from "./types";
