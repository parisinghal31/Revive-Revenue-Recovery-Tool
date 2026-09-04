"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { DISHES } from "@/lib/menu";
import { get, post, rupees } from "@/lib/api";

const SCENARIOS = [
  { label: "OTP abandoned (hesitation)", code: "AUTHENTICATION_FAILED" },
  { label: "Bank declined", code: "PAYMENT_DECLINED" },
  { label: "Insufficient funds", code: "INSUFFICIENT_FUNDS" },
  { label: "Card expired", code: "CARD_EXPIRED" },
  { label: "Gateway error (transient)", code: "GATEWAY_ERROR" },
  { label: "Issuer bank down", code: "ISSUER_DOWN" },
  { label: "None — keep Razorpay's generic reason", code: "" },
];

const TEST_CARDS = [
  { label: "4111 1111 1111 1111 · Success", code: null },
  { label: "5104 0600 0000 0008 · OTP abandoned", code: "AUTHENTICATION_FAILED" },
  { label: "4000 0000 0000 0002 · Bank declined", code: "PAYMENT_DECLINED" },
  { label: "4000 0000 0000 9995 · Insufficient funds", code: "INSUFFICIENT_FUNDS" },
  { label: "4000 0000 0000 0069 · Card expired", code: "CARD_EXPIRED" },
  { label: "5267 3181 8797 5449 · Gateway error", code: "GATEWAY_ERROR" },
  { label: "4917 6100 0000 0000 · Issuer bank down", code: "ISSUER_DOWN" },
];

type Stage = "cart" | "paying" | "success" | "failed";

