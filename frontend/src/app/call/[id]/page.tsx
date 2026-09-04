"use client";
import { use, useEffect, useRef, useState } from "react";
import { API, get, rupees, Failure } from "@/lib/api";

const VAPI_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY || "";

type CallState = "ringing" | "connecting" | "live" | "ended" | "error";

export default function CustomerPhone({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [f, setF] = useState<Failure | null>(null);
  const [state, setState] = useState<CallState>("ringing");
  const [err, setErr] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const vapiRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => { get<Failure>(`/api/failure/${id}`).then(setF); }, [id]);

  useEffect(() => {
    if (state !== "live") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [state]);

  const answer = async () => {
    setState("connecting");
    try {
      const cfg = await get<{ assistant?: Record<string, unknown>; error?: string }>(`/voice/web-call-config/${id}`);
      if (!cfg.assistant) throw new Error(cfg.error || "no assistant config");
      if (!VAPI_PUBLIC_KEY) throw new Error("NEXT_PUBLIC_VAPI_PUBLIC_KEY not set — see README setup");
      const { default: Vapi } = await import("@vapi-ai/web");
      const vapi = new Vapi(VAPI_PUBLIC_KEY);
      vapiRef.current = vapi;
      vapi.on("call-start", () => setState("live"));
      vapi.on("call-end", () => setState("ended"));
      vapi.on("speech-start", () => setSpeaking(true));
      vapi.on("speech-end", () => setSpeaking(false));
      vapi.on("error", (e: unknown) => {
        const o = e as { errorMsg?: string; error?: { msg?: string }; message?: string };
        const msg = o?.errorMsg || o?.error?.msg || o?.message || String(e);
        // Asha hanging up (endCall tool / silence timeout / max duration) surfaces as a
        // Daily "ejection" error — that's a normal call ending, not a failure.
        if (/ejection|meeting has ended/i.test(msg)) { setState("ended"); return; }
        setErr(msg);
        setState("error");
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await vapi.start(cfg.assistant as any);
    } catch (e) {
      setErr(String((e as Error)?.message || e));
      setState("error");
    }
  };

  const hangup = () => { vapiRef.current?.stop(); setState("ended"); };

  const mmss = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950 px-4">
      <div className="w-full max-w-xs rounded-[2.5rem] border-4 border-neutral-800 bg-gradient-to-b from-neutral-900 to-black p-6 text-center text-white shadow-2xl">
        <div className="mx-auto mb-6 h-1.5 w-16 rounded-full bg-neutral-700" />

        <div className={`mx-auto flex h-24 w-24 items-center justify-center rounded-full text-5xl ${
          state === "live" && speaking ? "animate-pulse bg-emerald-500/30 ring-4 ring-emerald-400" : "bg-neutral-800"}`}>
          👩‍💼
        </div>
        <h1 className="mt-4 text-xl font-bold">Asha from Tomato</h1>
        <p className="text-sm text-neutral-400">
          {state === "ringing" && "Incoming call… 📳"}
          {state === "connecting" && "Connecting…"}
          {state === "live" && (speaking ? `${mmss} · Asha is speaking` : `${mmss} · listening…`)}
          {state === "ended" && "Call ended"}
          {state === "error" && `⚠️ ${err}`}
        </p>
        {f && state === "ringing" && (
          <p className="mt-2 text-xs text-neutral-500">About your failed {rupees(f.amount)} payment</p>
        )}

        <div className="mt-10 flex justify-center gap-8">
          {state === "ringing" && (
            <>
              <button onClick={answer} className="h-16 w-16 animate-bounce rounded-full bg-green-500 text-2xl">📞</button>
              <button onClick={() => setState("ended")} className="h-16 w-16 rounded-full bg-red-500 text-2xl">📵</button>
            </>
          )}
          {(state === "connecting" || state === "live") && (
            <button onClick={hangup} className="h-16 w-16 rounded-full bg-red-500 text-2xl">📵</button>
          )}
          {(state === "ended" || state === "error") && (
            <a href="/dashboard" className="rounded-xl bg-neutral-800 px-5 py-3 text-sm font-bold">View dashboard →</a>
          )}
        </div>

        <p className="mt-8 text-[10px] text-neutral-600">
          Live AI call via Vapi · tools guarded server-side · {API.replace("http://", "")}
        </p>
      </div>
    </div>
  );
}
