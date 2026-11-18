/** @type {import('next').NextConfig} */
const nextConfig = {
  // The portal is fully client-rendered and talks to the FastAPI backend, so it ships as static files.
  output: 'export',
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  env: {
    // On Vercel, default to same-origin /api (proxied to Render) so the browser never hits CORS.
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      (process.env.VERCEL ? '/api/v1' : 'http://localhost:8000/api/v1'),
  },
};

export default nextConfig;
