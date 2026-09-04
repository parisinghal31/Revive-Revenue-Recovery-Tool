"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { get, post, rupees, Failure } from "@/lib/api";
import { GOLD_PLAN } from "@/lib/menu";

export default function RestartAutopay({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [f, setF] = useState<Failure | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { get<Failure>(`/api/failure/${id}`).then(setF); }, [id]);

  const restart = async () => {
    setBusy(true);
    await new Promise((r) => setTimeout(r, 1500));
    await post("/api/pay", { failure_id: id });
    localStorage.setItem("gold", "1");
    setDone(true);
  };

  if (!f) return <div className="flex min-h-screen items-center justify-center bg-neutral-900 text-amber-50">Loading…</div>;

  if (done || f.status === "recovered") return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-neutral-900 px-4 text-center text-amber-50">
      <div className="text-7xl">✨</div>
      <h1 className="mt-4 text-2xl font-extrabold text-amber-400">Welcome back to Gold!</h1>
      <p className="mt-2 text-amber-100/70">Autopay mandate re-authorized · {rupees(f.amount)}/month</p>
      <Link href="/" className="mt-6 rounded-xl bg-amber-400 px-6 py-3 font-bold text-amber-950">Back to Tomato</Link>
    </div>
  );

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-900 px-4">
      <div className="w-full max-w-sm rounded-3xl bg-neutral-800 p-6 text-center text-amber-50 shadow-2xl">
        <span className="text-4xl">🍅✨</span>
        <h1 className="mt-2 text-xl font-extrabold">Don&apos;t lose your Gold perks</h1>
        <p className="mt-1 text-sm text-amber-100/60">
          Hi {f.customer_name}! Your autopay was cancelled — your benefits end soon.
        </p>
        <ul className="mt-4 space-y-1.5 text-left text-sm">
          {GOLD_PLAN.perks.map((p) => <li key={p} className="rounded-lg bg-white/5 px-3 py-2">🌟 {p}</li>)}
        </ul>
        <button onClick={restart} disabled={busy}
          className="mt-5 w-full rounded-xl bg-amber-400 py-3.5 font-extrabold text-amber-950 disabled:opacity-60">
          {busy ? "Authorizing mandate…" : `Restart Autopay · ${rupees(f.amount)}/mo`}
        </button>
        <p className="mt-3 text-[10px] text-amber-100/40">UPI Autopay mandate · secured by Razorpay</p>
      </div>
    </div>
  );
}
