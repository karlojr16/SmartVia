"use client";

import React, { useState, useEffect, useRef } from "react";

type ToastAlert = {
  camera_id: string;
  vehicle_count: number;
  stationary_count?: number;
};

type AlertItem = {
  timestamp: string;
  camera_id: string;
  vehicle_count: number;
  stationary_count?: number;
  severity?: string;
  title?: string;
  body?: string;
};

type VisionStatus = {
  jam: boolean;
  vehicle_count: number;
  stationary_count: number;
  last_alert_at: string | null;
  error: string | null;
  camera_key: string;
  camera_id: string;
  camera_label: string;
};

const CAMERAS = [
  { key: "cam1", label: "Cámara 1", tag: "trafico.mp4" },
  { key: "cam2", label: "Cámara 2", tag: "trafico2.mp4" },
  { key: "cam3", label: "Cámara 3", tag: "Stream Teléfono" },
  { key: "cam4", label: "Cámara 4", tag: "trafico3.mp4" },
];

export default function Dashboard() {
  // PECUU Alerts State
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [activeAlertIndex, setActiveAlertIndex] = useState<number | null>(null);
  const [lastSync, setLastSync] = useState<string>("");
  const [toast, setToast] = useState<ToastAlert | null>(null);
  const [dispatchedAlerts, setDispatchedAlerts] = useState<Record<string, boolean>>({});
  const primedAlerts = useRef(false);
  const lastAlertKey = useRef<string>("");

  // Layout State: 'split' (50/50), 'cameras' (100%), 'dispatch' (100%)
  const [layoutMode, setLayoutMode] = useState<"split" | "cameras" | "dispatch">("split");

  // SmartVia Vision AI State
  const [selectedCamera, setSelectedCamera] = useState("cam1");
  const [isChangingCamera, setIsChangingCamera] = useState(false);
  const [streamVersion, setStreamVersion] = useState(0);
  const [visionStatus, setVisionStatus] = useState<VisionStatus>({
    jam: false,
    vehicle_count: 0,
    stationary_count: 0,
    last_alert_at: null,
    error: null,
    camera_key: "cam1",
    camera_id: "Cámara 1 · trafico.mp4",
    camera_label: "Cámara 1",
  });

  // Poll PECUU alerts
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await fetch("/api/alerts", { cache: "no-store" });
        if (res.ok) {
          const data: AlertItem[] = await res.json();
          const list = Array.isArray(data) ? [...data].reverse() : [];
          setAlerts(list);
          setLastSync(new Date().toLocaleTimeString());

          if (activeAlertIndex === null && list.length > 0) {
            setActiveAlertIndex(0);
          }

          if (list.length > 0) {
            const newest = list[0];
            const key = `${newest.timestamp}|${newest.camera_id}|${newest.vehicle_count}`;
            if (!primedAlerts.current) {
              primedAlerts.current = true;
              lastAlertKey.current = key;
            } else if (key !== lastAlertKey.current) {
              lastAlertKey.current = key;
              setActiveAlertIndex(0);
              setToast({
                camera_id: newest.camera_id || "Cámara desconocida",
                vehicle_count: newest.vehicle_count ?? 0,
                stationary_count: newest.stationary_count,
              });
            }
          }
        }
      } catch (error) {
        console.error("Failed to fetch alerts:", error);
      }
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 3000);
    return () => clearInterval(interval);
  }, [activeAlertIndex]);

  // Poll SmartVia Vision Status
  useEffect(() => {
    const fetchVisionStatus = async () => {
      try {
        const res = await fetch("/api/vision/status", { cache: "no-store" });
        if (res.ok) {
          const data: VisionStatus = await res.json();
          setVisionStatus(data);
          if (data.camera_key && !isChangingCamera) {
            setSelectedCamera(data.camera_key);
          }
        }
      } catch (err) {
        console.error("Failed to fetch vision status:", err);
      }
    };

    fetchVisionStatus();
    const interval = setInterval(fetchVisionStatus, 1000);
    return () => clearInterval(interval);
  }, [isChangingCamera]);

  // Toast Timer
  useEffect(() => {
    if (!toast) return;
    const hide = setTimeout(() => setToast(null), 5500);
    return () => clearTimeout(hide);
  }, [toast]);

  // Handle Camera Switch
  const handleSelectCamera = async (camKey: string) => {
    setSelectedCamera(camKey);
    setIsChangingCamera(true);
    try {
      await fetch("/api/vision/camera", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera: camKey }),
      });
      setStreamVersion((prev) => prev + 1);
    } catch (err) {
      console.error("Error al cambiar cámara:", err);
    } finally {
      setTimeout(() => setIsChangingCamera(false), 400);
    }
  };

  const activeAlert = activeAlertIndex !== null ? alerts[activeAlertIndex] : null;
  const isCurrentAlertDispatched = activeAlert
    ? Boolean(dispatchedAlerts[activeAlert.timestamp || "default"])
    : false;

  const handleDispatch = () => {
    if (!activeAlert) return;
    const key = activeAlert.timestamp || "default";
    setDispatchedAlerts((prev) => ({ ...prev, [key]: true }));
  };

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-[#07090e] font-sans text-gray-200">
      {/* UNIFIED HEADER */}
      <header className="h-14 border-b border-gray-800 bg-[#0d1117] flex items-center justify-between px-4 shrink-0 z-20">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-gradient-to-r from-red-600 to-amber-600 px-2.5 py-1 rounded text-white font-black text-xs tracking-wider shadow-sm">
            <span>SMARTVIA</span>
            <span className="opacity-50 font-normal">|</span>
            <span>PECUU</span>
          </div>
          <div>
            <h1 className="text-white font-bold tracking-wider text-xs uppercase flex items-center gap-2">
              Centro Unificado de Control & Visión Artificial
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-700/50 px-1.5 py-0.2 rounded">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                SISTEMA EN VIVO
              </span>
            </h1>
            <p className="text-gray-400 text-[10px] uppercase font-mono mt-0.5">
              YOLOv8 ByteTrack AI · Despacho de Contingencias Viales
            </p>
          </div>
        </div>

        {/* CONTROLS & STATUS */}
        <div className="flex items-center gap-4">
          {/* LAYOUT SWITCHER */}
          <div className="flex items-center bg-[#161b22] border border-gray-700 rounded p-0.5 text-xs font-mono">
            <button
              onClick={() => setLayoutMode("split")}
              className={`px-2.5 py-1 rounded transition-colors ${
                layoutMode === "split"
                  ? "bg-blue-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              }`}
              title="Vista dividida 50/50"
            >
              ◫ 50/50 Split
            </button>
            <button
              onClick={() => setLayoutMode("cameras")}
              className={`px-2.5 py-1 rounded transition-colors ${
                layoutMode === "cameras"
                  ? "bg-blue-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              }`}
              title="Solo Cámaras"
            >
              📹 Cámaras
            </button>
            <button
              onClick={() => setLayoutMode("dispatch")}
              className={`px-2.5 py-1 rounded transition-colors ${
                layoutMode === "dispatch"
                  ? "bg-blue-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              }`}
              title="Solo Despacho PECUU"
            >
              🚨 Despacho
            </button>
          </div>

          <div className="font-mono text-xs text-emerald-400 flex items-center gap-2 bg-[#161b22] px-3 py-1 rounded border border-gray-800">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span>SYNC: {lastSync || "CONECTANDO..."}</span>
          </div>
        </div>
      </header>

      {/* MAIN VIEWPORT */}
      <div className="flex flex-1 overflow-hidden">
        {/* ========================================================================= */}
        {/* LEFT HALF: SMARTVIA LIVE AI CAMERAS                                       */}
        {/* ========================================================================= */}
        {(layoutMode === "split" || layoutMode === "cameras") && (
          <section
            className={`flex flex-col border-r border-gray-800 bg-[#0b0e14] overflow-y-auto ${
              layoutMode === "split" ? "w-1/2" : "w-full"
            }`}
          >
            {/* SUB-HEADER: TABS */}
            <div className="p-3 border-b border-gray-800 bg-[#111620] flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-300 uppercase tracking-wider font-mono flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-500"></span>
                  Alimentación de Cámaras (SmartVia)
                </span>
                <span className="text-[10px] font-mono bg-blue-950/70 border border-blue-700/50 text-blue-300 px-2 py-0.5 rounded">
                  4 ACTIVAS
                </span>
              </div>

              {/* CAMERA TABS */}
              <div className="flex items-center gap-1 bg-[#161b22] p-1 rounded-lg border border-gray-700/60">
                {CAMERAS.map((cam) => {
                  const isActive = selectedCamera === cam.key;
                  return (
                    <button
                      key={cam.key}
                      onClick={() => handleSelectCamera(cam.key)}
                      className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                        isActive
                          ? "bg-blue-600 text-white shadow-sm font-semibold"
                          : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                      }`}
                    >
                      {cam.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* VIDEO STREAM CONTAINER */}
            <div className="p-4 flex flex-col gap-4 flex-1">
              <div className="relative rounded-xl border border-gray-800 bg-black overflow-hidden shadow-2xl flex items-center justify-center min-h-[300px] max-h-[54vh]">
                {/* VIDEO FEED IMAGE */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={streamVersion > 0 ? `/video?v=${streamVersion}` : "/video"}
                  alt="Transmisión en vivo SmartVia"
                  className="block w-full h-full max-h-[54vh] object-contain"
                />

                {/* OVERLAYS */}
                <div className="absolute top-2.5 left-3 flex items-center gap-2 z-10 pointer-events-none">
                  <span className="flex items-center gap-1.5 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded border border-gray-700/70 text-[11px] font-mono text-white">
                    <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse"></span>
                    REC · {visionStatus.camera_label || selectedCamera.toUpperCase()}
                  </span>
                  <span className="bg-black/75 backdrop-blur-md px-2 py-1 rounded border border-gray-700/70 text-[10px] font-mono text-gray-300">
                    YOLOv8n + ByteTrack
                  </span>
                </div>

                <div className="absolute top-2.5 right-3 flex items-center gap-2 z-10 pointer-events-none">
                  <span className="bg-black/75 backdrop-blur-md px-2 py-1 rounded border border-gray-700/70 text-[10px] font-mono text-cyan-400">
                    30 FPS · PROCESAMIENTO ACTIVO
                  </span>
                </div>

                {/* JAM WARNING STRIP */}
                {visionStatus.jam && (
                  <div className="absolute bottom-0 inset-x-0 bg-red-600/90 backdrop-blur-md py-1.5 px-4 flex items-center justify-center gap-2 text-white font-bold text-xs uppercase tracking-widest animate-pulse border-t border-red-400">
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                    Congestionamiento Crítico Detectado · Sector Bloqueado
                  </div>
                )}
              </div>

              {/* TELEMETRY & STATUS CARDS */}
              <div className="grid grid-cols-4 gap-3">
                {/* STATUS BADGE */}
                <div
                  className={`col-span-2 rounded-xl p-3.5 border transition-all ${
                    visionStatus.jam
                      ? "border-red-600/70 bg-red-950/40 shadow-[0_0_15px_rgba(239,68,68,0.2)]"
                      : "border-emerald-700/60 bg-emerald-950/30"
                  }`}
                >
                  <p className="text-[10px] uppercase font-mono tracking-wider text-gray-400">
                    Estado en Tiempo Real
                  </p>
                  <p
                    className={`mt-1 text-lg font-bold flex items-center gap-2 ${
                      visionStatus.jam ? "text-red-400" : "text-emerald-400"
                    }`}
                  >
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${
                        visionStatus.jam ? "bg-red-500 animate-ping" : "bg-emerald-400"
                      }`}
                    ></span>
                    {visionStatus.jam ? "Embotellamiento Detectado" : "Tráfico Fluido"}
                  </p>
                </div>

                {/* VEHICLES COUNT */}
                <div className="rounded-xl border border-gray-800 bg-[#121722] p-3">
                  <p className="text-[10px] uppercase font-mono text-gray-400">Vehículos</p>
                  <p className="mt-1 text-2xl font-bold font-mono text-white">
                    {visionStatus.vehicle_count}
                  </p>
                </div>

                {/* STATIONARY COUNT */}
                <div className="rounded-xl border border-gray-800 bg-[#121722] p-3">
                  <p className="text-[10px] uppercase font-mono text-gray-400">Detenidos</p>
                  <p
                    className={`mt-1 text-2xl font-bold font-mono ${
                      visionStatus.stationary_count >= 4 ? "text-red-400" : "text-gray-200"
                    }`}
                  >
                    {visionStatus.stationary_count}
                  </p>
                </div>
              </div>

              {/* CAMERA DETAILS FOOTER */}
              <div className="rounded-lg border border-gray-800/80 bg-[#10141d] p-2.5 px-3.5 flex items-center justify-between text-xs font-mono text-gray-400">
                <div>
                  <span className="text-gray-500">CÁMARA:</span>{" "}
                  <span className="text-gray-200 font-semibold">{visionStatus.camera_id}</span>
                </div>
                <div>
                  <span className="text-gray-500">ÚLTIMA ALERTA:</span>{" "}
                  <span className="text-amber-400">
                    {visionStatus.last_alert_at
                      ? new Date(visionStatus.last_alert_at).toLocaleTimeString()
                      : "NINGUNA"}
                  </span>
                </div>
              </div>

              {/* ERROR ALERT IF ANY */}
              {visionStatus.error && (
                <div className="rounded-lg border border-amber-600/50 bg-amber-950/40 p-3 text-xs text-amber-200 font-mono">
                  {visionStatus.error}
                </div>
              )}
            </div>
          </section>
        )}

        {/* ========================================================================= */}
        {/* RIGHT HALF: PECUU COMMAND & INCIDENT DISPATCH                             */}
        {/* ========================================================================= */}
        {(layoutMode === "split" || layoutMode === "dispatch") && (
          <section
            className={`flex flex-col bg-[#0a0d14] overflow-hidden ${
              layoutMode === "split" ? "w-1/2" : "w-full"
            }`}
          >
            {/* SUB-HEADER */}
            <div className="p-3 border-b border-gray-800 bg-[#111620] flex items-center justify-between shrink-0">
              <span className="text-xs font-bold text-gray-300 uppercase tracking-wider font-mono flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-red-500"></span>
                Centro de Mando e Intervención (PECUU)
              </span>
              <span className="bg-red-500/20 text-red-400 text-[10px] px-2 py-0.5 rounded font-mono border border-red-500/40">
                {alerts.length} ANOMALÍAS REGISTRADAS
              </span>
            </div>

            {/* SPLIT SUB-PANEL: ALERTS LIST & DISPATCH DETAILS */}
            <div className="flex flex-1 overflow-hidden">
              {/* ALERTS FEED COLUMN */}
              <div className="w-1/2 border-r border-gray-800 flex flex-col bg-[#0d1017]">
                <div className="p-2.5 border-b border-gray-800/80 bg-[#121622] flex justify-between items-center">
                  <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider font-mono">
                    Incidentes Críticos
                  </span>
                  <span className="text-[10px] font-mono text-gray-500">CLICK PARA REVISAR</span>
                </div>

                <div className="flex-1 overflow-y-auto p-2 space-y-2">
                  {alerts.length === 0 ? (
                    <div className="text-center text-gray-500 font-mono text-xs py-16 flex flex-col items-center gap-2">
                      <svg
                        className="w-8 h-8 text-gray-600"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="1.5"
                          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      <span>SIN ALERTAS ACTIVAS</span>
                      <span className="text-[10px] text-gray-600">
                        El sistema SmartVia notificará automáticamente al detectar congestión.
                      </span>
                    </div>
                  ) : (
                    alerts.map((alert, index) => {
                      const isSelected = activeAlertIndex === index;
                      const isDispatched = Boolean(
                        dispatchedAlerts[alert.timestamp || "default"]
                      );

                      return (
                        <div
                          key={index}
                          onClick={() => setActiveAlertIndex(index)}
                          className={`p-3 border rounded-lg cursor-pointer transition-all ${
                            isSelected
                              ? "border-red-500/70 bg-red-950/25 shadow-[0_0_12px_rgba(239,68,68,0.15)]"
                              : "border-gray-800/80 bg-[#131722] hover:border-gray-700"
                          }`}
                        >
                          <div className="flex justify-between items-start mb-1.5">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase border-red-500/50 bg-red-500/10 text-red-400 font-bold">
                                CRÍTICO
                              </span>
                              {isDispatched && (
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase border-emerald-500/50 bg-emerald-500/20 text-emerald-300 font-bold">
                                  DESPACHADO
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-gray-400 font-mono">
                              {new Date(alert.timestamp).toLocaleTimeString()}
                            </span>
                          </div>

                          <h3 className="text-xs font-semibold text-gray-200 truncate">
                            {alert.camera_id}
                          </h3>

                          <div className="mt-2 text-[11px] font-mono text-gray-400 flex items-center justify-between border-t border-gray-800/60 pt-1.5">
                            <div>
                              <span className="text-gray-500">TOTAL:</span>{" "}
                              <span className="text-red-400 font-bold">{alert.vehicle_count}</span>
                            </div>
                            {alert.stationary_count != null && (
                              <div>
                                <span className="text-gray-500">DETENIDOS:</span>{" "}
                                <span className="text-amber-400 font-bold">
                                  {alert.stationary_count}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* DISPATCH PROTOCOL COLUMN */}
              <div className="w-1/2 flex flex-col bg-[#0b0e15] overflow-y-auto">
                <div className="p-2.5 border-b border-gray-800/80 bg-[#121622]">
                  <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider font-mono">
                    Protocolo de Intervención
                  </span>
                </div>

                {activeAlert ? (
                  <div className="p-4 flex-1 flex flex-col justify-between">
                    <div className="space-y-4">
                      <div>
                        <div className="text-[10px] text-gray-500 font-mono mb-1">
                          UBICACIÓN DEL INCIDENTE
                        </div>
                        <h3 className="text-base font-bold text-white leading-tight">
                          {activeAlert.camera_id}
                        </h3>
                      </div>

                      <div className="space-y-3">
                        <div className="bg-[#141824] p-3 rounded-lg border border-gray-800">
                          <div className="text-[10px] text-gray-500 font-mono mb-1">
                            UMBRAL DE DETECCIÓN / SEVERIDAD
                          </div>
                          <div className="text-xs text-gray-300 font-mono">
                            {activeAlert.severity ||
                              `${activeAlert.stationary_count} vehículos detenidos`}
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div className="bg-[#141824] p-3 rounded-lg border border-gray-800 border-l-2 border-l-red-500">
                            <div className="text-[10px] text-gray-500 font-mono mb-0.5">
                              VEHÍCULOS
                            </div>
                            <div className="text-xl text-red-400 font-mono font-bold">
                              {activeAlert.vehicle_count}
                            </div>
                          </div>

                          <div className="bg-[#141824] p-3 rounded-lg border border-gray-800 border-l-2 border-l-amber-500">
                            <div className="text-[10px] text-gray-500 font-mono mb-0.5">
                              ESTACIONARIOS
                            </div>
                            <div className="text-xl text-amber-400 font-mono font-bold">
                              {activeAlert.stationary_count ?? "—"}
                            </div>
                          </div>
                        </div>

                        <div className="bg-[#141824] p-3 rounded-lg border border-gray-800">
                          <div className="text-[10px] text-gray-500 font-mono mb-0.5">
                            MARCA DE TIEMPO
                          </div>
                          <div className="text-xs text-gray-300 font-mono">
                            {new Date(activeAlert.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* DISPATCH ACTION */}
                    <div className="pt-4 border-t border-gray-800/80 mt-4">
                      <p className="text-[10px] text-gray-500 font-mono text-center mb-2.5">
                        ALERTA: El despacho de unidad anula ciclos semafóricos automáticos.
                      </p>

                      {isCurrentAlertDispatched ? (
                        <div className="w-full py-3 rounded-lg font-bold uppercase tracking-wider text-xs bg-emerald-600/20 border border-emerald-500/60 text-emerald-300 flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
                          <svg
                            className="w-4 h-4 text-emerald-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                          Unidad Despachada · En Ruta
                        </div>
                      ) : (
                        <button
                          onClick={handleDispatch}
                          className="w-full py-3 rounded-lg font-bold uppercase tracking-widest text-xs bg-red-600 hover:bg-red-500 active:bg-red-700 text-white shadow-[0_0_20px_rgba(220,38,38,0.35)] transition-all flex items-center justify-center gap-2 cursor-pointer"
                        >
                          <svg
                            className="w-4 h-4"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                          </svg>
                          Despachar Unidad de Respuesta
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-gray-500 text-xs font-mono uppercase p-6 text-center">
                    <svg
                      className="w-10 h-10 mb-2 text-gray-700"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.5"
                        d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
                      />
                    </svg>
                    Selecciona una alerta del listado para gestionar el despacho
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      {/* TOAST POPUP FOR NEW CRITICAL ALERTS */}
      {toast && (
        <div
          role="status"
          className="pointer-events-none fixed left-1/2 top-4 z-[100] w-[min(92vw,28rem)] -translate-x-1/2"
        >
          <div className="alert-toast rounded-xl border border-red-500/80 bg-[#160808]/95 px-4 py-3 shadow-[0_8px_32px_rgba(220,38,38,0.45)] backdrop-blur-md">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-red-500 animate-ping"></span>
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-red-400 font-bold">
                ¡NUEVA ALERTA DE EMBOTELLAMIENTO!
              </p>
            </div>
            <p className="mt-1 truncate text-sm font-semibold text-white">{toast.camera_id}</p>
            <p className="mt-0.5 font-mono text-xs text-gray-300">
              {toast.vehicle_count} vehículos
              {toast.stationary_count != null ? ` · ${toast.stationary_count} detenidos` : ""}
              {" · Posible colisión o congestión severa"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
