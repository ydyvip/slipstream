import { common } from "./common";
import { sidebar } from "./sidebar";
import { newrun } from "./newrun";
import { detail } from "./detail";
import { compare } from "./compare";
import { mesh } from "./mesh";
import { lib } from "./lib";
import { extras } from "./extras";
import { program } from "./program";

export const zh: Record<string, string> = {
  ...common,
  ...sidebar,
  ...newrun,
  ...detail,
  ...compare,
  ...mesh,
  ...lib,
  ...extras,
  ...program,
};
