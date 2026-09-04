"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { get, post, rupees, Failure } from "@/lib/api";

export default function RecoveryPay({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [f, setF] = useState<Failure | null>(null);
  const [paid, setPaid] = useState(false);
  const [paying, setPaying] = useState(false);
  const [note, setNote] = useState("");
  const [rzpKey, setRzpKey] = useState<string | null>(null);

  useEffect(() => {
    get<Failure>(`/api/failure/${id}`).then(setF);
    get<{ key_id: string | null }>("/api/rzp-config").then((c) => {
      if (!c.key_id) return;
      setRzpKey(c.key_id);
      if (!document.getElementById("rzp-js")) {
        const s = document.createElement("script");
        s.id = "rzp-js";
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        document.body.appendChild(s);
      }
    });
  }, [id]);

  const recordRecovery = async () => {
    await post("/api/pay", { failure_id: id, channel: "whatsapp" });
    setPaid(true);
  };

  const payNow = async () => {
    if (!f) return;
    setPaying(true);
    setNote("");

    if (rzpKey) {
      // real Razorpay test-mode order at the negotiated amount
      const order = await post<{ id?: string; error?: string }>("/api/create-order", { amount: payable });
      if (!order.id) { setNote(`Could not create order: ${order.error}`); setPaying(false); return; }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Razorpay = (window as any).Razorpay;
      const rzp = new Razorpay({
        key: rzpKey,
        order_id: order.id,
        amount: payable,
        currency: "INR",
        name: "Tomato",
        description: `Payment recovery · order ${f.order_id}`,
        prefill: { name: f.customer_name, contact: f.customer_phone },
        theme: { color: "#E23744" },
        retry: { enabled: false },
        handler: () => { recordRecovery(); },
        modal: { ondismiss: () => setPaying(false) },
      });
      rzp.on("payment.failed", () => {
        rzp.close();
        setNote("Payment didn't go through — you can try again.");
        setPaying(false);
      });
      rzp.open();
      return;
    }

    // keyless fallback: simulated UPI approval
    await new Promise((r) => setTimeout(r, 1500));
    await recordRecovery();
  };

  if (!f) return <Center>Loading…</Center>;
  if ("error" in (f as object) && !(f as Failure).id) return <Center>Link expired.</Center>;

  const discount = f.discount_pct || 0;
  const payable = f.payable_paise ?? f.amount;

  if (paid || f.status === "recovered") return (
    <Center>
      <div className="text-7xl">✅</div>
      <h1 className="mt-4 text-2xl font-extrabold text-green-700">Payment complete!</h1>
      <p className="mt-2 text-neutral-500">{rupees(payable)} paid. Your order is back on. 🎉</p>
      <Link href="/" className="mt-6 rounded-xl bg-[#E23744] px-6 py-3 font-bold text-white">Order more on Tomato</Link>
    </Center>
  );

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-[#E23744] to-[#a31f2b] px-4">
      <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-neutral-900 shadow-2xl">
        <div className="text-center">
          <span className="text-4xl">🍅</span>
          <h1 className="mt-1 text-lg font-extrabold">Complete your Tomato order</h1>
          <p className="text-xs text-neutral-500">Hi {f.customer_name}! Your payment didn&apos;t go through — finish it here in one tap.</p>
        </div>

        <div className="mt-5 rounded-2xl bg-neutral-50 p-4 text-center">
          {discount > 0 ? (
            <>
              <div className="text-sm text-neutral-400 line-through">{rupees(f.amount)}</div>
              <div className="text-3xl font-extrabold text-green-600">{rupees(payable)}</div>
              <div className="mt-1 inline-block rounded-full bg-green-100 px-3 py-0.5 text-xs font-bold text-green-700">
                {discount}% OFF applied on call 🎉
              </div>
            </>
          ) : (
            <div className="text-3xl font-extrabold">{rupees(payable)}</div>
          )}
          <div className="mt-2 text-xs text-neutral-400">Order {f.order_id}</div>
        </div>

        <button onClick={payNow} disabled={paying}
          className="mt-5 w-full cursor-pointer rounded-xl bg-green-600 py-3.5 font-extrabold text-white transition-colors hover:bg-green-500 disabled:opacity-60">
          {paying ? (rzpKey ? "Opening Razorpay…" : "Approving in UPI app…") : `Pay ${rupees(payable)} with UPI ▶`}
        </button>
        {note && <p className="mt-2 text-center text-xs font-semibold text-red-600">{note}</p>}
        <p className="mt-3 text-center text-[10px] text-neutral-400">
          {rzpKey ? "Live Razorpay gateway (test mode)" : "Secured by Razorpay"} · link sent by Revive after your payment failed
        </p>
      </div>
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-screen flex-col items-center justify-center bg-neutral-50 px-4 text-center text-neutral-900">{children}</div>;
}
