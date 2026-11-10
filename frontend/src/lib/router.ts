// Minimal hash router: deep links + browser back/forward via `hashchange`,
// zero dependencies, identical behaviour when the bundle is later wrapped
// for Windows desktop. Routes look like `#/agents/<id>`.
import { useEffect, useState } from "react";

export interface Route {
  name: string;
  param: string | null;
  raw: string;
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, "").replace(/^\//, "");
  const parts = raw.split("/").filter(Boolean);
  if (parts.length === 0) return { name: "overview", param: null, raw: "" };
  return {
    name: parts[0],
    param: parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : null,
    raw,
  };
}

export function navigate(name: string, param?: string | null): void {
  const target = param ? `#/${name}/${encodeURIComponent(param)}` : `#/${name}`;
  if (window.location.hash === target) {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = target;
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
