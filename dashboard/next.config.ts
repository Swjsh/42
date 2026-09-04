import type { NextConfig } from "next";

const COMPANION = process.env.GAMMA_COMPANION_ORIGIN ?? "http://127.0.0.1:4317";

const config: NextConfig = {
  reactStrictMode: true,
  typedRoutes: false,
  devIndicators: { position: "bottom-right" },
  // The cockpit talks to the Gamma companion (army pulse, card fire, orchestrator chat)
  // through a same-origin proxy so the browser never needs CORS or a hardcoded port.
  async rewrites() {
    return [{ source: "/companion/:path*", destination: `${COMPANION}/:path*` }];
  },
};

export default config;
