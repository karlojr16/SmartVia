import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// Temporary in-memory store for hackathon MVP (SmartVia YOLO → PECUU)
let currentAlerts = [];
const MAX_ALERTS = 50;

export async function POST(request) {
  const data = await request.json();
  if (!data.timestamp) {
    data.timestamp = new Date().toISOString();
  }
  currentAlerts.push(data);
  if (currentAlerts.length > MAX_ALERTS) {
    currentAlerts = currentAlerts.slice(-MAX_ALERTS);
  }
  console.log('ALERT RECEIVED FROM YOLO:', data);
  return NextResponse.json({ status: 'Alert logged', data }, { status: 200 });
}

export async function GET() {
  return NextResponse.json(currentAlerts, { status: 200 });
}
