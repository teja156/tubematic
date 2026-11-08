// An atomic file replace: write a sibling, then rename it over the target. A reader of verdict.json (the MCP
// server's readiness check, `--check`, `--status`) that opens the file mid-write would otherwise see an empty or
// half-written JSON and fail after the verdict was in fact recorded.
import * as fs from "node:fs";

export const writeAtomic = (file: string, text: string): void => {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, text);
  fs.renameSync(tmp, file);
};
