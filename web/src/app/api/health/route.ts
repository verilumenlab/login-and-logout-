import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    service: 'enterprise-attendance-web',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'development',
  });
}

