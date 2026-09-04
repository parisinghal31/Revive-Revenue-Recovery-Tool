"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { GOLD_PLAN } from "@/lib/menu";
import { post, rupees } from "@/lib/api";

export default function Gold() {
  const [member, setMember] = useState(false);
  const [cancelled, setCancelled] = useState(false);

  useEffect(() => { setMember(localStorage.getItem("gold") === "1"); }, []);

  const join = () => { localStorage.setItem("gold", "1"); setMember(true); };

  const cancel = async () => {
    localStorage.setItem("gold", "0");
    setMember(false);
    setCancelled(true);
    await post("/webhook/razorpay", {
      event: "subscription.cancelled",
      payload: {
        customer_name: "Pari", customer_phone: "+919876543210",
        amount: GOLD_PLAN.price, method: "upi", bank: "HDFC",
      },
    });
  };

  return (
    <div className="min-h-screen bg-neutral-900 text-amber-50">
      <header className="bg-black/40 py-3">
        <div className="mx-auto flex max-w-2xl items-center gap-3 px-4">
          <Link href="/" className="text-xl">←</Link>
          <span className="text-lg font-extrabold">🍅 tomato <span className="text-amber-400">GOLD</span></span>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-10 text-center">
        <div className="text-6xl">✨</div>
        <h1 className="mt-3 text-3xl font-extrabold text-amber-400">{GOLD_PLAN.name}</h1>
        <p className="mt-1 text-amber-100/70">{rupees(GOLD_PLAN.price)}/{GOLD_PLAN.period} · UPI Autopay</p>

        <ul className="mx-auto mt-6 max-w-sm space-y-2 text-left">
          {GOLD_PLAN.perks.map((p) => (
            <li key={p} className="rounded-xl bg-white/5 px-4 py-3">🌟 {p}</li>
          ))}
        </ul>

        {cancelled && (
          <div className="mx-auto mt-6 max-w-sm rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
            Autopay mandate cancelled. 🛡️ Revive noticed — check WhatsApp for a restart link
            (and the <Link href="/dashboard" className="underline">dashboard</Link>).
          </div>
        )}

        {member ? (
          <button onClick={cancel}
            className="mt-8 rounded-xl border border-red-400/60 px-6 py-3 font-bold text-red-300 hover:bg-red-500/10">
            Cancel autopay mandate
          </button>
        ) : (
          <button onClick={join}
            className="mt-8 rounded-xl bg-amber-400 px-8 py-3.5 font-extrabold text-amber-950 hover:bg-amber-300">
            Join with UPI Autopay · {rupees(GOLD_PLAN.price)}/mo
          </button>
        )}
      </main>
    </div>
  );
}
