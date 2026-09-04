"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, Crown, MapPin, Search, ShieldCheck, ShoppingBag } from "lucide-react";
import { MenuItemCard } from "@/components/ui/menu-item-card";
import { CATEGORIES, DISHES, Dish, GOLD_PLAN } from "@/lib/menu";
import { rupees } from "@/lib/api";
import { cn } from "@/lib/utils";

type Cart = Record<string, number>;

export default function Home() {
  const [cart, setCart] = useState<Cart>({});
  const [gold, setGold] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");

  useEffect(() => {
    try {
      setCart(JSON.parse(localStorage.getItem("cart") || "{}"));
      setGold(localStorage.getItem("gold") === "1");
    } catch { /* fresh start */ }
  }, []);

  const save = (c: Cart) => { setCart(c); localStorage.setItem("cart", JSON.stringify(c)); };
  const add = (d: Dish) => save({ ...cart, [d.id]: (cart[d.id] || 0) + 1 });
  const remove = (d: Dish) => {
    const c = { ...cart };
    if (c[d.id] > 1) c[d.id] -= 1; else delete c[d.id];
    save(c);
  };

  const visible = useMemo(() => DISHES.filter((d) =>
    (category === "All" || d.category === category) &&
    (query.trim() === "" ||
      `${d.name} ${d.restaurant} ${d.category}`.toLowerCase().includes(query.trim().toLowerCase()))
  ), [query, category]);

  const count = Object.values(cart).reduce((a, b) => a + b, 0);
  const total = DISHES.reduce((s, d) => s + (cart[d.id] || 0) * d.price, 0);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* header */}
      <header className="sticky top-0 z-20 border-b border-border bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:gap-5">
          <Link href="/" className="shrink-0 text-2xl font-extrabold lowercase tracking-tight text-primary">
            tomato
          </Link>

          <button className="hidden cursor-pointer items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground sm:flex"
            aria-label="Choose delivery location">
            <MapPin className="h-4 w-4 text-primary" aria-hidden />
            Koramangala, Bengaluru
            <ChevronDown className="h-3.5 w-3.5" aria-hidden />
          </button>

          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for restaurant or a dish…"
              aria-label="Search for restaurant or a dish"
              className="w-full rounded-xl border border-border bg-muted py-2 pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary focus:bg-white focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <Link href="/gold"
            className="hidden shrink-0 items-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-400 px-3 py-2 text-sm font-bold text-amber-950 transition-opacity hover:opacity-90 sm:flex">
            <Crown className="h-4 w-4" aria-hidden />
            {gold ? "Gold Member" : "Get Gold"}
          </Link>

          <Link href="/dashboard" title="Revive dashboard" aria-label="Revive dashboard"
            className="shrink-0 rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:border-primary hover:text-primary">
            <ShieldCheck className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </header>

      {/* hero */}
      <section className="border-b border-border bg-gradient-to-b from-muted to-background">
        <div className="mx-auto max-w-6xl px-4 pb-6 pt-8 text-center sm:pb-8 sm:pt-12">
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Discover the best food in <span className="text-primary">Bengaluru</span>
          </h1>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">
            Order from 500+ restaurants near you · delivered hot in minutes
          </p>
        </div>
      </section>

      <main className="mx-auto max-w-6xl px-4 pb-32 pt-6">
        {/* category rail */}
        <div className="flex gap-2 overflow-x-auto pb-2" role="tablist" aria-label="Food categories">
          {CATEGORIES.map((c) => (
            <button key={c} role="tab" aria-selected={category === c} onClick={() => setCategory(c)}
              className={cn(
                "shrink-0 cursor-pointer rounded-full border px-4 py-1.5 text-sm font-semibold transition-colors duration-200",
                category === c
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-white text-muted-foreground hover:border-primary hover:text-primary"
              )}>
              {c}
            </button>
          ))}
        </div>

        {/* dish grid */}
        <h2 className="mb-4 mt-6 text-xl font-bold">
          {category === "All" ? "Popular near you" : category}
          <span className="ml-2 text-sm font-normal text-muted-foreground">{visible.length} dishes</span>
        </h2>
        {visible.length === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-12 text-center text-muted-foreground">
            No dishes match “{query}”. Try another craving?
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {visible.map((d) => (
              <MenuItemCard
                key={d.id}
                imageUrl={d.image}
                isVegetarian={d.veg}
                name={d.name}
                price={d.price}
                originalPrice={d.mrp}
                restaurant={d.restaurant}
                rating={d.rating}
                time={d.time}
                quantity={cart[d.id] || 0}
                onAdd={() => add(d)}
                onRemove={() => remove(d)}
              />
            ))}
          </div>
        )}

        {/* gold banner */}
        <div className="mt-12 overflow-hidden rounded-2xl bg-gradient-to-r from-amber-400 to-amber-300 p-6 text-amber-950">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xl font-extrabold">
                <Crown className="h-5 w-5" aria-hidden />
                {GOLD_PLAN.name} — {rupees(GOLD_PLAN.price)}/{GOLD_PLAN.period}
              </div>
              <div className="mt-1 text-sm">{GOLD_PLAN.perks.join(" · ")}</div>
            </div>
            <Link href="/gold"
              className="cursor-pointer rounded-xl bg-amber-950 px-5 py-2.5 font-bold text-amber-100 transition-opacity hover:opacity-90">
              {gold ? "Manage membership" : "Join Gold"}
            </Link>
          </div>
        </div>
      </main>

      {/* cart bar */}
      {count > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-white p-3 shadow-[0_-4px_20px_rgba(0,0,0,0.12)]">
          <Link href="/checkout"
            className="mx-auto flex max-w-6xl cursor-pointer items-center justify-between rounded-xl bg-primary px-5 py-3 font-bold text-primary-foreground transition-opacity hover:opacity-95">
            <span className="flex items-center gap-2">
              <ShoppingBag className="h-5 w-5" aria-hidden />
              {count} item{count > 1 ? "s" : ""} · {rupees(total)}
            </span>
            <span>View Cart →</span>
          </Link>
        </div>
      )}
    </div>
  );
}
