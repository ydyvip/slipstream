import { common } from "./common";
import { sidebar } from "./sidebar";
import { newrun } from "./newrun";
import { detail } from "./detail";
import { compare } from "./compare";
import { mesh } from "./mesh";
import { lib } from "./lib";
import { extras } from "./extras";

/** Flat key → English message. `t()` falls back to this when a lang key is missing. */
export const en: Record<string, string> = {
  ...common,
  ...sidebar,
  ...newrun,
  ...detail,
  ...compare,
  ...mesh,
  ...lib,
  ...extras,
};
