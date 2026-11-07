/**
 * Host half of dsh-linus-brand.
 *
 * Two jobs:
 *  1. Serve the pet sprite sheets (one SVG per animation state) so the Client
 *     module can point the composer pet at them.
 *  2. Drop the Linus mark into the brand store that the skin reads, so a fresh
 *     machine shows the artwork without anyone uploading it by hand.
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_NAME = "dsh-linus-brand";
const ROUTE_PREFIX = "/dsh-linus-brand";
const ASSETS_PREFIX = `${ROUTE_PREFIX}/assets/`;

/** Animation states of the Deepy pet that this bundle carries artwork for. */
const STATES = new Set([
  "idle",
  "idle-look",
  "idle-spout",
  "thinking",
  "typing",
  "music",
  "conducting",
  "building",
  "error",
  "happy",
  "notification",
  "compacting",
  "sleeping",
  "waking",
  "poke-left",
  "poke-right",
  "tickle",
  "drag",
]);

function packageRoot() {
  return dirname(fileURLToPath(import.meta.url));
}

function dshHome(ctx) {
  try {
    const resolvePath = ctx.get?.("dshHomePath");
    if (typeof resolvePath === "function") return resolvePath();
  } catch {
    /* fall through to the environment */
  }
  return process.env.DSH_HOME ?? join(homedir(), ".dsh");
}

/** Copy mark.png into the skin's brand store unless a mark is already stored. */
function installBrandMark(ctx) {
  const source = join(packageRoot(), "mark.png");
  if (!existsSync(source)) return;
  const directory = join(dshHome(ctx), "dsh-claude-style", "brand");
  const target = join(directory, "mark.png");
  try {
    mkdirSync(directory, { recursive: true });
    if (!existsSync(target)) {
      copyFileSync(source, target);
      ctx.logger?.info?.(`${PACKAGE_NAME}: brand mark stored at ${target}`);
    }
  } catch (error) {
    ctx.logger?.warn?.(`${PACKAGE_NAME}: brand mark not stored: ${error?.message ?? String(error)}`);
  }
}

function registerAssetRoute(ctx, scope) {
  const directory = join(packageRoot(), "assets");
  const server = scope.webServer;
  if (server === undefined || server === null) {
    ctx.logger?.warn?.(`${PACKAGE_NAME}: the host carries no webServer service, so pet sheets stay unserved`);
    return;
  }
  const dispose = server.register({
    kind: "prefix",
    path: ASSETS_PREFIX.slice(0, -1),
    handler: (req, res) => {
      const method = req.method ?? "GET";
      if (method !== "GET" && method !== "HEAD") {
        res.writeHead(405, { allow: "GET, HEAD" });
        res.end();
        return;
      }
      const { pathname } = new URL(req.url ?? "/", "http://local");
      const name = pathname.startsWith(ASSETS_PREFIX) ? pathname.slice(ASSETS_PREFIX.length) : "";
      const state = name.endsWith(".svg") ? name.slice(0, -".svg".length) : "";
      if (state === "" || !STATES.has(state)) {
        res.writeHead(404);
        res.end();
        return;
      }
      const file = join(directory, `${state}.svg`);
      if (!existsSync(file)) {
        res.writeHead(404);
        res.end();
        return;
      }
      const body = readFileSync(file);
      res.writeHead(200, {
        "content-type": "image/svg+xml",
        "content-length": String(body.byteLength),
        "cache-control": "no-cache",
      });
      res.end(method === "HEAD" ? undefined : body);
    },
  });
  scope.effect?.(() => () => {
    if (typeof dispose === "function") dispose();
  });
}

export function apply(ctx) {
  installBrandMark(ctx);
  if (typeof ctx.inject === "function") {
    ctx.inject(["webServer"], (scope) => registerAssetRoute(ctx, scope));
  }
}

export { PACKAGE_NAME as name };
