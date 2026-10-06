// Cloudflare Worker behind the map's "Update" button.
// It holds the GitHub token so the public map page never sees it, and only
// starts the workflow when the request carries the right passphrase.
//
// Settings (Cloudflare dashboard -> this Worker -> Settings -> Variables and Secrets):
//   GITHUB_TOKEN    secret  fine-grained token: this repo only, Actions read and write
//   PASSPHRASE      secret  the passphrase you type on the map
//   GITHUB_REPO     text    owner/repo, e.g. ephraimpe/BirdMapper
//   ALLOWED_ORIGIN  text    the map's origin, e.g. https://ephraimpe.github.io
//   WORKFLOW_FILE   text    optional, defaults to update-map.yml
//   GITHUB_BRANCH   text    optional, defaults to main
//
// Routes (both POST with JSON {passphrase, ...}):
//   /status  latest run of the workflow: {id, status, conclusion}
//   /run     start the workflow, body may include {include_yesterday: true|false}

export default {
  async fetch(request, env) {
    const allowOrigin = env.ALLOWED_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": allowOrigin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    const reply = (status, body) =>
      new Response(body === null ? null : JSON.stringify(body), {
        status,
        headers: { ...cors, "Content-Type": "application/json" },
      });

    if (request.method === "OPTIONS") return reply(204, null);
    if (request.method !== "POST") return reply(405, { error: "Use POST" });

    const origin = request.headers.get("Origin");
    if (env.ALLOWED_ORIGIN && origin !== env.ALLOWED_ORIGIN) {
      return reply(403, { error: "Requests from this site are not allowed" });
    }
    if (!env.GITHUB_TOKEN || !env.PASSPHRASE || !env.GITHUB_REPO) {
      return reply(500, { error: "The update service is missing a setting" });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return reply(400, { error: "Bad request" });
    }

    if (!(await samePassphrase(body.passphrase, env.PASSPHRASE))) {
      // slow down guessing
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return reply(401, { error: "Wrong passphrase" });
    }

    const workflow = env.WORKFLOW_FILE || "update-map.yml";
    const base = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${workflow}`;
    const github = (path, init = {}) =>
      fetch(base + path, {
        ...init,
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "map-refresh-worker",
          "Content-Type": "application/json",
        },
      });

    const path = new URL(request.url).pathname;

    if (path === "/run") {
      const res = await github("/dispatches", {
        method: "POST",
        body: JSON.stringify({
          ref: env.GITHUB_BRANCH || "main",
          inputs: { include_yesterday: body.include_yesterday === false ? "false" : "true" },
        }),
      });
      if (!res.ok) return reply(502, { error: `GitHub refused the request (${res.status})` });
      return reply(200, { started: true });
    }

    if (path === "/status") {
      const res = await github("/runs?per_page=1");
      if (!res.ok) return reply(502, { error: `GitHub refused the request (${res.status})` });
      const run = (await res.json()).workflow_runs?.[0];
      return reply(200, run ? { id: run.id, status: run.status, conclusion: run.conclusion } : { id: null });
    }

    return reply(404, { error: "Not found" });
  },
};

// Compare hashes so the check takes the same time whatever was typed
async function samePassphrase(given, expected) {
  if (typeof given !== "string") return false;
  const hash = async (s) => new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
  const [a, b] = await Promise.all([hash(given), hash(expected)]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
