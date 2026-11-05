import { useEffect, useState } from "react";

export type Route = "app" | "about" | "api" | "pipeline";

/** Hash routes ("#/about"), because the built app is served as static files and a
 *  path like /about has no file behind it. */
export function useRoute(): Route {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const on = () => {
      setHash(window.location.hash);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  if (hash === "#/about") return "about";
  if (hash === "#/api") return "api";
  if (hash === "#/pipeline") return "pipeline";
  return "app";
}
