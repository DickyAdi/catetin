import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Tailwind-merge's default font-size class group only knows Tailwind's
// built-in scale (text-sm, text-lg, ...). Without this, our custom v4
// @theme font-size tokens (--text-button-large etc., defined in
// globals.css) get misread as text-color utilities and silently collide
// with real color classes like text-white — e.g. "text-white
// text-button-large" would merge down to just "text-button-large".
const customTwMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "hero-display",
            "hero-display-mobile",
            "display-md",
            "lead",
            "body-strong",
            "body",
            "body-small",
            "button-large",
            "button-utility",
            "nav-link",
            "money-figure",
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return customTwMerge(clsx(inputs));
}
