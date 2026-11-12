/*
 * Line icons for System Flow nodes, keyed by the names the style pack lists
 * (tubematic_core/style_packs/system_flow.json extra.icons; a test pins the two
 * together). Each icon is the element list of a Lucide icon on a 24x24 grid,
 * drawn with a stroke and no fill.
 *
 * Generated from lucide-static 1.61.0 (icon-nodes.json). Lucide's licence:
 *
 * ISC License
 *
 * Copyright (c) 2026 Lucide Icons and Contributors
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The following Lucide icons are derived from the Feather project:
 *
 * airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
 *
 * The MIT License (MIT) (for the icons listed above)
 *
 * Copyright (c) 2013-present Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

export type IconElement = [tag: string, attrs: Record<string, string>];

export const ICONS: Record<string, IconElement[]> = {
  api: [["path", {"d": "M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4Z"}], ["path", {"d": "m2 22 3-3"}], ["path", {"d": "M7.5 13.5 10 11"}], ["path", {"d": "M10.5 16.5 13 14"}], ["path", {"d": "m18 3-4 4h6l-4 4"}]], // lucide plug-zap
  app: [["rect", {"width": "7", "height": "7", "x": "3", "y": "3", "rx": "1"}], ["rect", {"width": "7", "height": "7", "x": "14", "y": "3", "rx": "1"}], ["rect", {"width": "7", "height": "7", "x": "14", "y": "14", "rx": "1"}], ["rect", {"width": "7", "height": "7", "x": "3", "y": "14", "rx": "1"}]], // lucide layout-grid
  attacker: [["path", {"d": "m12.5 17-.5-1-.5 1h1z"}], ["path", {"d": "M15 22a1 1 0 0 0 1-1v-1a2 2 0 0 0 1.56-3.25 8 8 0 1 0-11.12 0A2 2 0 0 0 8 20v1a1 1 0 0 0 1 1z"}], ["circle", {"cx": "15", "cy": "12", "r": "1"}], ["circle", {"cx": "9", "cy": "12", "r": "1"}]], // lucide skull
  browser: [["rect", {"x": "2", "y": "4", "width": "20", "height": "16", "rx": "2"}], ["path", {"d": "M10 4v4"}], ["path", {"d": "M2 8h20"}], ["path", {"d": "M6 4v4"}]], // lucide app-window
  bug: [["path", {"d": "M12 20v-9"}], ["path", {"d": "M14 7a4 4 0 0 1 4 4v3a6 6 0 0 1-12 0v-3a4 4 0 0 1 4-4z"}], ["path", {"d": "M14.12 3.88 16 2"}], ["path", {"d": "M21 21a4 4 0 0 0-3.81-4"}], ["path", {"d": "M21 5a4 4 0 0 1-3.55 3.97"}], ["path", {"d": "M22 13h-4"}], ["path", {"d": "M3 21a4 4 0 0 1 3.81-4"}], ["path", {"d": "M3 5a4 4 0 0 0 3.55 3.97"}], ["path", {"d": "M6 13H2"}], ["path", {"d": "m8 2 1.88 1.88"}], ["path", {"d": "M9 7.13V6a3 3 0 1 1 6 0v1.13"}]], // lucide bug
  cache: [["ellipse", {"cx": "12", "cy": "5", "rx": "9", "ry": "3"}], ["path", {"d": "M3 5V19A9 3 0 0 0 15 21.84"}], ["path", {"d": "M21 5V8"}], ["path", {"d": "M21 12L18 17H22L19 22"}], ["path", {"d": "M3 12A9 3 0 0 0 14.59 14.87"}]], // lucide database-zap
  cdn: [["rect", {"x": "16", "y": "16", "width": "6", "height": "6", "rx": "1"}], ["rect", {"x": "2", "y": "16", "width": "6", "height": "6", "rx": "1"}], ["rect", {"x": "9", "y": "2", "width": "6", "height": "6", "rx": "1"}], ["path", {"d": "M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"}], ["path", {"d": "M12 12V8"}]], // lucide network
  chart: [["path", {"d": "M3 3v16a2 2 0 0 0 2 2h16"}], ["path", {"d": "m19 9-5 5-4-4-3 3"}]], // lucide chart-line
  clock: [["circle", {"cx": "12", "cy": "12", "r": "10"}], ["path", {"d": "M12 6v6l4 2"}]], // lucide clock
  cloud: [["path", {"d": "M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"}]], // lucide cloud
  container: [["path", {"d": "M22 7.7c0-.6-.4-1.2-.8-1.5l-6.3-3.9a1.72 1.72 0 0 0-1.7 0l-10.3 6c-.5.2-.9.8-.9 1.4v6.6c0 .5.4 1.2.8 1.5l6.3 3.9a1.72 1.72 0 0 0 1.7 0l10.3-6c.5-.3.9-1 .9-1.5Z"}], ["path", {"d": "M10 21.9V14L2.1 9.1"}], ["path", {"d": "m10 14 11.9-6.9"}], ["path", {"d": "M14 19.8v-8.1"}], ["path", {"d": "M18 17.5V9.4"}]], // lucide container
  cpu: [["path", {"d": "M12 20v2"}], ["path", {"d": "M12 2v2"}], ["path", {"d": "M17 20v2"}], ["path", {"d": "M17 2v2"}], ["path", {"d": "M2 12h2"}], ["path", {"d": "M2 17h2"}], ["path", {"d": "M2 7h2"}], ["path", {"d": "M20 12h2"}], ["path", {"d": "M20 17h2"}], ["path", {"d": "M20 7h2"}], ["path", {"d": "M7 20v2"}], ["path", {"d": "M7 2v2"}], ["rect", {"x": "4", "y": "4", "width": "16", "height": "16", "rx": "2"}], ["rect", {"x": "8", "y": "8", "width": "8", "height": "8", "rx": "1"}]], // lucide cpu
  database: [["ellipse", {"cx": "12", "cy": "5", "rx": "9", "ry": "3"}], ["path", {"d": "M3 5V19A9 3 0 0 0 21 19V5"}], ["path", {"d": "M3 12A9 3 0 0 0 21 12"}]], // lucide database
  disk: [["path", {"d": "M10 16h.01"}], ["path", {"d": "M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"}], ["path", {"d": "M21.946 12.013H2.054"}], ["path", {"d": "M6 16h.01"}]], // lucide hard-drive
  dns: [["path", {"d": "M12 13v8"}], ["path", {"d": "M12 3v3"}], ["path", {"d": "M2.354 10.354a1.207 1.207 0 0 1 0-1.708l2.06-2.06A2 2 0 0 1 5.828 6h12.344a2 2 0 0 1 1.414.586l2.06 2.06a1.207 1.207 0 0 1 0 1.708l-2.06 2.06a2 2 0 0 1-1.414.586H5.828a2 2 0 0 1-1.414-.586z"}]], // lucide signpost
  email: [["path", {"d": "m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7"}], ["rect", {"x": "2", "y": "4", "width": "20", "height": "16", "rx": "2"}]], // lucide mail
  file: [["path", {"d": "M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"}], ["path", {"d": "M14 2v5a1 1 0 0 0 1 1h5"}], ["path", {"d": "M10 9H8"}], ["path", {"d": "M16 13H8"}], ["path", {"d": "M16 17H8"}]], // lucide file-text
  firewall: [["rect", {"width": "18", "height": "18", "x": "3", "y": "3", "rx": "2"}], ["path", {"d": "M12 9v6"}], ["path", {"d": "M16 15v6"}], ["path", {"d": "M16 3v6"}], ["path", {"d": "M3 15h18"}], ["path", {"d": "M3 9h18"}], ["path", {"d": "M8 15v6"}], ["path", {"d": "M8 3v6"}]], // lucide brick-wall
  function: [["rect", {"width": "18", "height": "18", "x": "3", "y": "3", "rx": "2", "ry": "2"}], ["path", {"d": "M9 17c2 0 2.8-1 2.8-2.8V10c0-2 1-3.3 3.2-3"}], ["path", {"d": "M9 11.2h5.7"}]], // lucide square-function
  globe: [["circle", {"cx": "12", "cy": "12", "r": "10"}], ["path", {"d": "M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"}], ["path", {"d": "M2 12h20"}]], // lucide globe
  key: [["path", {"d": "M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"}], ["circle", {"cx": "16.5", "cy": "7.5", "r": ".5", "fill": "currentColor"}]], // lucide key-round
  load_balancer: [["path", {"d": "M16 3h5v5"}], ["path", {"d": "M8 3H3v5"}], ["path", {"d": "M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"}], ["path", {"d": "m15 9 6-6"}]], // lucide split
  lock: [["rect", {"width": "18", "height": "11", "x": "3", "y": "11", "rx": "2", "ry": "2"}], ["path", {"d": "M7 11V7a5 5 0 0 1 10 0v4"}]], // lucide lock
  memory: [["path", {"d": "M12 12v-2"}], ["path", {"d": "M12 18v-2"}], ["path", {"d": "M16 12v-2"}], ["path", {"d": "M16 18v-2"}], ["path", {"d": "M2 11h1.5"}], ["path", {"d": "M20 18v-2"}], ["path", {"d": "M20.5 11H22"}], ["path", {"d": "M4 18v-2"}], ["path", {"d": "M8 12v-2"}], ["path", {"d": "M8 18v-2"}], ["rect", {"x": "2", "y": "6", "width": "20", "height": "10", "rx": "2"}]], // lucide memory-stick
  phone: [["rect", {"width": "14", "height": "20", "x": "5", "y": "2", "rx": "2", "ry": "2"}], ["path", {"d": "M12 18h.01"}]], // lucide smartphone
  queue: [["path", {"d": "M16 5H3"}], ["path", {"d": "M16 12H3"}], ["path", {"d": "M9 19H3"}], ["path", {"d": "m16 16-3 3 3 3"}], ["path", {"d": "M21 5v12a2 2 0 0 1-2 2h-6"}]], // lucide list-end
  router: [["rect", {"width": "20", "height": "8", "x": "2", "y": "14", "rx": "2"}], ["path", {"d": "M6.01 18H6"}], ["path", {"d": "M10.01 18H10"}], ["path", {"d": "M15 10v4"}], ["path", {"d": "M17.84 7.17a4 4 0 0 0-5.66 0"}], ["path", {"d": "M20.66 4.34a8 8 0 0 0-11.31 0"}]], // lucide router
  server: [["rect", {"width": "20", "height": "8", "x": "2", "y": "2", "rx": "2", "ry": "2"}], ["rect", {"width": "20", "height": "8", "x": "2", "y": "14", "rx": "2", "ry": "2"}], ["line", {"x1": "6", "x2": "6.01", "y1": "6", "y2": "6"}], ["line", {"x1": "6", "x2": "6.01", "y1": "18", "y2": "18"}]], // lucide server
  shield: [["path", {"d": "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}], ["path", {"d": "m9 12 2 2 4-4"}]], // lucide shield-check
  user: [["path", {"d": "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"}], ["circle", {"cx": "12", "cy": "7", "r": "4"}]], // lucide user
};
