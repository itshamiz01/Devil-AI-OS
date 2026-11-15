import React from "react";
import "./ShinyText.css";

/**
 * ShinyText — adapted from React Bits "ShinyText" (reactbits.dev,
 * github.com/DavidHDev/react-bits), fetched fresh from the official
 * shadcn registry item `ShinyText-TS-CSS` at build time (2026-11-15).
 * Licence: MIT + Commons Clause v1.0 — free to use inside this
 * application; the component itself must never be sold, sublicensed
 * or redistributed onward, so it lives only inside this project.
 *
 * Adaptation note: the registry's canvas-driven JS engine is replaced
 * here with the component's own CSS contract (`.shiny-text` background
 * -clip rules, used as fetched) plus a CSS keyframe sheen in the
 * project's dark + gold identity. `prefers-reduced-motion` disables
 * the sweep. One strong effect, used sparingly (CEO Office heading).
 */
export interface ShinyTextProps {
  text: string;
  color?: string;
  shineColor?: string;
  speed?: number; // seconds per sweep
  className?: string;
}

export function ShinyText({
  text,
  color = "#c9a86a",
  shineColor = "#f7e7bd",
  speed = 3.5,
  className = "",
}: ShinyTextProps): React.ReactElement {
  return (
    <span
      className={`shiny-text shiny-sweep ${className}`}
      style={
        {
          "--shiny-base": color,
          "--shiny-shine": shineColor,
          "--shiny-speed": `${speed}s`,
        } as React.CSSProperties
      }
    >
      {text}
    </span>
  );
}
