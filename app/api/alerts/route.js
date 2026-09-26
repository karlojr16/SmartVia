import { NextResponse } from 'next/server';

// Temporary in-memory store for hackathon MVP
let currentAlerts = [];

export async function POST(request) {
  const data = await request.json();
  currentAlerts.push(data);
  console.log("ALERT RECEIVED FROM YOLO:", data);
  return NextResponse.json({ status: "Alert logged", data }, { status: 200 });
}

export async function GET() {
  return NextResponse.json(currentAlerts, { status: 200 });
}