export default function Checkout() {
  const [cart, setCart] = useState<Record<string, number>>({});
  const [name, setName] = useState("Pari");
  const [phone, setPhone] = useState("+919876543210");
  const [card, setCard] = useState(1);
  const [stage, setStage] = useState<Stage>("cart");
  const [failCode, setFailCode] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<{ failure_id: string; action: string; link?: string } | null>(null);
  const [ringIn, setRingIn] = useState(0);
  const [sipRing, setSipRing] = useState(false);

  const [plain, setPlain] = useState(false); // ?revive=off - merchant WITHOUT Revive (problem film)
  const [rzpKey, setRzpKey] = useState<string | null>(null);
  const [scenario, setScenario] = useState(0);

  useEffect(() => {
    try { setCart(JSON.parse(localStorage.getItem("cart") || "{}")); } catch { /* empty */ }
    if (new URLSearchParams(window.location.search).get("revive") === "off") { setPlain(true); setCard(2); }
    // reload-safe: if a redirect flow wiped the page mid-payment, reconcile with Razorpay
    const pendingRaw = localStorage.getItem("pending_order");
    if (pendingRaw) {
      localStorage.removeItem("pending_order");
      try {
        const pending = JSON.parse(pendingRaw);
        post<{ status: string; failure_id?: string; action?: string; detail?: { link?: string } }>(
          "/api/check-order", pending).then((res) => {
          if (res.status === "paid") { localStorage.setItem("cart", "{}"); setStage("success"); }
          else if (res.status === "failed" && res.failure_id) {
            setFailCode("PAYMENT_FAILED");
            setStage("failed");
            handleFailure({ failure_id: res.failure_id, action: res.action || "none", detail: res.detail });
          }
        });
      } catch { /* malformed pending order — ignore */ }
    }
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
  }, []);

  const handleFailure = (res: { failure_id: string; action: string; detail?: { link?: string; sip_ring?: boolean } }) => {
    setRecovery({ failure_id: res.failure_id, action: res.action, link: res.detail?.link });
    if (res.action === "voice_call") {
      if (res.detail?.sip_ring) { setSipRing(true); return; } // the actual phone is ringing — don't open a second call
      let n = 4;
      setRingIn(n);
      const t = setInterval(() => {
        n -= 1;
        setRingIn(n);
        if (n <= 0) { clearInterval(t); window.location.href = `/call/${res.failure_id}`; }
      }, 1000);
    }
  };

  const payReal = async () => {
    setStage("paying");
    const order = await post<{ id?: string; error?: string }>("/api/create-order", { amount: total });
    if (!order.id) { alert(`Order failed: ${order.error}`); setStage("cart"); return; }
    localStorage.setItem("pending_order", JSON.stringify({
      order_id: order.id, customer_name: name, customer_phone: phone,
      amount: total, scenario: SCENARIOS[scenario].code,
    }));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Razorpay = (window as any).Razorpay;
    const rzp = new Razorpay({
      key: rzpKey,
      order_id: order.id,
      amount: total,
      currency: "INR",
      name: "Tomato",
      description: "Food order",
      prefill: { name, contact: phone },
      theme: { color: "#E23744" },
      retry: { enabled: false },
      handler: () => { localStorage.removeItem("pending_order"); localStorage.setItem("cart", "{}"); setStage("success"); },
      modal: { ondismiss: () => setStage("cart") },
    });
    rzp.on("payment.failed", async (resp: { error: Record<string, unknown> }) => {
      rzp.close();
      localStorage.removeItem("pending_order");
      setFailCode(String(resp.error?.code || "PAYMENT_FAILED"));
      setStage("failed");
      if (plain) return; // no Revive: the failure just sits there
      const res = await post<{ failure_id: string; action: string; detail?: { link?: string } }>(
        "/api/client-failure",
        { error: resp.error, order_id: order.id, customer_name: name, customer_phone: phone, amount: total, method: "card", scenario: SCENARIOS[scenario].code });
      handleFailure(res);
    });
    rzp.open();
  };

  const items = useMemo(() => DISHES.filter((d) => cart[d.id]), [cart]);
  const total = items.reduce((s, d) => s + cart[d.id] * d.price, 0);
  const bank = ["HDFC", "ICICI", "SBI", "AXIS"][total % 4];

  const pay = async () => {
    setStage("paying");
    const code = TEST_CARDS[card].code;
    await new Promise((r) => setTimeout(r, 1800)); // gateway spinner
    if (!code) {
      localStorage.setItem("cart", "{}");
      setStage("success");
      return;
    }
    setFailCode(code);
    setStage("failed");
    if (plain) return; // no Revive: the failure just sits there
    const res = await post<{ failure_id: string; action: string; detail?: { link?: string } }>("/webhook/razorpay", {
      event: "payment.failed",
      payload: { customer_name: name, customer_phone: phone, amount: total, method: "card", error_code: code, bank },
    });
    handleFailure(res);
  };

  const abandon = async () => {
    const res = await post<{ failure_id: string; action: string }>("/webhook/razorpay", {
      event: "payment.failed",
      payload: { customer_name: name, customer_phone: phone, amount: total, method: "upi", error_code: "CHECKOUT_ABANDONED", bank },
    });
    window.location.href = res.action === "voice_call" ? `/call/${res.failure_id}` : "/";
  };

  if (stage === "success") return (
    <Screen emoji="🎉" title="Order placed!" sub="Your food is being prepared. ETA 25 min.">
      <Link href="/" className="mt-6 rounded-xl bg-[#E23744] px-6 py-3 font-bold text-white">Back to Tomato</Link>
    </Screen>
  );

  // Merchant WITHOUT Revive: a dead end. Nothing is dispatched, nobody follows up.
  if (stage === "failed" && plain) return (
    <div className="min-h-screen bg-neutral-100 text-neutral-900">
      <header className="border-b border-neutral-200 bg-white py-3">
        <div className="mx-auto max-w-2xl px-4 text-xl font-extrabold lowercase tracking-tight text-[#E23744]">tomato</div>
      </header>
      <main className="mx-auto max-w-md px-4 py-16 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-50 text-3xl">⚠️</div>
        <h1 className="mt-5 text-2xl font-bold">Payment failed</h1>
        <p className="mt-2 text-sm text-neutral-500">
          We couldn&apos;t process your payment. Your order has not been placed.
        </p>
        <p className="mt-4 text-xs text-neutral-400">
          If any amount was debited, it will be refunded to your account within 5–7 working days.
        </p>
        <p className="mt-5 font-mono text-[10px] text-neutral-400">Error {failCode} · txn {total}00{items.length}</p>
        <button onClick={() => (rzpKey ? payReal() : pay())}
          className="mt-8 w-full rounded-lg bg-[#E23744] py-3 font-bold text-white">
          Retry payment
        </button>
        <Link href="/" className="mt-3 block text-sm text-neutral-400 underline">Back to menu</Link>
      </main>
    </div>
  );

  if (stage === "failed") return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-neutral-50 px-4 text-center text-neutral-900">
      <div className="animate-bounce text-8xl">😬</div>
      <h1 className="mt-5 text-3xl font-extrabold">Oops! Payment failed</h1>
      <p className="mt-2 max-w-sm text-neutral-500">
        Your money is safe — nothing was charged.<br />
        <b className="text-neutral-700">Don&apos;t worry, we&apos;ll get back to you right away.</b>
      </p>
      <p className="mt-3 font-mono text-[10px] text-neutral-400">ref: {failCode}</p>

      {!recovery && (
        <div className="mt-6 flex items-center gap-2 text-sm text-neutral-500">
          <span className="h-2 w-2 animate-ping rounded-full bg-[#E23744]" />
          Finding the best way to help you…
        </div>
      )}

      {recovery?.action === "whatsapp_link" && recovery.link && (
        <div className="mt-6 w-full max-w-sm rounded-2xl border border-green-200 bg-white p-4 text-left shadow-lg">
          <div className="flex items-center gap-3">
            <span className="text-3xl">💬</span>
            <div className="flex-1">
              <div className="text-sm font-bold">WhatsApp · Tomato</div>
              <div className="text-xs text-neutral-500">Hi! Complete your order in one tap with UPI 👇</div>
            </div>
          </div>
          <Link href={recovery.link}
            className="mt-3 block rounded-xl bg-green-600 py-2.5 text-center text-sm font-extrabold text-white">
            Open payment link
          </Link>
        </div>
      )}

      {recovery && !["voice_call", "whatsapp_link"].includes(recovery.action) && (
        <div className="mt-6 max-w-sm rounded-2xl border border-sky-200 bg-white p-4 text-sm text-sky-900 shadow-lg">
          🛡️ We&apos;re retrying this automatically — you don&apos;t need to do anything.
        </div>
      )}

      <Link href="/" className="mt-8 text-sm font-bold text-neutral-400 underline">Back to Tomato</Link>

      {/* incoming call overlay — slides up when Revive decides to call */}
      {recovery?.action === "voice_call" && (
        <div className="absolute inset-0 flex flex-col items-center justify-end bg-black/70 backdrop-blur-sm">
          <div className="mb-0 w-full max-w-sm rounded-t-[2rem] bg-neutral-900 p-8 pb-12 text-white shadow-2xl">
            <div className="mx-auto flex h-20 w-20 animate-pulse items-center justify-center rounded-full bg-emerald-500/20 text-4xl ring-4 ring-emerald-400/50">
              👩‍💼
            </div>
            <div className="mt-4 text-lg font-bold">Asha from Tomato</div>
            <div className="text-sm text-neutral-400">Incoming call · about your payment</div>
            <div className="mt-1 text-xs text-neutral-500">
              {sipRing ? "📞 your phone is ringing — pick up!" : `auto-connecting in ${ringIn}s…`}
            </div>
            <div className="mt-6 flex justify-center gap-10">
              <button onClick={() => recovery && (window.location.href = `/call/${recovery.failure_id}`)}
                className="flex h-16 w-16 animate-bounce items-center justify-center rounded-full bg-green-500 text-2xl shadow-lg">
                📞
              </button>
              <Link href="/" className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500 text-2xl shadow-lg">
                📵
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <header className="bg-[#E23744] py-3 text-white">
        <div className="mx-auto flex max-w-2xl items-center gap-3 px-4">
          <Link href="/" className="text-xl">←</Link>
          <span className="text-lg font-extrabold">🍅 Checkout</span>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-6">
        {items.length === 0 ? (
          <div className="rounded-2xl bg-white p-10 text-center shadow-sm">
            Cart is empty. <Link href="/" className="font-bold text-[#E23744]">Add something tasty →</Link>
          </div>
        ) : (
          <>
            <div className="rounded-2xl bg-white p-5 shadow-sm">
              <h2 className="mb-3 font-bold">Your order</h2>
              {items.map((d) => (
                <div key={d.id} className="flex justify-between border-b border-neutral-100 py-2 text-sm">
                  <span>{d.emoji} {d.name} × {cart[d.id]}</span>
                  <span className="font-semibold">{rupees(d.price * cart[d.id])}</span>
                </div>
              ))}
              <div className="flex justify-between pt-3 font-extrabold">
                <span>To pay</span><span>{rupees(total)}</span>
              </div>
            </div>

            <div className="mt-4 rounded-2xl bg-white p-5 shadow-sm">
              <h2 className="mb-3 font-bold">Contact</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                <input value={name} onChange={(e) => setName(e.target.value)}
                  className="rounded-lg border border-neutral-300 px-3 py-2 text-sm" placeholder="Name" />
                <input value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="rounded-lg border border-neutral-300 px-3 py-2 text-sm" placeholder="Phone" />
              </div>
            </div>

            <div className="mt-4 rounded-2xl bg-white p-5 shadow-sm">
              {rzpKey ? (
                <>
                  <h2 className="mb-1 font-bold">Payment</h2>
                  {!plain && <><p className="mb-3 text-xs text-neutral-500">
                    ⚡ Live Razorpay gateway (test mode). In the modal: UPI <b>failure@razorpay</b> = fail,{" "}
                    <b>success@razorpay</b> = success · or Netbanking → any bank → Success/Failure buttons
                  </p>
                  <label className="mb-1 block text-[11px] font-bold text-neutral-500">
                    On failure, treat decline as (test mode only emits generic reasons):
                  </label>
                  <select value={scenario} onChange={(e) => setScenario(+e.target.value)}
                    className="mb-2 w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm">
                    {SCENARIOS.map((s, i) => <option key={s.label} value={i}>{s.label}</option>)}
                  </select></>}
                  <button onClick={payReal} disabled={stage === "paying"}
                    className="mt-1 w-full rounded-xl bg-[#0b2eff] py-3.5 font-extrabold text-white disabled:opacity-60">
                    {stage === "paying" ? "Opening Razorpay…" : `Pay ${rupees(total)} with Razorpay`}
                  </button>
                </>
              ) : (
                <>
                  <h2 className="mb-1 font-bold">Payment — Card</h2>
                  {!plain && <>
                    <p className="mb-3 text-xs text-neutral-500">Simulated gateway: pick a card to choose the outcome</p>
                    <select value={card} onChange={(e) => setCard(+e.target.value)}
                      className="w-full rounded-lg border border-neutral-300 px-3 py-2 font-mono text-sm">
                      {TEST_CARDS.map((c, i) => <option key={c.label} value={i}>{c.label}</option>)}
                    </select>
                  </>}
                  <button onClick={pay} disabled={stage === "paying"}
                    className="mt-4 w-full rounded-xl bg-green-600 py-3.5 font-extrabold text-white disabled:opacity-60">
                    {stage === "paying" ? "Contacting bank…" : `Pay ${rupees(total)}`}
                  </button>
                </>
              )}
              {!plain && (
                <button onClick={abandon} className="mt-3 w-full text-center text-xs text-neutral-400 underline">
                  I&apos;ll decide later (abandon checkout)
                </button>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function Screen({ emoji, title, sub, children }: { emoji: string; title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-neutral-50 px-4 text-center text-neutral-900">
      <div className="text-7xl">{emoji}</div>
      <h1 className="mt-4 text-2xl font-extrabold">{title}</h1>
      <p className="mt-2 text-neutral-500">{sub}</p>
      {children}
    </div>
  );
}
