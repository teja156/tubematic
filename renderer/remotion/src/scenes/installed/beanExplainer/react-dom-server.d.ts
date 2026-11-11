// The one function sprite.tsx uses from react-dom/server. react-dom is a
// dependency; its type package is not, and one declaration is lighter than one.
declare module "react-dom/server" {
  import type { ReactElement } from "react";
  export function renderToStaticMarkup(element: ReactElement): string;
}
