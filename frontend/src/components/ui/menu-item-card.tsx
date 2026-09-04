"use client";
// components/ui/menu-item-card.tsx — Zomato-style dish card

import * as React from "react";
import { motion, type Variants } from "framer-motion";
import { Clock, Minus, Plus, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { rupees } from "@/lib/api";

interface MenuItemCardProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>,
    "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd"> {
  imageUrl: string;
  isVegetarian: boolean;
  name: string;
  price: number; // paise
  originalPrice: number; // paise (MRP before offer)
  restaurant: string;
  rating: number;
  time: string;
  quantity: number; // items of this dish in cart
  onAdd: () => void;
  onRemove: () => void;
}

const cardVariants: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  hover: { y: -4, transition: { duration: 0.2 } },
};

const vegIconVariants: Variants = {
  initial: { scale: 0 },
  animate: { scale: 1, transition: { delay: 0.3, type: "spring", stiffness: 200 } },
};

const MenuItemCard = React.forwardRef<HTMLDivElement, MenuItemCardProps>(
  (
    { className, imageUrl, isVegetarian, name, price, originalPrice, restaurant,
      rating, time, quantity, onAdd, onRemove, ...props },
    ref
  ) => {
    const savings = originalPrice - price;

    return (
      <motion.div
        ref={ref}
        className={cn(
          "group relative flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-sm transition-shadow hover:shadow-lg",
          className
        )}
        variants={cardVariants}
        initial="initial"
        animate="animate"
        whileHover="hover"
        layout
        {...props}
      >
        {/* image */}
        <div className="relative overflow-hidden">
          <img
            src={imageUrl}
            alt={name}
            loading="lazy"
            className="h-44 w-full object-cover transition-transform duration-300 ease-in-out group-hover:scale-105"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />

          {/* veg / non-veg mark */}
          <motion.div
            className="absolute left-3 top-3"
            variants={vegIconVariants}
            aria-label={isVegetarian ? "Vegetarian" : "Non-vegetarian"}
          >
            <div className={cn(
              "flex h-5 w-5 items-center justify-center rounded-md border-2 bg-white",
              isVegetarian ? "border-green-600" : "border-red-600"
            )}>
              <div className={cn("h-2.5 w-2.5 rounded-full", isVegetarian ? "bg-green-600" : "bg-red-600")} />
            </div>
          </motion.div>

          {/* rating pill */}
          <div className="absolute right-3 top-3 flex items-center gap-1 rounded-md bg-green-700 px-1.5 py-0.5 text-xs font-bold text-white">
            {rating.toFixed(1)} <Star className="h-3 w-3 fill-white" aria-hidden />
          </div>

          {/* offer strip */}
          {savings > 0 && (
            <div className="absolute bottom-2 left-3 rounded bg-[#256fef] px-1.5 py-0.5 text-[11px] font-extrabold uppercase tracking-wide text-white">
              {Math.round((savings / originalPrice) * 100)}% OFF
            </div>
          )}
        </div>

        {/* content */}
        <div className="flex flex-grow flex-col p-3.5 text-left">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-[15px] font-semibold leading-tight">{name}</h3>
          </div>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">{restaurant}</p>

          <div className="mt-2.5 flex items-end justify-between">
            <div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-base font-bold">{rupees(price)}</span>
                {savings > 0 && (
                  <span className="text-xs text-muted-foreground line-through">{rupees(originalPrice)}</span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" aria-hidden />
                <span>{time}</span>
              </div>
            </div>

            {/* ADD / stepper — always visible (touch-first), Zomato-style */}
            {quantity === 0 ? (
              <motion.button
                onClick={onAdd}
                whileTap={{ scale: 0.95 }}
                aria-label={`Add ${name} to cart`}
                className="min-h-9 cursor-pointer rounded-lg border border-primary bg-white px-5 py-1.5 text-sm font-extrabold uppercase text-primary shadow-sm transition-colors duration-200 hover:bg-primary hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                Add
              </motion.button>
            ) : (
              <div className="flex min-h-9 items-center gap-1 rounded-lg border border-primary bg-primary text-primary-foreground shadow-sm">
                <button onClick={onRemove} aria-label={`Remove one ${name}`}
                  className="cursor-pointer px-2.5 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Minus className="h-4 w-4" aria-hidden />
                </button>
                <span className="min-w-4 text-center text-sm font-extrabold tabular-nums">{quantity}</span>
                <button onClick={onAdd} aria-label={`Add one more ${name}`}
                  className="cursor-pointer px-2.5 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Plus className="h-4 w-4" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>
      </motion.div>
    );
  }
);

MenuItemCard.displayName = "MenuItemCard";

export { MenuItemCard };
