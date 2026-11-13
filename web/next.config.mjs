/** @type {import('next').NextConfig} */
const nextConfig = {
  // The portal is fully client-rendered and talks to the FastAPI backend, so it ships as static files.
  output: 'export',
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1',
  },
};

export default nextConfig;
